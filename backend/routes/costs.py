"""
routes/costs.py — GET /costs endpoints.
Provides cost summary, daily trend, and per-service breakdown.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime

from database import get_db
from services.cost_estimator import get_cost_summary, get_daily_cost_trend
from services.security import get_current_user
from models.user import User
from models.account import CloudAccount

router = APIRouter(prefix="/costs", tags=["Costs"])


def get_user_account_ids(db: Session, current_user: User, account_id: Optional[str] = None) -> List[str]:
    if account_id:
        acc = db.query(CloudAccount).filter(CloudAccount.id == account_id, CloudAccount.user_id == current_user.id).first()
        if not acc:
            raise HTTPException(status_code=403, detail="Account not found or access denied")
        return [account_id]
    accounts = db.query(CloudAccount).filter(CloudAccount.user_id == current_user.id).all()
    return [acc.id for acc in accounts]


@router.get("/summary")
def cost_summary(
    account_id: Optional[str] = Query(None, description="Filter by specific AWS account ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns the current month's estimated cost summary.
    """
    account_ids = get_user_account_ids(db, current_user, account_id)
    return get_cost_summary(db, account_ids)


@router.get("/trend")
def cost_trend(
    days: int = Query(30, ge=7, le=365, description="Number of past days to include"),
    account_id: Optional[str] = Query(None, description="Filter by specific AWS account ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns daily aggregated cost totals for the past N days.
    Used to render the cost trend line chart on the dashboard.
    """
    account_ids = get_user_account_ids(db, current_user, account_id)
    return {"trend": get_daily_cost_trend(db, account_ids, days=days)}


@router.get("/by-service")
def cost_by_service(
    account_id: Optional[str] = Query(None, description="Filter by specific AWS account ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns total monthly cost grouped by AWS service.
    Used for the pie/bar breakdown chart.
    """
    from models.resource import Resource
    from sqlalchemy import func

    account_ids = get_user_account_ids(db, current_user, account_id)
    if not account_ids:
        return []

    rows = (
        db.query(
            Resource.service_type,
            func.sum(Resource.estimated_monthly_cost).label("total"),
            func.count(Resource.id).label("count"),
        )
        .filter(Resource.account_id.in_(account_ids))
        .group_by(Resource.service_type)
        .all()
    )

    return [
        {
            "service": row.service_type,
            "total_cost_usd": round(float(row.total or 0), 2),
            "resource_count": row.count,
        }
        for row in rows
    ]


@router.get("/top-resources")
def top_resources_by_cost(
    limit: int = Query(10, ge=1, le=50),
    account_id: Optional[str] = Query(None, description="Filter by specific AWS account ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns the most expensive resources sorted by monthly cost.
    Used by the 'Top Resources' table on the dashboard.
    """
    from models.resource import Resource

    account_ids = get_user_account_ids(db, current_user, account_id)
    if not account_ids:
        return []

    resources = (
        db.query(Resource)
        .filter(Resource.account_id.in_(account_ids))
        .order_by(Resource.estimated_monthly_cost.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "resource_id": r.resource_id,
            "resource_name": r.resource_name or r.resource_id,
            "service_type": r.service_type,
            "region": r.region,
            "status": r.status,
            "resource_type": r.resource_type,
            "monthly_cost": round(r.estimated_monthly_cost, 2) if r.estimated_monthly_cost is not None else None,
        }
        for r in resources
    ]


# ── Explainable Forecasting (Item C) ──────────────────────────────

@router.get("/explain")
def explain_costs(
    account_id: Optional[str] = Query(None, description="Filter by specific cloud account ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explainable Forecasting endpoint.
    Returns per-service metrics, 30-day normalized forecasts, deterministic usage narratives,
    and top-5 resource breakdowns with individual explanations.
    """
    from models.resource import Resource
    from models.anomaly import Anomaly
    from models.cost_record import Recommendation
    from services.ml_predictor import predict_costs

    account_ids = get_user_account_ids(db, current_user, account_id)
    if not account_ids:
        return {"services": [], "total_monthly_cost_usd": 0.0}

    # 1. Fetch tracked resources
    resources = (
        db.query(Resource)
        .filter(Resource.account_id.in_(account_ids))
        .all()
    )

    # Calculate total known cost (None-cost resources excluded from shares)
    known_resource_costs = [r.estimated_monthly_cost for r in resources if r.estimated_monthly_cost is not None]
    total_known_cost = sum(known_resource_costs) if known_resource_costs else 0.0

    # 2. Normalized per-service forecast (never raw attribution)
    try:
        forecast_data = predict_costs(db, account_ids)
        per_service_forecast = forecast_data.get("per_service_forecast", [])
        forecast_map = {svc["service"]: float(svc["monthly_estimate_usd"]) for svc in per_service_forecast}
    except Exception:
        forecast_map = {}

    # 3. Active anomalies by service
    active_anomalies = (
        db.query(Anomaly)
        .filter(Anomaly.account_id.in_(account_ids), Anomaly.is_resolved == False)
        .order_by(Anomaly.z_score.desc())
        .all()
    )
    anomalies_by_service = {}
    for a in active_anomalies:
        if a.service_type not in anomalies_by_service:
            anomalies_by_service[a.service_type] = a

    # 4. Active recommendations by resource (excluding commitment)
    active_recs = (
        db.query(Recommendation)
        .filter(
            Recommendation.account_id.in_(account_ids),
            Recommendation.is_resolved == False,
            Recommendation.issue != "No Commitment"
        )
        .order_by(Recommendation.potential_savings_usd.desc())
        .all()
    )
    recs_by_resource = {}
    for rec in active_recs:
        key = (rec.account_id, rec.resource_id)
        if key not in recs_by_resource:
            recs_by_resource[key] = rec

    # Group resources by service
    services_present = sorted(list({r.service_type for r in resources} | set(forecast_map.keys())))
    services_output = []

    for srv in services_present:
        svc_resources = [r for r in resources if r.service_type == srv]
        svc_known_costs = [r.estimated_monthly_cost for r in svc_resources if r.estimated_monthly_cost is not None]

        if svc_known_costs:
            monthly_cost = round(sum(svc_known_costs), 2)
        elif svc_resources:
            monthly_cost = None  # All resources have unknown cost
        else:
            monthly_cost = 0.0

        if total_known_cost > 0 and monthly_cost is not None:
            share_of_total_pct = round((monthly_cost / total_known_cost) * 100.0, 1)
        else:
            share_of_total_pct = 0.0

        forecast_30d = forecast_map.get(srv)
        if forecast_30d is not None:
            forecast_30d = round(forecast_30d, 2)
            if monthly_cost is not None and monthly_cost > 0:
                trend_vs_current_pct = round(((forecast_30d - monthly_cost) / monthly_cost) * 100.0, 1)
            else:
                trend_vs_current_pct = 0.0
        else:
            trend_vs_current_pct = None

        active_anom = anomalies_by_service.get(srv)
        anomaly_note = (
            f"Active {active_anom.severity} anomaly detected on {active_anom.record_date} (z-score: {active_anom.z_score:.2f})."
            if active_anom else None
        )

        # Service-level deterministic narrative
        svc_parts = []
        if monthly_cost is not None:
            svc_parts.append(
                f"{srv} accounts for ${monthly_cost:.2f} ({share_of_total_pct:.1f}% of total spend) "
                f"across {len(svc_resources)} tracked resource{'s' if len(svc_resources) != 1 else ''}."
            )
        else:
            svc_parts.append(
                f"{srv} encompasses {len(svc_resources)} tracked resource{'s' if len(svc_resources) != 1 else ''} with cost unavailable."
            )

        if forecast_30d is not None:
            if trend_vs_current_pct is not None and trend_vs_current_pct > 1.0:
                svc_parts.append(f"The 30-day normalized forecast is ${forecast_30d:.2f}, projecting a +{trend_vs_current_pct:.1f}% upward trend.")
            elif trend_vs_current_pct is not None and trend_vs_current_pct < -1.0:
                svc_parts.append(f"The 30-day normalized forecast is ${forecast_30d:.2f}, projecting a {trend_vs_current_pct:.1f}% downward trend.")
            else:
                svc_parts.append(f"The 30-day normalized forecast is ${forecast_30d:.2f}, indicating stable baseline spend.")

        idle_count = sum(1 for r in svc_resources if r.is_idle)
        if idle_count > 0:
            svc_parts.append(f"{idle_count} resource{'s are' if idle_count != 1 else ' is'} currently flagged as idle.")

        if active_anom:
            svc_parts.append(f"Elevated spend is flagged as an active {active_anom.severity} anomaly.")

        svc_narrative = " ".join(svc_parts)

        # Top 5 resources by cost
        sorted_resources = sorted(
            svc_resources,
            key=lambda r: (r.estimated_monthly_cost is not None, r.estimated_monthly_cost or 0.0),
            reverse=True
        )
        top_5 = sorted_resources[:5]
        top_resources_output = []

        for r in top_5:
            m_cost = round(r.estimated_monthly_cost, 2) if r.estimated_monthly_cost is not None else None
            share_svc = round((m_cost / monthly_cost) * 100.0, 1) if (monthly_cost and monthly_cost > 0 and m_cost is not None) else None
            share_tot = round((m_cost / total_known_cost) * 100.0, 1) if (total_known_cost > 0 and m_cost is not None) else None
            rec = recs_by_resource.get((r.account_id, r.resource_id))

            # Deterministic resource narrative
            r_parts = []
            type_label = r.resource_type or r.service_type
            status_label = r.status.capitalize() if r.status else "Active"
            if m_cost is not None:
                r_parts.append(f"{status_label} {type_label} costing ${m_cost:.2f}/mo in {r.region}.")
            else:
                r_parts.append(f"{status_label} {type_label} in {r.region} with cost unavailable.")

            metrics = []
            if r.runtime_hours is not None:
                metrics.append(f"{r.runtime_hours:.0f}h runtime")
            if r.cpu_utilization_avg is not None:
                metrics.append(f"{r.cpu_utilization_avg:.1f}% avg CPU")
            if r.storage_size_gb is not None:
                metrics.append(f"{r.storage_size_gb:.1f} GB storage")
            if r.request_count is not None:
                metrics.append(f"{r.request_count:.0f} requests")
            if metrics:
                r_parts.append(f"Recorded {', '.join(metrics)}.")

            if r.is_idle:
                r_parts.append("Flagged as idle due to low utilization.")
            if rec:
                r_parts.append(f"Active recommendation: {rec.issue} with ${rec.potential_savings_usd:.2f}/mo potential saving.")
            if active_anom and getattr(r, 'is_flagged', False):
                r_parts.append(f"Flagged as a contributor to {r.service_type} anomaly.")

            r_narrative = " ".join(r_parts)

            top_resources_output.append({
                "resource_name": r.resource_name or r.resource_id,
                "resource_id": r.resource_id,
                "monthly_cost": m_cost,
                "share_of_service_pct": share_svc,
                "share_of_total_pct": share_tot,
                "narrative": r_narrative,
                "recommendation_issue": rec.issue if rec else None,
                "potential_saving": rec.potential_savings_usd if rec else None
            })

        # Remaining resources count
        if len(svc_resources) > 5:
            other_count = len(svc_resources) - 5
            other_known = [r.estimated_monthly_cost for r in sorted_resources[5:] if r.estimated_monthly_cost is not None]
            other_cost = round(sum(other_known), 2) if other_known else None
            other_resources = {
                "count": other_count,
                "label": f"{other_count} other resource{'s' if other_count != 1 else ''}",
                "monthly_cost": other_cost
            }
        else:
            other_resources = None

        services_output.append({
            "service": srv,
            "monthly_cost": monthly_cost,
            "share_of_total_pct": share_of_total_pct,
            "forecast_30d": forecast_30d,
            "trend_vs_current_pct": trend_vs_current_pct,
            "anomaly_note": anomaly_note,
            "narrative": svc_narrative,
            "top_resources": top_resources_output,
            "other_resources": other_resources
        })

    # Sort services by monthly_cost desc
    services_output.sort(
        key=lambda s: (s["monthly_cost"] is not None, s["monthly_cost"] or 0.0),
        reverse=True
    )

    return {
        "services": services_output,
        "total_monthly_cost_usd": round(total_known_cost, 2),
        "as_of": datetime.utcnow().isoformat()
    }
