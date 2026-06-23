"""
routes/costs.py — GET /costs endpoints.
Provides cost summary, daily trend, and per-service breakdown.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from services.cost_estimator import get_cost_summary, get_daily_cost_trend

router = APIRouter(prefix="/costs", tags=["Costs"])


@router.get("/summary")
def cost_summary(db: Session = Depends(get_db)):
    """
    Returns the current month's estimated cost summary:
      - total_monthly_cost_usd
      - cost_by_service
      - total_resources
      - idle_resources
      - potential_savings_usd
    """
    return get_cost_summary(db)


@router.get("/trend")
def cost_trend(
    days: int = Query(30, ge=7, le=365, description="Number of past days to include"),
    db:   Session = Depends(get_db),
):
    """
    Returns daily aggregated cost totals for the past N days.
    Used to render the cost trend line chart on the dashboard.
    """
    return {"trend": get_daily_cost_trend(db, days=days)}


@router.get("/by-service")
def cost_by_service(db: Session = Depends(get_db)):
    """
    Returns total monthly cost grouped by AWS service.
    Used for the pie/bar breakdown chart.
    """
    from models.resource import Resource
    from sqlalchemy import func

    rows = (
        db.query(
            Resource.service_type,
            func.sum(Resource.estimated_monthly_cost).label("total"),
            func.count(Resource.id).label("count"),
        )
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
    db: Session = Depends(get_db),
):
    """
    Returns the most expensive resources sorted by monthly cost.
    Used by the 'Top Resources' table on the dashboard.
    """
    from models.resource import Resource

    resources = (
        db.query(Resource)
        .order_by(Resource.estimated_monthly_cost.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "resource_id":   r.resource_id,
            "resource_name": r.resource_name or r.resource_id,
            "service_type":  r.service_type,
            "region":        r.region,
            "status":        r.status,
            "resource_type": r.resource_type,
            "monthly_cost":  round(r.estimated_monthly_cost or 0.0, 2),
        }
        for r in resources
    ]
