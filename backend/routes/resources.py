"""
routes/resources.py — GET /resources endpoints.
Returns paginated list of cloud resources with filtering options.
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from database import get_db
from models.resource import Resource
from services.security import get_current_user
from models.user import User
from models.account import CloudAccount

router = APIRouter(prefix="/resources", tags=["Resources"])


def get_user_account_ids(db: Session, current_user: User, account_id: Optional[str] = None) -> List[str]:
    if account_id:
        acc = db.query(CloudAccount).filter(CloudAccount.id == account_id, CloudAccount.user_id == current_user.id).first()
        if not acc:
            raise HTTPException(status_code=403, detail="Account not found or access denied")
        return [account_id]
    accounts = db.query(CloudAccount).filter(CloudAccount.user_id == current_user.id).all()
    return [acc.id for acc in accounts]


# ── Response Schemas ─────────────────────────────────────────────


class ResourceOut(BaseModel):
    resource_id: str
    resource_name: Optional[str]
    service_type: str
    region: str
    status: str
    resource_type: Optional[str]
    cpu_utilization_avg: Optional[float]
    storage_size_gb: Optional[float]
    request_count: Optional[float]
    runtime_hours: Optional[float]
    estimated_monthly_cost: Optional[float] = None
    original_cost_amount: Optional[float] = None
    cost_currency: Optional[str] = None
    is_idle: bool
    is_flagged: bool
    last_seen: Optional[datetime]
    launch_time: Optional[datetime]
    potential_saving_usd: Optional[float] = None
    saving_issue: Optional[str] = None

    class Config:
        from_attributes = True


class ResourceListResponse(BaseModel):
    total: int
    resources: List[ResourceOut]


# ── Endpoints ────────────────────────────────────────────────────


@router.get("/", response_model=ResourceListResponse)
def list_resources(
    service_type: Optional[str] = Query(
        None, description="Filter by service: EC2, S3, RDS, Lambda"
    ),
    status: Optional[str] = Query(
        None, description="Filter by status: running, stopped, etc."
    ),
    region: Optional[str] = Query(None, description="Filter by AWS region"),
    idle_only: bool = Query(
        False, description="Show only idle/underutilized resources"
    ),
    sort: Optional[str] = Query(
        None, description="Sort order: saving_desc, etc."
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    account_id: Optional[str] = Query(None, description="Filter by specific AWS account ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns all tracked cloud resources.
    Supports filtering by service type, status, region, and idle flag.
    Includes potential_saving_usd and saving_issue from active recommendations.
    """
    account_ids = get_user_account_ids(db, current_user, account_id)
    if not account_ids:
        return {"total": 0, "resources": []}

    query = db.query(Resource).filter(Resource.account_id.in_(account_ids))

    if service_type:
        query = query.filter(Resource.service_type == service_type)
    if status:
        query = query.filter(Resource.status == status)
    if region:
        query = query.filter(Resource.region == region)
    if idle_only:
        query = query.filter(Resource.is_idle == True)

    total = query.count()

    from sqlalchemy import func, case
    from models.cost_record import Recommendation

    saving_sub = (
        db.query(
            Recommendation.account_id.label("rec_acc_id"),
            Recommendation.resource_id.label("rec_res_id"),
            func.max(Recommendation.potential_savings_usd).label("max_saving")
        )
        .filter(
            Recommendation.account_id.in_(account_ids),
            Recommendation.is_resolved == False,
            Recommendation.issue != "No Commitment"
        )
        .group_by(Recommendation.account_id, Recommendation.resource_id)
        .subquery()
    )

    if sort == "saving_desc":
        query = (
            query.outerjoin(
                saving_sub,
                (Resource.account_id == saving_sub.c.rec_acc_id) &
                (Resource.resource_id == saving_sub.c.rec_res_id)
            )
            .order_by(
                case((saving_sub.c.max_saving.is_(None), 1), else_=0),
                saving_sub.c.max_saving.desc(),
                case((Resource.estimated_monthly_cost.is_(None), 1), else_=0),
                Resource.estimated_monthly_cost.desc()
            )
        )
    else:
        query = query.order_by(
            case((Resource.estimated_monthly_cost.is_(None), 1), else_=0),
            Resource.estimated_monthly_cost.desc()
        )

    resources = query.offset(skip).limit(limit).all()

    # Populate potential_saving_usd and saving_issue per resource
    if resources:
        res_ids = [r.resource_id for r in resources]
        recs = (
            db.query(Recommendation)
            .filter(
                Recommendation.account_id.in_(account_ids),
                Recommendation.resource_id.in_(res_ids),
                Recommendation.is_resolved == False,
                Recommendation.issue != "No Commitment"
            )
            .order_by(Recommendation.potential_savings_usd.desc())
            .all()
        )
        recs_map = {}
        for rec in recs:
            key = (rec.account_id, rec.resource_id)
            if key not in recs_map:
                recs_map[key] = rec

        for r in resources:
            matched_rec = recs_map.get((r.account_id, r.resource_id))
            r.potential_saving_usd = matched_rec.potential_savings_usd if matched_rec else None
            r.saving_issue = matched_rec.issue if matched_rec else None

    return {"total": total, "resources": resources}


@router.get("/summary")
def resource_summary(
    account_id: Optional[str] = Query(None, description="Filter by specific AWS account ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns a high-level count breakdown by service type and status.
    Used by the dashboard summary cards.
    """
    account_ids = get_user_account_ids(db, current_user, account_id)
    if not account_ids:
        return {"total": 0, "by_service": {}, "by_status": {}, "idle_count": 0}

    resources = db.query(Resource).filter(Resource.account_id.in_(account_ids)).all()

    by_service: dict = {}
    by_status: dict = {}
    idle_count = 0

    for r in resources:
        by_service[r.service_type] = by_service.get(r.service_type, 0) + 1
        by_status[r.status] = by_status.get(r.status, 0) + 1
        if r.is_idle:
            idle_count += 1

    return {
        "total": len(resources),
        "by_service": by_service,
        "by_status": by_status,
        "idle_count": idle_count,
    }


@router.get("/{resource_id}", response_model=ResourceOut)
def get_resource(
    resource_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single resource by its AWS resource ID."""
    account_ids = get_user_account_ids(db, current_user)
    
    resource = db.query(Resource).filter(Resource.resource_id == resource_id).first()
    if not resource or resource.account_id not in account_ids:
        raise HTTPException(status_code=404, detail="Resource not found")

    from models.cost_record import Recommendation
    matched_rec = (
        db.query(Recommendation)
        .filter(
            Recommendation.account_id == resource.account_id,
            Recommendation.resource_id == resource.resource_id,
            Recommendation.is_resolved == False,
            Recommendation.issue != "No Commitment"
        )
        .order_by(Recommendation.potential_savings_usd.desc())
        .first()
    )
    resource.potential_saving_usd = matched_rec.potential_savings_usd if matched_rec else None
    resource.saving_issue = matched_rec.issue if matched_rec else None
    return resource
