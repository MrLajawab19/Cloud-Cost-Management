"""
routes/savings_optimiser.py — Savings Plan Optimiser API.
Read-only endpoint GET /savings-optimiser/plans?account_id=
Evaluates commitment options across eligible services (EC2, RDS, AzureVM).
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from models.user import User
from models.account import CloudAccount
from models.cost_record import CostRecord, Recommendation
from models.anomaly import Anomaly
from services.security import get_current_user
from services.ml_predictor import predict_costs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/savings-optimiser", tags=["Savings Optimiser"])

LOOKBACK_DAYS = 14
BREAK_EVEN_THRESHOLD_MONTHS = 8.0

# ONE named dict for illustrative plan option constants as required
ILLUSTRATIVE_PLAN_CONSTANTS = {
    "pay_as_you_go": {
        "id": "pay_as_you_go",
        "name": "Pay As You Go",
        "discount_pct": 0.0,
        "upfront_pct": 0.0,
        "is_illustrative": False,
        "badge": "On Demand"
    },
    "1y_no_upfront": {
        "id": "1y_no_upfront",
        "name": "1-Year No Upfront",
        "discount_pct": 0.20,
        "upfront_pct": 0.0,
        "is_illustrative": True,
        "badge": "Illustrative (20% off)"
    },
    "1y_partial_upfront": {
        "id": "1y_partial_upfront",
        "name": "1-Year Partial Upfront",
        "discount_pct_aws": 0.30,
        "discount_pct_azure": 0.25,
        "upfront_pct": 0.50,
        "is_illustrative": False,  # Matches existing mock recommendation
        "badge": "Standard Mock (30% off AWS / 25% Azure)"
    },
    "1y_all_upfront": {
        "id": "1y_all_upfront",
        "name": "1-Year All Upfront",
        "discount_pct": 0.35,
        "upfront_pct": 1.0,
        "is_illustrative": True,
        "badge": "Illustrative (35% off)"
    }
}


def _check_account_access(db: Session, current_user: User, account_id: Optional[str]) -> CloudAccount:
    if account_id:
        acc = db.query(CloudAccount).filter(
            CloudAccount.id == account_id,
            CloudAccount.user_id == current_user.id
        ).first()
        if not acc:
            raise HTTPException(status_code=403, detail="Account not found or access denied")
        return acc

    # Default to user's first account
    acc = db.query(CloudAccount).filter(CloudAccount.user_id == current_user.id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="No cloud accounts registered")
    return acc


@router.get("/plans")
def get_savings_plans(
    account_id: Optional[str] = Query(None, description="Cloud Account ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Evaluates commitment options per eligible service (EC2, RDS, AzureVM).
    Reproduces existing recommendation figures for 1y_partial_upfront exactly.
    """
    account = _check_account_access(db, current_user, account_id)
    provider = account.provider.lower()

    if provider == "azure":
        eligible_services = ["AzureVM"]
    else:
        eligible_services = ["EC2", "RDS"]

    # 1. Existing commitment recommendations in DB
    existing_recs = db.query(Recommendation).filter(
        Recommendation.account_id == account.id,
        Recommendation.issue == "No Commitment",
        Recommendation.is_resolved == False
    ).all()
    existing_map = {rec.service_type: rec for rec in existing_recs}

    # 2. Baseline monthly forecast from ml_predictor
    try:
        forecast_data = predict_costs(db, [account.id])
        per_service_forecast = forecast_data.get("per_service_forecast", [])
        forecast_map = {svc["service"]: float(svc["monthly_estimate_usd"]) for svc in per_service_forecast}
    except Exception as e:
        logger.warning(f"Failed to generate cost forecast for account {account.id}: {e}")
        forecast_map = {}

    # 3. Anomalous services in last 14 days
    cutoff = datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)
    recent_anomalies = db.query(Anomaly).filter(
        Anomaly.account_id == account.id,
        Anomaly.record_date >= cutoff.date(),
        Anomaly.is_resolved == False
    ).all()
    anomalous_services = {a.service_type for a in recent_anomalies}

    # 4. Unresolved non-commitment potential savings per service
    non_commit_savings = db.query(
        Recommendation.service_type,
        func.sum(Recommendation.potential_savings_usd)
    ).filter(
        Recommendation.account_id == account.id,
        Recommendation.is_resolved == False,
        Recommendation.issue != "No Commitment"
    ).group_by(Recommendation.service_type).all()
    non_commit_map = {row[0]: float(row[1] or 0.0) for row in non_commit_savings}

    services_output = []

    for srv in eligible_services:
        # Check if service has any historical cost records or recommendations
        has_history = db.query(CostRecord).filter(
            CostRecord.account_id == account.id,
            CostRecord.service_type == srv
        ).first() is not None

        if not has_history and srv not in forecast_map and srv not in existing_map:
            continue

        existing_rec = existing_map.get(srv)

        # Determine baseline_monthly
        if existing_rec:
            # Derive baseline from existing recommendation to ensure 100% exact reproduction
            disc = 0.25 if srv == "AzureVM" else 0.30
            upfront_p = 0.50
            baseline_monthly = round(existing_rec.upfront_cost_usd / (12.0 * upfront_p * (1.0 - disc)), 2)
        else:
            baseline_monthly = round(forecast_map.get(srv, 0.0), 2)

        # Check skip conditions matching existing optimiser
        skipped = False
        skip_reason = ""
        if srv in anomalous_services:
            skipped = True
            skip_reason = f"Recent unresolved cost anomaly detected in {srv} within the last 14 days."
        elif baseline_monthly < 50.0:
            skipped = True
            skip_reason = f"Baseline monthly spend (${baseline_monthly:.2f}) is below the $50 minimum threshold for commitment plans."
        elif not has_history:
            skipped = True
            skip_reason = "Insufficient historical usage to generate a reliable commitment baseline."

        # Compute Options
        # Option 1: pay_as_you_go
        payg = {
            "id": "pay_as_you_go",
            "name": "Pay As You Go",
            "upfront_cash": 0.0,
            "monthly_payment": round(baseline_monthly, 2),
            "monthly_saving": 0.0,
            "total_12m": round(baseline_monthly * 12.0, 2),
            "saving_vs_payg_12m": 0.0,
            "break_even_months": 0.0,
            "discount_pct": 0.0,
            "is_illustrative": False
        }

        # Option 2: 1y_no_upfront (20% discount, 0 upfront)
        no_upfront_disc = ILLUSTRATIVE_PLAN_CONSTANTS["1y_no_upfront"]["discount_pct"]
        no_upfront_monthly = round(baseline_monthly * (1.0 - no_upfront_disc), 2)
        no_upfront_total = round(no_upfront_monthly * 12.0, 2)
        no_upfront_savings_12m = round((baseline_monthly * 12.0) - no_upfront_total, 2)
        opt_no_upfront = {
            "id": "1y_no_upfront",
            "name": "1-Year No Upfront",
            "upfront_cash": 0.0,
            "monthly_payment": no_upfront_monthly,
            "monthly_saving": round(baseline_monthly - no_upfront_monthly, 2),
            "total_12m": no_upfront_total,
            "saving_vs_payg_12m": no_upfront_savings_12m,
            "break_even_months": 0.0,
            "discount_pct": int(no_upfront_disc * 100),
            "is_illustrative": True
        }

        # Option 3: 1y_partial_upfront (reproduces existing recommendation exactly)
        part_disc = 0.25 if srv == "AzureVM" else 0.30
        if existing_rec:
            part_upfront_cash = round(existing_rec.upfront_cost_usd, 2)
            part_monthly_saving = round(existing_rec.potential_savings_usd, 2)
            part_monthly_payment = round(baseline_monthly - part_monthly_saving, 2)
            part_total_12m = round(part_upfront_cash + (part_monthly_payment * 12.0), 2)
            part_savings_12m = round((baseline_monthly * 12.0) - part_total_12m, 2)
            part_break_even = round(part_upfront_cash / part_monthly_saving, 1) if part_monthly_saving > 0 else 0.0
        else:
            discounted_30d = baseline_monthly * (1.0 - part_disc)
            part_monthly_payment = round(discounted_30d * 0.50, 2)
            part_upfront_cash = round(discounted_30d * 12.0 * 0.50, 2)
            part_monthly_saving = round(baseline_monthly - part_monthly_payment, 2)
            part_total_12m = round(part_upfront_cash + (part_monthly_payment * 12.0), 2)
            part_savings_12m = round((baseline_monthly * 12.0) - part_total_12m, 2)
            part_break_even = round(part_upfront_cash / part_monthly_saving, 1) if part_monthly_saving > 0 else 0.0

        opt_partial_upfront = {
            "id": "1y_partial_upfront",
            "name": "1-Year Partial Upfront",
            "upfront_cash": part_upfront_cash,
            "monthly_payment": part_monthly_payment,
            "monthly_saving": part_monthly_saving,
            "total_12m": part_total_12m,
            "saving_vs_payg_12m": part_savings_12m,
            "break_even_months": part_break_even,
            "discount_pct": int(part_disc * 100),
            "is_illustrative": False
        }

        # Option 4: 1y_all_upfront (35% discount, 100% upfront)
        all_disc = ILLUSTRATIVE_PLAN_CONSTANTS["1y_all_upfront"]["discount_pct"]
        discounted_30d_all = baseline_monthly * (1.0 - all_disc)
        all_upfront_cash = round(discounted_30d_all * 12.0, 2)
        all_monthly_payment = 0.0
        all_total_12m = all_upfront_cash
        all_savings_12m = round((baseline_monthly * 12.0) - all_total_12m, 2)
        all_break_even = round(all_upfront_cash / baseline_monthly, 1) if baseline_monthly > 0 else 0.0

        opt_all_upfront = {
            "id": "1y_all_upfront",
            "name": "1-Year All Upfront",
            "upfront_cash": all_upfront_cash,
            "monthly_payment": all_monthly_payment,
            "monthly_saving": round(baseline_monthly, 2),
            "total_12m": all_total_12m,
            "saving_vs_payg_12m": all_savings_12m,
            "break_even_months": all_break_even,
            "discount_pct": int(all_disc * 100),
            "is_illustrative": True
        }

        options_dict = {
            "pay_as_you_go": payg,
            "1y_no_upfront": opt_no_upfront,
            "1y_partial_upfront": opt_partial_upfront,
            "1y_all_upfront": opt_all_upfront
        }

        options_list = [payg, opt_no_upfront, opt_partial_upfront, opt_all_upfront]

        # Recommendation logic
        if skipped:
            recommended = "pay_as_you_go"
            reason = skip_reason
            cash_note = "No upfront cash required"
        else:
            # Filter options with break_even <= 8.0
            qualifying = [
                opt for opt in options_list
                if opt["id"] != "pay_as_you_go" and opt["break_even_months"] <= BREAK_EVEN_THRESHOLD_MONTHS
            ]
            if qualifying:
                best_opt = max(qualifying, key=lambda x: x["saving_vs_payg_12m"])
                recommended = best_opt["id"]
                reason = (
                    f"Provides the highest 12-month net savings (${best_opt['saving_vs_payg_12m']:.2f}) "
                    f"with a payback period of {best_opt['break_even_months']:.1f} months "
                    f"(<= {BREAK_EVEN_THRESHOLD_MONTHS} months threshold)."
                )
                cash_note = f"requires ${best_opt['upfront_cash']:.2f} today" if best_opt["upfront_cash"] > 0 else "No upfront cash required"
            else:
                recommended = "pay_as_you_go"
                reason = "No commitment plan achieves break-even within the 8.0-month threshold."
                cash_note = "No upfront cash required"

        # Right-size first note
        unresolved_non_commit = non_commit_map.get(srv, 0.0)
        if unresolved_non_commit > 0:
            right_size_first_note = f"Right-size first: ${unresolved_non_commit:.2f}/mo of idle or oversized spend is included in this baseline"
        else:
            right_size_first_note = None

        services_output.append({
            "service": srv,
            "baseline_monthly": baseline_monthly,
            "options": options_dict,
            "options_list": options_list,
            "recommended": recommended,
            "reason": reason,
            "cash_note": cash_note,
            "right_size_first_note": right_size_first_note,
            "existing_recommendation": {
                "monthly_saving": existing_rec.potential_savings_usd,
                "upfront_cost": existing_rec.upfront_cost_usd,
                "payback_days": existing_rec.payback_days
            } if existing_rec else None
        })

    return {
        "account_id": account.id,
        "account_name": account.name,
        "provider": provider,
        "services": services_output,
        "disclaimer": "Illustrative pricing, not live AWS/Azure rates",
        "empty_message": "Not enough history yet - stay pay-as-you-go" if not services_output else None
    }
