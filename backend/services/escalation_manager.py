import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from models.remediation import EscalationState
from models.cost_record import Recommendation
from models.account import CloudAccount
from models.anomaly import Anomaly
from services.remediation_executor import execute_remediation

logger = logging.getLogger(__name__)

def process_escalations(db: Session):
    """
    Evaluates all pending/escalated stop recommendations.
    If grace period expired and not anomalous, triggers execution.
    """
    now = datetime.utcnow()
    active_escalations = db.query(EscalationState).filter(
        EscalationState.status.in_(["pending", "escalated"])
    ).all()
    
    count_executed = 0
    
    for esc in active_escalations:
        import uuid
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
        
        # Check if due for execution
        if now >= esc.due_at:
            # Check FR-7.8 Opt-Out
            if (account and not account.auto_remediate_enabled) or rec.ignore_remediation:
                esc.status = "cancelled"
                logger.info(f"Escalation {esc.id} cancelled (auto-remediation opted out).")
                continue
                
            # Check FR-7.6 Anomaly Exclusion
            cutoff = datetime.utcnow() - timedelta(days=14)
            recent_anomaly = db.query(Anomaly).filter(
                Anomaly.account_id == rec.account_id,
                Anomaly.record_date >= cutoff.date(),
                Anomaly.is_resolved == False,
                # The issue is we don't have resource-level anomalies, they are service-level.
                # So we exclude the stop if the service is anomalous.
                Anomaly.service_type == rec.service_type
            ).first()
            
            if recent_anomaly:
                # We skip execution, but we don't cancel it entirely? 
                # "shall be excluded from automatic stopping...". We'll just leave it pending/escalated.
                logger.info(f"Escalation {esc.id} deferred: Service {rec.service_type} has active anomaly.")
                continue
                
            # Execute
            esc.status = "resolved"
            rec.is_resolved = True
            rec.resolved_at = now
            
            execute_remediation(
                db=db,
                account_id=rec.account_id,
                resource_id=rec.resource_id,
                action_type="stop",
                before_state=f"Idle resource {rec.issue}",
                trigger_reason=f"Grace period {account.grace_period_hours}h expired without manual action"
            )
            count_executed += 1
            
    db.commit()
    logger.info(f"Processed escalations. Executed {count_executed} auto-stops.")

def process_auto_resizes(db: Session):
    """
    Executes resize recommendations (Underutilized EC2) immediately, bypassing escalation.
    """
    now = datetime.utcnow()
    # Find all active resize recommendations
    active_resizes = db.query(Recommendation).filter(
        Recommendation.remediation_type == "resize",
        Recommendation.is_resolved == False
    ).all()
    
    count_executed = 0
    for rec in active_resizes:
        account = db.query(CloudAccount).filter(CloudAccount.id == rec.account_id).first()
        if (account and not account.auto_remediate_enabled) or rec.ignore_remediation:
            continue
            
        rec.is_resolved = True
        rec.resolved_at = now
        
        execute_remediation(
            db=db,
            account_id=rec.account_id,
            resource_id=rec.resource_id,
            action_type="resize",
            before_state=f"Underutilized resource {rec.issue}",
            trigger_reason="Auto-resize eligible (Immediate)"
        )
        count_executed += 1
        
    db.commit()
    logger.info(f"Processed auto-resizes. Executed {count_executed}.")
