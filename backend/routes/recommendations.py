"""
routes/recommendations.py — GET /recommendations endpoints.
Returns cleanup and cost-saving recommendations.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.orm import Session

from database import get_db
from models.cost_record import Recommendation
from services.cleanup_advisor import generate_recommendations

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


@router.get("/")
def list_recommendations(
    severity:     Optional[str] = Query(None, description="Filter: low|medium|high|critical"),
    service_type: Optional[str] = Query(None, description="Filter by service"),
    resolved:     bool = Query(False, description="Include resolved recommendations"),
    db: Session = Depends(get_db),
):
    """
    Returns all active cleanup and cost-saving recommendations.
    Sorted by severity (high → low) then potential savings.
    """
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    query = db.query(Recommendation)

    if not resolved:
        query = query.filter(Recommendation.is_resolved == False)
    if severity:
        query = query.filter(Recommendation.severity == severity)
    if service_type:
        query = query.filter(Recommendation.service_type == service_type)

    recs = query.all()

    # Sort: severity first, then by potential savings descending
    recs.sort(key=lambda r: (
        severity_order.get(r.severity, 99),
        -r.potential_savings_usd,
    ))

    return [
        {
            "id":            str(r.id),
            "resource_id":   r.resource_id,
            "resource_name": r.resource_name,
            "service_type":  r.service_type,
            "region":        r.region,
            "issue":         r.issue,
            "description":   r.description,
            "action":        r.action,
            "severity":      r.severity,
            "potential_savings_usd": r.potential_savings_usd,
            "is_resolved":   r.is_resolved,
            "created_at":    r.created_at.isoformat() if r.created_at else None,
        }
        for r in recs
    ]


@router.get("/summary")
def recommendations_summary(db: Session = Depends(get_db)):
    """
    Returns aggregate stats about current recommendations.
    Used by the dashboard summary cards.
    """
    recs = db.query(Recommendation).filter(Recommendation.is_resolved == False).all()

    total_savings = sum(r.potential_savings_usd for r in recs)
    by_severity = {}
    for r in recs:
        by_severity[r.severity] = by_severity.get(r.severity, 0) + 1

    return {
        "total_recommendations": len(recs),
        "total_potential_savings_usd": round(total_savings, 2),
        "by_severity": by_severity,
    }


@router.post("/{recommendation_id}/resolve")
def resolve_recommendation(recommendation_id: str, db: Session = Depends(get_db)):
    """Mark a recommendation as resolved (client has taken action)."""
    from fastapi import HTTPException
    import uuid

    rec = db.query(Recommendation).filter(
        Recommendation.id == uuid.UUID(recommendation_id)
    ).first()

    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    rec.is_resolved = True
    db.commit()

    return {"message": "Recommendation marked as resolved", "id": recommendation_id}


@router.post("/refresh")
def refresh_recommendations(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Trigger an on-demand re-scan for recommendations."""
    count = generate_recommendations(db)
    return {"message": f"Regenerated {count} recommendations"}
