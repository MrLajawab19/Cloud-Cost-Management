"""
routes/resources.py — GET /resources endpoints.
Returns paginated list of cloud resources with filtering options.
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from database import get_db
from models.resource import Resource

router = APIRouter(prefix="/resources", tags=["Resources"])


# ── Response Schemas ─────────────────────────────────────────────

class ResourceOut(BaseModel):
    resource_id:   str
    resource_name: Optional[str]
    service_type:  str
    region:        str
    status:        str
    resource_type: Optional[str]
    cpu_utilization_avg:    Optional[float]
    storage_size_gb:        Optional[float]
    request_count:          Optional[float]
    runtime_hours:          Optional[float]
    estimated_monthly_cost: float
    is_idle:    bool
    is_flagged: bool
    last_seen:  Optional[datetime]
    launch_time: Optional[datetime]

    class Config:
        from_attributes = True


class ResourceListResponse(BaseModel):
    total:     int
    resources: List[ResourceOut]


# ── Endpoints ────────────────────────────────────────────────────

@router.get("/", response_model=ResourceListResponse)
def list_resources(
    service_type: Optional[str] = Query(None, description="Filter by service: EC2, S3, RDS, Lambda"),
    status:       Optional[str] = Query(None, description="Filter by status: running, stopped, etc."),
    region:       Optional[str] = Query(None, description="Filter by AWS region"),
    idle_only:    bool = Query(False, description="Show only idle/underutilized resources"),
    skip:  int = Query(0,   ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """
    Returns all tracked cloud resources.
    Supports filtering by service type, status, region, and idle flag.
    """
    query = db.query(Resource)

    if service_type:
        query = query.filter(Resource.service_type == service_type)
    if status:
        query = query.filter(Resource.status == status)
    if region:
        query = query.filter(Resource.region == region)
    if idle_only:
        query = query.filter(Resource.is_idle == True)

    total = query.count()
    resources = query.order_by(Resource.estimated_monthly_cost.desc()).offset(skip).limit(limit).all()

    return {"total": total, "resources": resources}


@router.get("/summary")
def resource_summary(db: Session = Depends(get_db)):
    """
    Returns a high-level count breakdown by service type and status.
    Used by the dashboard summary cards.
    """
    resources = db.query(Resource).all()

    by_service: dict = {}
    by_status:  dict = {}
    idle_count  = 0

    for r in resources:
        by_service[r.service_type] = by_service.get(r.service_type, 0) + 1
        by_status[r.status]        = by_status.get(r.status, 0) + 1
        if r.is_idle:
            idle_count += 1

    return {
        "total":      len(resources),
        "by_service": by_service,
        "by_status":  by_status,
        "idle_count": idle_count,
    }


@router.get("/{resource_id}", response_model=ResourceOut)
def get_resource(resource_id: str, db: Session = Depends(get_db)):
    """Get a single resource by its AWS resource ID."""
    from fastapi import HTTPException
    resource = db.query(Resource).filter(Resource.resource_id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    return resource
