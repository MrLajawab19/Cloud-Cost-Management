import logging
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from models.remediation import RemediationLog
from models.account import CloudAccount

logger = logging.getLogger(__name__)

def execute_remediation(db: Session, account_id: str, resource_id: str, action_type: str, before_state: str, trigger_reason: str):
    """
    Executes a remediation action with a strict safety guard:
    Remediation is simulated-only for all accounts (real or demo).
    """
    account = db.query(CloudAccount).filter(CloudAccount.id == account_id).first()
    if not account:
        logger.error(f"Account {account_id} not found for remediation.")
        return

    status = "simulated"
    after_state = f"{action_type} executed (simulated)"
    
    log_entry = RemediationLog(
        id=str(uuid.uuid4()),
        account_id=account_id,
        resource_id=resource_id,
        action_type=action_type,
        status=status,
        before_state=before_state,
        after_state=after_state,
        trigger_reason=trigger_reason,
        timestamp=datetime.utcnow()
    )
    db.add(log_entry)
    db.commit()
    logger.info(f"Remediation Logged: [{status}] {action_type} for {resource_id}.")
