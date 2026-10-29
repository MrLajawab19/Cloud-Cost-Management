"""
routes/notifications.py — Notification events derived on-the-fly from existing database records.
Provides GET /notifications with ownership validation, deterministic IDs, severity classification,
and deep links into frontend routes.
"""

import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from models.account import CloudAccount
from models.anomaly import Anomaly
from models.cost_record import Recommendation, CostRecord, format_recommendation_id_fk
from models.remediation import EscalationState, RemediationLog
from services.security import get_current_user
from services.escalation_manager import check_anomaly_exclusion

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def get_user_account_ids(db: Session, current_user: User, account_id: Optional[str] = None) -> List[str]:
    """Ownership check matching /remediation/status. Returns list of authorized account IDs."""
    if account_id:
        acc = db.query(CloudAccount).filter(
            CloudAccount.id == account_id,
            CloudAccount.user_id == current_user.id
        ).first()
        if not acc:
            raise HTTPException(status_code=403, detail="Account not found or access denied")
        return [account_id]
    accounts = db.query(CloudAccount).filter(CloudAccount.user_id == current_user.id).all()
    return [acc.id for acc in accounts]


@router.get("")
@router.get("/")
def get_notifications(
    account_id: Optional[str] = Query(None, description="Filter by account ID"),
    limit: int = Query(30, ge=1, le=100, description="Max notifications to return"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Builds notification events on-the-fly from existing tables:
      - anomaly_detected (from anomalies)
      - recommendation_created (from recommendations)
      - guided_* (from remediation_logs)
      - escalation_action_due / escalation_held (from escalation_states)
      - demo_injected (from cost_records where source='demo_injected')
    Note: 'collection failed' is not persisted in the database and is skipped.
    Reset actions do not persist audit logs and are skipped.
    """
    account_ids = get_user_account_ids(db, current_user, account_id)
    if not account_ids:
        return []

    events = []
    now = datetime.utcnow()

    # 1. Anomaly Detected Events
    anomalies = (
        db.query(Anomaly)
        .filter(Anomaly.account_id.in_(account_ids))
        .order_by(Anomaly.created_at.desc() if hasattr(Anomaly, "created_at") else Anomaly.record_date.desc())
        .limit(limit * 2)
        .all()
    )
    for a in anomalies:
        sev = "critical" if (a.severity or "").lower() == "critical" else "warning"
        rec_dt = a.created_at if a.created_at else (
            datetime.combine(a.record_date, datetime.min.time()) if a.record_date else now
        )
        date_str = a.record_date.isoformat() if a.record_date else "recent"
        driver = a.driver_service or a.service_type or "Unknown"
        events.append({
            "id": f"anom_{a.id}",
            "type": "anomaly_detected",
            "severity": sev,
            "title": f"Cost Anomaly: {a.service_type}",
            "message": f"{sev.capitalize()} cost spike on {a.service_type} ({date_str}). Driver: {driver}.",
            "created_at": rec_dt.isoformat(),
            "link": "/anomalies",
            "account_id": a.account_id,
        })

    # 2. Recommendation Created Events (including Savings Plan / Reserved Instance)
    recs = (
        db.query(Recommendation)
        .filter(Recommendation.account_id.in_(account_ids))
        .order_by(Recommendation.created_at.desc())
        .limit(limit * 2)
        .all()
    )
    for r in recs:
        sev = "warning" if (r.severity or "").lower() in ["high", "critical"] else "info"
        res_name = r.resource_name or r.resource_id or "Resource"
        savings_text = f"Potential savings: ${r.potential_savings_usd:.2f}/mo" if (r.potential_savings_usd and r.potential_savings_usd > 0) else "Optimization available"
        link = "/savings-optimiser" if r.issue == "No Commitment" else "/recommendations"
        rec_dt = r.created_at or now
        events.append({
            "id": f"rec_{r.id}",
            "type": "recommendation_created",
            "severity": sev,
            "title": f"Recommendation: {r.issue}",
            "message": f"{res_name} ({r.service_type}): {r.action}. {savings_text}.",
            "created_at": rec_dt.isoformat(),
            "link": link,
            "account_id": r.account_id,
        })

    # 3. Guided Remediation Log Events
    logs = (
        db.query(RemediationLog)
        .filter(RemediationLog.account_id.in_(account_ids))
        .order_by(RemediationLog.timestamp.desc())
        .limit(limit * 2)
        .all()
    )
    for l in logs:
        # Include guided_* actions
        if l.status and l.status.startswith("guided_"):
            actor = current_user.email
            if l.before_state and "Actor: " in l.before_state:
                actor = l.before_state.split("Actor: ")[1].split(" |")[0].strip()

            action_name = l.status.replace("guided_", "").capitalize()
            action_type = (l.action_type or "Action").capitalize()
            res_id = l.resource_id or "Resource"
            events.append({
                "id": f"log_{l.id}",
                "type": l.status,
                "severity": "warning" if l.status == "guided_declined" else "info",
                "title": f"Remediation {action_name}",
                "message": f"{action_type} on {res_id} by {actor}. State: {l.after_state or l.trigger_reason or 'recorded'}.",
                "created_at": (l.timestamp or now).isoformat(),
                "link": "/recommendations",
                "account_id": l.account_id,
            })

    # 4. Escalation Action Due / Held Events
    # Map recommendations for foreign key join
    rec_by_fk = {}
    for r in recs:
        rec_by_fk[format_recommendation_id_fk(r.id, db)] = r
        rec_by_fk[str(r.id)] = r

    escalations = (
        db.query(EscalationState)
        .order_by(EscalationState.created_at.desc())
        .limit(limit * 2)
        .all()
    )
    for esc in escalations:
        rec = rec_by_fk.get(esc.recommendation_id)
        if not rec or rec.account_id not in account_ids:
            # Fallback UUID match
            try:
                esc_u = uuid.UUID(str(esc.recommendation_id))
                rec = next((r for r in recs if r.id == esc_u), None)
            except Exception:
                rec = None
        if not rec or rec.account_id not in account_ids or rec.is_resolved:
            continue

        is_past_due = now >= esc.due_at if esc.due_at else False
        anomaly = check_anomaly_exclusion(db, rec.account_id, rec.service_type) if is_past_due else None
        held = bool(is_past_due and anomaly is not None)

        res_desc = rec.resource_name or rec.resource_id or "Resource"
        if held:
            held_reason = f"Unresolved anomaly on {rec.service_type} within 14 days"
            events.append({
                "id": f"esc_held_{esc.id}",
                "type": "escalation_held",
                "severity": "warning",
                "title": "Remediation Action Held",
                "message": f"Action on {res_desc} held: {held_reason}.",
                "created_at": (esc.due_at or esc.created_at or now).isoformat(),
                "link": "/recommendations",
                "account_id": rec.account_id,
            })
        elif is_past_due or esc.status == "action_due":
            events.append({
                "id": f"esc_due_{esc.id}",
                "type": "escalation_action_due",
                "severity": "warning",
                "title": "Remediation Action Due",
                "message": f"Grace period expired for {res_desc} ({rec.issue}). Manual confirmation required.",
                "created_at": (esc.due_at or esc.created_at or now).isoformat(),
                "link": "/recommendations",
                "account_id": rec.account_id,
            })

    # 5. Injected Services from Live Data Lab (if derived from CostRecord source='demo_injected')
    injected_records = (
        db.query(
            CostRecord.service_type,
            CostRecord.account_id,
            func.min(CostRecord.created_at).label("min_created")
        )
        .filter(
            CostRecord.account_id.in_(account_ids),
            CostRecord.source == "demo_injected"
        )
        .group_by(CostRecord.service_type, CostRecord.account_id)
        .all()
    )
    for svc, acc_id, min_cr in injected_records:
        events.append({
            "id": f"injected_{acc_id}_{svc}",
            "type": "demo_injected",
            "severity": "info",
            "title": f"Live Data Lab: {svc} Injected",
            "message": f"Synthetic {svc} service with backfilled history injected for commitment evaluation.",
            "created_at": (min_cr or now).isoformat(),
            "link": "/savings-optimiser",
            "account_id": acc_id,
        })

    # Sort events newest first (deterministic)
    events.sort(key=lambda e: (e.get("created_at") or "", e.get("id") or ""), reverse=True)
    return events[:limit]

