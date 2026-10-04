import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey
from database import Base

class EscalationState(Base):
    __tablename__ = "escalation_states"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    recommendation_id = Column(String(36), ForeignKey("recommendations.id"), nullable=False, unique=True)
    status = Column(String(50), default="pending")  # pending, escalated, resolved, cancelled
    due_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class RemediationLog(Base):
    __tablename__ = "remediation_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id = Column(String(36), ForeignKey("aws_accounts.id"), nullable=False)
    resource_id = Column(String(255), nullable=False)
    action_type = Column(String(50), nullable=False) # resize, stop
    status = Column(String(50), nullable=False) # simulated, executed, failed
    before_state = Column(String(255))
    after_state = Column(String(255))
    trigger_reason = Column(String(255))
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
