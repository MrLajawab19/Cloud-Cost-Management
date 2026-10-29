import logging
import uuid
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from models.remediation import EscalationState
from models.cost_record import Recommendation, format_recommendation_id_fk
from models.account import CloudAccount
from models.anomaly import Anomaly

logger = logging.getLogger(__name__)

def check_anomaly_exclusion(db: Session, account_id: str, service_type: str):
    """
    FR-7.6: Checks if there is an active/unresolved anomaly for this service
    within the last 14 days.
    """
    cutoff = datetime.utcnow() - timedelta(days=14)
    return db.query(Anomaly).filter(
        Anomaly.account_id == account_id,
        Anomaly.record_date >= cutoff.date(),
        Anomaly.is_resolved == False,
        Anomaly.service_type == service_type
    ).first()

def process_escalations(db: Session):
    """
    Evaluates all pending/escalated stop recommendations.
    If grace period expired and not anomalous, the escalation becomes stage 'action_due'
    (guided reminder, no simulated stop log executed).
    """
    now = datetime.utcnow()
    active_escalations = db.query(EscalationState).filter(
        EscalationState.status.in_(["pending", "escalated"])
    ).all()
    
    count_due = 0
    
    for esc in active_escalations:
        try:
            rec_id_uuid = uuid.UUID(esc.recommendation_id)
        except ValueError:
            continue
            
        rec = db.query(Recommendation).filter(Recommendation.id == rec_id_uuid).first()
        
        # FR-7.5 Cancel if user resolved it manually
        if not rec or rec.is_resolved:
            esc.status = "cancelled"
            logger.info(f"Escalation {esc.id} cancelled (recommendation resolved or missing).")
            continue
            
        account = db.query(CloudAccount).filter(CloudAccount.id == rec.account_id).first()
        
        # Check if due
        if now >= esc.due_at:
            # Check FR-7.8 Opt-Out
            if (account and not account.auto_remediate_enabled) or rec.ignore_remediation:
                esc.status = "cancelled"
                logger.info(f"Escalation {esc.id} cancelled (remediation opted out).")
                continue
                
            # Check FR-7.6 Anomaly Exclusion
            recent_anomaly = check_anomaly_exclusion(db, rec.account_id, rec.service_type)
            if recent_anomaly:
                logger.info(f"Escalation {esc.id} deferred (HELD): Service {rec.service_type} has active anomaly.")
                continue
                
            # Transition to action_due: app never executes cloud actions or simulated stop logs
            esc.status = "action_due"
            count_due += 1
            
    db.commit()
    logger.info(f"Processed escalations. Transitioned {count_due} to action_due.")
    return count_due

def process_auto_resizes(db: Session):
    """
    Resize recommendations become a guided item immediately (status 'recommended')
    instead of a simulated resize.
    """
    now = datetime.utcnow()
    active_resizes = db.query(Recommendation).filter(
        Recommendation.remediation_type == "resize",
        Recommendation.is_resolved == False
    ).all()
    
    count_recommended = 0
    for rec in active_resizes:
        account = db.query(CloudAccount).filter(CloudAccount.id == rec.account_id).first()
        if (account and not account.auto_remediate_enabled) or rec.ignore_remediation:
            continue

        rec_fk = format_recommendation_id_fk(rec.id, db)
        esc = db.query(EscalationState).filter(
            (EscalationState.recommendation_id == rec_fk) |
            (EscalationState.recommendation_id == str(rec.id))
        ).first()

        if not esc:
            esc = EscalationState(
                id=str(uuid.uuid4()),
                recommendation_id=rec_fk,
                status="recommended",
                due_at=now
            )
            db.add(esc)
            count_recommended += 1
        elif esc.status == "pending":
            esc.status = "recommended"
        
    db.commit()
    logger.info(f"Processed guided resizes. Active recommended: {count_recommended}.")
    return count_recommended
