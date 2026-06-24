"""
routes/costs.py — GET /costs endpoints.
Provides cost summary, daily trend, and per-service breakdown.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List

from database import get_db
from services.cost_estimator import get_cost_summary, get_daily_cost_trend
from services.security import get_current_user
from models.user import User
from models.account import AWSAccount

router = APIRouter(prefix="/costs", tags=["Costs"])


def get_user_account_ids(db: Session, current_user: User, account_id: Optional[str] = None) -> List[str]:
    if account_id:
        acc = db.query(AWSAccount).filter(AWSAccount.id == account_id, AWSAccount.user_id == current_user.id).first()
        if not acc:
            raise HTTPException(status_code=403, detail="Account not found or access denied")
        return [account_id]
    accounts = db.query(AWSAccount).filter(AWSAccount.user_id == current_user.id).all()
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
            "monthly_cost": round(r.estimated_monthly_cost or 0.0, 2),
        }
        for r in resources
    ]
