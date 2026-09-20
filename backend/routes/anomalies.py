"""
routes/anomalies.py — GET /anomalies/ and GET /anomalies/summary endpoints.

FR-3.5: Anomaly feed — returns detected cost anomalies for the dashboard
and the dedicated Anomalies page.

Endpoints:
  GET  /anomalies/          — paginated anomaly list with optional filters
  GET  /anomalies/summary   — aggregate counts for the dashboard widget
  POST /anomalies/{id}/resolve — mark a single anomaly as resolved
"""

from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from services.anomaly_detector import (
    get_anomalies, get_anomaly_summary,
    detect_anomalies,
)
from services.security import get_current_user
from models.user import User
from models.account import AWSAccount
from models.anomaly import Anomaly

router = APIRouter(prefix="/anomalies", tags=["Anomalies"])


# ── Shared helper ────────────────────────────────────────────────

def _account_ids(
    db: Session,
    current_user: User,
    account_id: Optional[str],
) -> List[str]:
    if account_id:
        acc = db.query(AWSAccount).filter(
            AWSAccount.id == account_id,
            AWSAccount.user_id == current_user.id,
        ).first()
        if not acc:
            raise HTTPException(status_code=403, detail="Account not found or access denied")
        return [account_id]
    accounts = db.query(AWSAccount).filter(AWSAccount.user_id == current_user.id).all()
    return [a.id for a in accounts]


def _anomaly_to_dict(a: Anomaly) -> dict:
    return {
        "id":             a.id,
        "account_id":     a.account_id,
        "service_type":   a.service_type,
        "record_date":    str(a.record_date),
        "actual_cost":    round(a.actual_cost, 4),
        "forecast_cost":  round(a.forecast_cost, 4),
        "residual":       round(a.residual, 4),
        "deviation_pct":  round(
            abs(a.residual / a.forecast_cost * 100) if a.forecast_cost else 0.0, 1
        ),
        "z_score":        round(a.z_score, 3),
        "iqr_flagged":    a.iqr_flagged,
        "severity":       a.severity,
        "direction":      a.direction,
        "driver_service": a.driver_service,
        "is_resolved":    a.is_resolved,
        "resolved_at":    a.resolved_at.isoformat() if a.resolved_at else None,
        "created_at":     a.created_at.isoformat() if a.created_at else None,
    }


# ── Routes ───────────────────────────────────────────────────────

@router.get("/")
def list_anomalies(
    account_id:       Optional[str] = Query(None),
    days:             int            = Query(30,  ge=1,  le=365),
    severity:         Optional[str]  = Query(None, description="warning | critical"),
    include_resolved: bool           = Query(False),
    current_user:     User           = Depends(get_current_user),
    db:               Session        = Depends(get_db),
):
    """
    FR-3: Return anomalies for the current user's accounts.

    Filters:
      days             — look-back window (default 30)
      severity         — 'warning' | 'critical' | None (both)
      include_resolved — include user-dismissed anomalies (default False)
    """
    if severity and severity not in ("warning", "critical"):
        raise HTTPException(status_code=400, detail="severity must be 'warning' or 'critical'")

    ids   = _account_ids(db, current_user, account_id)
    rows  = get_anomalies(db, ids, days=days, severity=severity,
                          include_resolved=include_resolved)

    warning_count  = sum(1 for r in rows if r.severity == "warning")
    critical_count = sum(1 for r in rows if r.severity == "critical")

    return {
        "anomalies":     [_anomaly_to_dict(a) for a in rows],
        "total":         len(rows),
        "warning_count": warning_count,
        "critical_count":critical_count,
        "window_days":   days,
    }


@router.get("/summary")
def anomaly_summary(
    account_id:   Optional[str] = Query(None),
    days:         int            = Query(30, ge=1, le=365),
    current_user: User           = Depends(get_current_user),
    db:           Session        = Depends(get_db),
):
    """
    FR-3.5: Compact summary for the dashboard anomaly widget.

    Returns: total, warning_count, critical_count, top_driver, recent_critical[5]
    """
    ids = _account_ids(db, current_user, account_id)
    return get_anomaly_summary(db, ids, days=days)


@router.post("/{anomaly_id}/resolve")
def resolve_anomaly(
    anomaly_id:   str,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Mark a single anomaly as resolved (user-dismissed).

    Once resolved, the detection cycle will NOT flip this back to
    is_resolved=False even if the same spike recurs. See the
    resolution contract in models/anomaly.py.
    """
    # Verify ownership
    anomaly = db.query(Anomaly).filter(Anomaly.id == anomaly_id).first()
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found")

    # Verify the anomaly belongs to one of this user's accounts
    user_account_ids = [
        a.id for a in db.query(AWSAccount)
        .filter(AWSAccount.user_id == current_user.id).all()
    ]
    if anomaly.account_id not in user_account_ids:
        raise HTTPException(status_code=403, detail="Access denied")

    if anomaly.is_resolved:
        return {"message": "Already resolved", "id": anomaly_id}

    anomaly.is_resolved = True
    anomaly.resolved_at = datetime.utcnow()
    db.commit()

    return {"message": "Anomaly resolved", "id": anomaly_id}


@router.post("/refresh")
def refresh_anomalies(
    account_id:   Optional[str] = Query(None),
    current_user: User           = Depends(get_current_user),
    db:           Session        = Depends(get_db),
):
    """
    Manually trigger anomaly re-detection for the current user's accounts.
    (The scheduler does this automatically every 6 hours.)
    """
    ids    = _account_ids(db, current_user, account_id)
    totals = detect_anomalies(db, ids)
    return {
        "message":      "Anomaly detection complete",
        "per_account":  {k[:8]: v for k, v in totals.items()},
        "total_upserted": sum(totals.values()),
    }
