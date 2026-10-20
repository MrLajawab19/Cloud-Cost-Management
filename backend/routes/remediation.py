"""
routes/remediation.py — GET /remediation/status endpoint.
Returns active escalations and historical remediation logs.
"""

import uuid
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from models.account import CloudAccount
from models.cost_record import Recommendation, format_recommendation_id_fk
from models.resource import Resource
from models.remediation import EscalationState, RemediationLog
from services.security import get_current_user
from services.escalation_manager import check_anomaly_exclusion, process_escalations
from services.cost_estimator import is_aws_real, is_azure_real

router = APIRouter(prefix="/remediation", tags=["Remediation"])


def get_user_account_ids(db: Session, current_user: User, account_id: Optional[str] = None) -> List[str]:
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


@router.get("/status")
def get_remediation_status(
    account_id: Optional[str] = Query(None, description="Filter by account ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns active escalations and audit logs for the specified or user accounts.
    """
    account_ids = get_user_account_ids(db, current_user, account_id)
    if not account_ids:
        return {"escalations": [], "logs": []}

    # Fetch recommendations for these accounts
    recs = db.query(Recommendation).filter(Recommendation.account_id.in_(account_ids)).all()
    rec_map = {}
    for r in recs:
        rec_map[str(r.id)] = r
        try:
            fk_fmt = format_recommendation_id_fk(r.id, db)
            rec_map[fk_fmt] = r
        except Exception:
            pass

    # All escalations
    all_escalations = db.query(EscalationState).all()
    now = datetime.utcnow()

    escalations_out = []
    for esc in all_escalations:
        rec = rec_map.get(esc.recommendation_id)
        if not rec:
            # Try UUID matching directly if string mismatch
            try:
                esc_u = uuid.UUID(esc.recommendation_id)
                for r in recs:
                    if r.id == esc_u:
                        rec = r
                        break
            except Exception:
                pass

        if not rec:
            continue

        is_past_due = now >= esc.due_at
        anomaly = check_anomaly_exclusion(db, rec.account_id, rec.service_type) if is_past_due else None
        held = bool(is_past_due and anomaly is not None)
        held_reason = (
            f"Unresolved anomaly on {rec.service_type} within 14 days"
            if held
            else None
        )

        hours_rem = round(max(0.0, (esc.due_at - now).total_seconds() / 3600.0), 2)

        escalations_out.append({
            "recommendation_id": str(rec.id),
            "resource_name": rec.resource_name,
            "issue": rec.issue,
            "stage": esc.status,
            "status": esc.status,
            "due_at": esc.due_at.isoformat() if esc.due_at else None,
            "hours_remaining": hours_rem,
            "held": held,
            "held_reason": held_reason,
        })

    # Logs
    logs = (
        db.query(RemediationLog)
        .filter(RemediationLog.account_id.in_(account_ids))
        .order_by(RemediationLog.timestamp.desc())
        .all()
    )

    # Cache resource names
    res_names = {
        r.resource_id: r.resource_name
        for r in db.query(Resource.resource_id, Resource.resource_name)
        .filter(Resource.account_id.in_(account_ids))
        .all()
    }

    logs_out = []
    for l in logs:
        res_name = res_names.get(l.resource_id, l.resource_id)
        logs_out.append({
            "created_at": l.timestamp.isoformat() if l.timestamp else None,
            "resource_name": res_name,
            "action_type": l.action_type,
            "status": l.status,
            "trigger_reason": l.trigger_reason,
            "before_state": l.before_state,
        })

    return {
        "escalations": escalations_out,
        "logs": logs_out,
    }


@router.post("/demo/fast-forward")
def demo_fast_forward(
    account_id: str = Query(..., description="Demo account ID to fast-forward"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Fast-forward pending escalations on a UUID5 demo account to mature immediately.
    Allowed only for UUID5 demo accounts with no credentials.
    """
    acc = db.query(CloudAccount).filter(CloudAccount.id == account_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")

    if str(acc.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    if is_aws_real(acc) or is_azure_real(acc):
        raise HTTPException(status_code=403, detail="Fast-forward not allowed on accounts with credentials")

    if acc.id == "00000000-0000-0000-0000-demoaccount01":
        raise HTTPException(status_code=403, detail="Fast-forward not allowed on legacy demo account")

    try:
        u_uuid = uuid.UUID(str(current_user.id))
        valid_demo_ids = {
            str(uuid.uuid5(u_uuid, "demo-aws")),
            str(uuid.uuid5(u_uuid, "demo-azure")),
        }
    except Exception:
        valid_demo_ids = set()

    if acc.id not in valid_demo_ids:
        raise HTTPException(status_code=403, detail="Fast-forward allowed only for UUID5 demo accounts")

    # Match recommendations for this account
    recs = db.query(Recommendation).filter(Recommendation.account_id == acc.id).all()
    rec_id_strs = set()
    for r in recs:
        rec_id_strs.add(str(r.id))
        try:
            rec_id_strs.add(format_recommendation_id_fk(r.id, db))
        except Exception:
            pass

    # Find pending escalations for this account
    all_pending = db.query(EscalationState).filter(
        EscalationState.status.in_(["pending", "escalated"])
    ).all()

    now = datetime.utcnow()
    fast_forwarded_count = 0
    for esc in all_pending:
        is_match = False
        if esc.recommendation_id in rec_id_strs:
            is_match = True
        else:
            try:
                if str(uuid.UUID(esc.recommendation_id)) in rec_id_strs:
                    is_match = True
            except Exception:
                pass

        if is_match:
            esc.due_at = now
            fast_forwarded_count += 1

    db.commit()

    # Call the real escalation-processing function once
    process_escalations(db)

    # Return the same JSON shape as GET /remediation/status plus a "processed" summary
    status_response = get_remediation_status(account_id=acc.id, current_user=current_user, db=db)
    status_response["processed"] = {
        "account_id": acc.id,
        "fast_forwarded_count": fast_forwarded_count,
        "executed_at": now.isoformat(),
    }
    return status_response
