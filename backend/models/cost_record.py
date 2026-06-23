"""
models/cost_record.py — Daily cost snapshot per resource, and cleanup recommendations.
Used for historical trend charts, ML training data, and client-facing recommendations.
"""

from datetime import datetime
from sqlalchemy import Column, Float, DateTime, Date, String, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID
import uuid

from database import Base


class CostRecord(Base):
    """
    One record = one day of cost for one resource (or one service aggregate).
    The ML predictor is trained on this table.
    """
    __tablename__ = "cost_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Link back to a specific resource (nullable for service-level aggregates)
    resource_id   = Column(String(255), nullable=True, index=True)
    service_type  = Column(String(50),  nullable=False, index=True)
    region        = Column(String(50),  nullable=False)

    # Cost data
    record_date      = Column(Date,  nullable=False, index=True)
    daily_cost_usd   = Column(Float, nullable=False, default=0.0)
    monthly_estimate = Column(Float, nullable=True)   # Projected from daily rate

    # Raw usage at snapshot time
    usage_quantity = Column(Float, nullable=True)
    usage_unit     = Column(String(50), nullable=True)   # e.g. "hours", "GB-Month"

    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<CostRecord {self.service_type} {self.record_date} ${self.daily_cost_usd:.4f}>"


class Recommendation(Base):
    """
    A cleanup or optimization recommendation for a specific resource.
    Regenerated on every collection cycle.
    """
    __tablename__ = "recommendations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    resource_id    = Column(String(255), nullable=False, index=True)
    resource_name  = Column(String(255), nullable=True)
    service_type   = Column(String(50),  nullable=False)
    region         = Column(String(50),  nullable=False)

    # Recommendation detail
    issue          = Column(String(255), nullable=False)   # Short one-line title
    description    = Column(Text, nullable=False)          # Full explanation
    action         = Column(String(255), nullable=False)   # What the user should do
    severity       = Column(String(20),  default="medium") # low | medium | high | critical
    potential_savings_usd = Column(Float, default=0.0)

    is_resolved = Column(Boolean, default=False)
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Recommendation {self.resource_id} [{self.severity}] {self.issue}>"
