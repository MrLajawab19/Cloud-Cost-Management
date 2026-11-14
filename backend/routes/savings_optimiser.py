"""
routes/savings_optimiser.py — Savings Plan Optimiser API.
Read-only endpoint GET /savings-optimiser/plans?account_id=
Evaluates commitment options across eligible services (EC2, RDS, AzureVM).
"""

import logging
import numpy as np
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any, Tuple
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

# Named dict for illustrative behavior heuristics as required
ILLUSTRATIVE_BEHAVIOR_HEURISTICS = {
    "STABILITY_STEADY_CV": 0.10,
    "STABILITY_VOLATILE_CV": 0.25,
    "TREND_DOWN_PCT": -0.10,
    "FLOOR_PERCENTILE": 10,
    "MIN_COVERAGE": 0.5,
}

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


def _evaluate_commitment_recommendation(
    cv: float,
    trend: float,
    coverage_pct: int,
    options_list: List[Dict[str, Any]]
) -> Tuple[str, str]:
    """Helper to evaluate recommendation rules 2, 3, 4 without anomaly hold."""
    if cv > ILLUSTRATIVE_BEHAVIOR_HEURISTICS["STABILITY_VOLATILE_CV"] or trend <= ILLUSTRATIVE_BEHAVIOR_HEURISTICS["TREND_DOWN_PCT"]:
        if cv > ILLUSTRATIVE_BEHAVIOR_HEURISTICS["STABILITY_VOLATILE_CV"]:
            why = f"Volatile usage (CV {int(round(cv*100))}% > 25%); zero-upfront commitment covers only the stable {coverage_pct}% floor, leaving peak usage on PAYG"
        else:
            why = f"Declining trend ({round(trend*100, 1):+.1f}%/mo <= -10%); zero-upfront commitment covers only the stable {coverage_pct}% floor without capital lock-in"
        return "1y_no_upfront", why

    if cv <= ILLUSTRATIVE_BEHAVIOR_HEURISTICS["STABILITY_STEADY_CV"] and trend > ILLUSTRATIVE_BEHAVIOR_HEURISTICS["TREND_DOWN_PCT"]:
        qualifying = [
            opt for opt in options_list
            if opt["id"] != "pay_as_you_go" and opt["break_even_months"] <= BREAK_EVEN_THRESHOLD_MONTHS
        ]
        if qualifying:
            best_opt = max(qualifying, key=lambda x: x["saving_vs_payg_12m"])
            why = (
                f"Steady usage (CV {int(round(cv*100))}% <= 10%); provides highest net savings "
                f"(${best_opt['saving_vs_payg_12m']:.2f}) with break-even of {best_opt['break_even_months']:.1f} mo "
                f"on {coverage_pct}% coverage"
            )
            return best_opt["id"], why
        return "pay_as_you_go", "No commitment plan achieves break-even within the 8.0-month threshold."

    # Moderate (0.10 < cv <= 0.25)
    why = (
        f"Moderate usage variation (CV {int(round(cv*100))}%); partial upfront balances savings "
        f"and flexibility across the stable {coverage_pct}% commitment floor"
    )
    return "1y_partial_upfront", why


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


def compute_savings_plans(db: Session, account: CloudAccount) -> Dict[str, Any]:
    """
    Core commitment evaluation logic per eligible service (EC2, RDS, AzureVM).
    """
    provider = account.provider.lower()

    if provider == "azure":
        base_eligible = ["AzureVM", "AzureSQL"]
        default_services = ["AzureVM", "AzureSQL", "AzureBlob", "AzureFunctions"]
    else:
        base_eligible = ["EC2", "RDS"]
        default_services = ["EC2", "RDS"]

    # Detect any injected services tagged source='demo_injected'
    injected_services = [
        r[0] for r in db.query(CostRecord.service_type)
        .filter(CostRecord.account_id == account.id, CostRecord.source == "demo_injected")
        .distinct()
        .all()
    ]

    eligible_services = list(default_services)
    for srv in injected_services:
        if srv not in eligible_services:
            eligible_services.append(srv)

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

        has_injected = db.query(CostRecord).filter(
            CostRecord.account_id == account.id,
            CostRecord.service_type == srv,
            CostRecord.source == "demo_injected"
        ).first() is not None
        is_new = bool(has_injected)

        # Services with no commitment product (e.g. S3, Lambda, AzureBlob, AzureFunctions)
        if srv not in base_eligible:
            if srv in forecast_map:
                baseline_monthly = round(forecast_map[srv], 2)
            else:
                recent_recs = db.query(CostRecord.daily_cost_usd).filter(
                    CostRecord.account_id == account.id,
                    CostRecord.service_type == srv
                ).order_by(CostRecord.record_date.desc()).limit(30).all()
                if recent_recs:
                    avg_daily = sum(r[0] for r in recent_recs) / len(recent_recs)
                    baseline_monthly = round(avg_daily * 30.0, 2)
                else:
                    baseline_monthly = 0.0

            services_output.append({
                "service": srv,
                "baseline_monthly": baseline_monthly,
                "cv": None,
                "trend_pct": None,
                "coverage_pct": 0,
                "committed_monthly": 0.0,
                "uncommitted_monthly": baseline_monthly,
                "options": {},
                "options_list": [],
                "recommended": "No commitment option for this service",
                "reason": "No commitment option for this service",
                "preview_if_resolved": None,
                "cash_note": "No upfront cash required",
                "right_size_first_note": None,
                "is_new": is_new,
                "has_commitment_option": False,
                "existing_recommendation": None
            })
            continue

        existing_rec = existing_map.get(srv)

        # Pull the last 30 daily cost records
        recent_records = (
            db.query(CostRecord)
            .filter(
                CostRecord.account_id == account.id,
                CostRecord.service_type == srv
            )
            .order_by(CostRecord.record_date.desc())
            .limit(30)
            .all()
        )

        # Unresolved anomalies for this service
        srv_unresolved_anoms = [
            a for a in recent_anomalies
            if a.service_type == srv and a.is_resolved == False
        ]
        unresolved_dates = {a.record_date for a in srv_unresolved_anoms}

        # Exclude any dates that fall in an active (unresolved) anomaly window for that service
        clean_records = [r for r in recent_records if r.record_date not in unresolved_dates]
        clean_records.sort(key=lambda x: x.record_date)
        clean_daily_costs = [float(r.daily_cost_usd) for r in clean_records]

        # Determine baseline_monthly
        if srv in forecast_map and forecast_map[srv] > 0:
            baseline_monthly = round(forecast_map[srv], 2)
        elif clean_daily_costs:
            baseline_monthly = round(float(np.mean(clean_daily_costs)) * 30.0, 2)
        else:
            baseline_monthly = 0.0

        # Behavioral heuristics & options
        if len(clean_daily_costs) < 14:
            is_new = True
            cv_val = round(float(np.std(clean_daily_costs, ddof=1) / np.mean(clean_daily_costs)), 3) if len(clean_daily_costs) > 1 and np.mean(clean_daily_costs) > 0 else 0.0
            trend_val = 0.0
            coverage = 0.0
            coverage_pct = 0
            committed_monthly = 0.0
            uncommitted_monthly = baseline_monthly
            recommended = "pay_as_you_go"
            reason = "Fewer than 14 days of stable history; observe usage before committing"
            preview_if_resolved = None
            cash_note = "No upfront cash required"
        else:
            std = float(np.std(clean_daily_costs, ddof=1))
            mean = float(np.mean(clean_daily_costs))
            cv_raw = std / mean if mean > 0 else 0.0
            cv_val = round(float(cv_raw), 3)

            forecast_30d = forecast_map.get(srv)
            current_run_rate_30d = mean * 30.0
            if forecast_30d is not None and current_run_rate_30d > 0:
                trend_raw = (forecast_30d / current_run_rate_30d) - 1.0
            else:
                x = np.arange(len(clean_daily_costs))
                slope, _ = np.polyfit(x, clean_daily_costs, 1)
                trend_raw = (slope * 30.0) / (current_run_rate_30d or 1.0)
            trend_val = round(float(trend_raw * 100.0), 1)

            stable_floor_daily = float(np.percentile(clean_daily_costs, ILLUSTRATIVE_BEHAVIOR_HEURISTICS["FLOOR_PERCENTILE"]))
            stable_floor_monthly = stable_floor_daily * 30.0
            coverage = max(
                ILLUSTRATIVE_BEHAVIOR_HEURISTICS["MIN_COVERAGE"],
                min(1.0, stable_floor_monthly / (baseline_monthly or 1.0))
            )
            coverage_pct = int(round(coverage * 100))
            committed_monthly = round(baseline_monthly * coverage, 2)
            uncommitted_monthly = round(baseline_monthly * (1.0 - coverage), 2)

        # Plan options calculated on committed_monthly ONLY; uncommitted_monthly stays on PAYG
        disc_no = ILLUSTRATIVE_PLAN_CONSTANTS["1y_no_upfront"]["discount_pct"]
        disc_part = 0.25 if srv in ["AzureVM", "AzureSQL"] else 0.30
        disc_all = ILLUSTRATIVE_PLAN_CONSTANTS["1y_all_upfront"]["discount_pct"]

        # Option 1: PAYG
        payg = {
            "id": "pay_as_you_go",
            "name": "Pay As You Go",
            "upfront_cash": 0.0,
            "monthly_payment": round(baseline_monthly, 2),
            "monthly_saving": 0.0,
            "total_12m": round(baseline_monthly * 12.0, 2),
            "saving_vs_payg_12m": 0.0,
            "break_even_months": 0.0,
            "discount_pct": 0,
            "is_illustrative": False
        }

        # Option 2: 1y_no_upfront
        comm_monthly_no = committed_monthly * (1.0 - disc_no)
        total_monthly_no = round(comm_monthly_no + uncommitted_monthly, 2)
        saving_monthly_no = round(baseline_monthly - total_monthly_no, 2)
        total_12m_no = round(total_monthly_no * 12.0, 2)
        saving_12m_no = round((baseline_monthly * 12.0) - total_12m_no, 2)
        opt_no_upfront = {
            "id": "1y_no_upfront",
            "name": "1-Year No Upfront",
            "upfront_cash": 0.0,
            "monthly_payment": total_monthly_no,
            "monthly_saving": saving_monthly_no,
            "total_12m": total_12m_no,
            "saving_vs_payg_12m": saving_12m_no,
            "break_even_months": 0.0,
            "discount_pct": int(disc_no * 100),
            "is_illustrative": True
        }

        # Option 3: 1y_partial_upfront
        comm_total_12m_part = committed_monthly * (1.0 - disc_part) * 12.0
        upfront_part = round(comm_total_12m_part * 0.50, 2)
        comm_monthly_part = (comm_total_12m_part * 0.50) / 12.0
        total_monthly_part = round(comm_monthly_part + uncommitted_monthly, 2)
        saving_monthly_part = round(baseline_monthly - total_monthly_part, 2)
        total_12m_part = round(upfront_part + (total_monthly_part * 12.0), 2)
        saving_12m_part = round((baseline_monthly * 12.0) - total_12m_part, 2)
        be_part = round(upfront_part / saving_monthly_part, 1) if saving_monthly_part > 0 else 0.0
        opt_partial_upfront = {
            "id": "1y_partial_upfront",
            "name": "1-Year Partial Upfront",
            "upfront_cash": upfront_part,
            "monthly_payment": total_monthly_part,
            "monthly_saving": saving_monthly_part,
            "total_12m": total_12m_part,
            "saving_vs_payg_12m": saving_12m_part,
            "break_even_months": be_part,
            "discount_pct": int(disc_part * 100),
            "is_illustrative": False
        }

        # Option 4: 1y_all_upfront
        comm_total_12m_all = committed_monthly * (1.0 - disc_all) * 12.0
        upfront_all = round(comm_total_12m_all, 2)
        total_monthly_all = round(uncommitted_monthly, 2)
        saving_monthly_all = round(baseline_monthly - total_monthly_all, 2)
        total_12m_all = round(upfront_all + (total_monthly_all * 12.0), 2)
        saving_12m_all = round((baseline_monthly * 12.0) - total_12m_all, 2)
        be_all = round(upfront_all / saving_monthly_all, 1) if saving_monthly_all > 0 else 0.0
        opt_all_upfront = {
            "id": "1y_all_upfront",
            "name": "1-Year All Upfront",
            "upfront_cash": upfront_all,
            "monthly_payment": total_monthly_all,
            "monthly_saving": saving_monthly_all,
            "total_12m": total_12m_all,
            "saving_vs_payg_12m": saving_12m_all,
            "break_even_months": be_all,
            "discount_pct": int(disc_all * 100),
            "is_illustrative": True
        }

        options_dict = {
            "pay_as_you_go": payg,
            "1y_no_upfront": opt_no_upfront,
            "1y_partial_upfront": opt_partial_upfront,
            "1y_all_upfront": opt_all_upfront
        }
        options_list = [payg, opt_no_upfront, opt_partial_upfront, opt_all_upfront]

        # Recommendation rules (precedence order)
        if len(clean_daily_costs) >= 14:
            # 1. Active (unresolved) anomaly in the last 14 days on this service
            active_14d_anoms = [
                a for a in srv_unresolved_anoms
                if a.record_date and (date.today() - a.record_date).days <= 14
            ]
            if active_14d_anoms:
                latest_anom = max(active_14d_anoms, key=lambda x: x.record_date)
                act_c = float(latest_anom.actual_cost) if latest_anom.actual_cost is not None else 0.0
                exp_c = float(latest_anom.forecast_cost) if latest_anom.forecast_cost is not None else 0.0
                diff_usd = max(0.0, float(latest_anom.residual if latest_anom.residual is not None else (act_c - exp_c)))
                diff_pct = ((act_c / exp_c) - 1.0) * 100.0 if exp_c > 0 else 0.0
                recommended = "pay_as_you_go"
                reason = f"Recent unaddressed anomaly on {latest_anom.record_date} (+${diff_usd:.2f} / +{diff_pct:.1f}%). Resolve before committing."
                prev_rec, prev_why = _evaluate_commitment_recommendation(cv_val, trend_val / 100.0, coverage_pct, options_list)
                preview_if_resolved = {
                    "recommended": prev_rec,
                    "coverage": coverage_pct,
                    "reason": prev_why
                }
                cash_note = "No upfront cash required"
            elif baseline_monthly < 50.0:
                recommended = "pay_as_you_go"
                reason = f"Baseline monthly spend (${baseline_monthly:.2f}) is below the $50 minimum threshold for commitment plans."
                preview_if_resolved = None
                cash_note = "No upfront cash required"
            else:
                recommended, reason = _evaluate_commitment_recommendation(cv_val, trend_val / 100.0, coverage_pct, options_list)
                preview_if_resolved = None
                rec_opt = next((o for o in options_list if o["id"] == recommended), None)
                if rec_opt and rec_opt["upfront_cash"] > 0:
                    cash_note = f"requires ${rec_opt['upfront_cash']:.2f} today"
                else:
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
            "cv": cv_val,
            "trend_pct": trend_val,
            "coverage_pct": coverage_pct,
            "committed_monthly": committed_monthly,
            "uncommitted_monthly": uncommitted_monthly,
            "options": options_dict,
            "options_list": options_list,
            "recommended": recommended,
            "reason": reason,
            "preview_if_resolved": preview_if_resolved,
            "cash_note": cash_note,
            "right_size_first_note": right_size_first_note,
            "is_new": is_new,
            "has_commitment_option": True,
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
    return compute_savings_plans(db, account)

