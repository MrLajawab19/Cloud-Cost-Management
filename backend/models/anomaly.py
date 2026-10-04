"""
models/anomaly.py — Anomaly detection results (FR-3).

One row = one anomaly event: a (account, service, date) triple where
the actual daily cost deviated from the FR-2 forecast by ≥ 2.5 σ.

Severity levels stored:
  'warning'  — 2.5 ≤ |z| < 3.5
  'critical' — |z| ≥ 3.5

Rows with |z| < 2.5 are never written to this table.
"""

from datetime import datetime
from sqlalchemy import Column, Float, DateTime, Date, String, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
import uuid

from database import Base


class Anomaly(Base):
    """
    One anomaly = one (account, service, date) combination where the
    actual daily cost exceeded the Z-score threshold derived from the
    FR-2 forecast residuals.

    Resolution contract
    ───────────────────
    Once is_resolved is set to True by a user action, the detection
    cycle MUST NOT flip it back to False — even if the same
    account+service+date still shows a residual spike on a later run.
    The upsert logic in anomaly_detector.py enforces this by skipping
    any existing row whose is_resolved=True.

    FR-6.4 and FR-7.6 depend on is_resolved to gate the Savings
    Optimizer and auto-stop remediation, so resurrection would silently
    corrupt their inputs.
    """

    __tablename__ = "anomalies"

    # Composite uniqueness: one anomaly record per account+service+date.
    # The UniqueConstraint drives the upsert key in the detector.
    __table_args__ = (
        UniqueConstraint("account_id", "service_type", "record_date",
                         name="uq_anomaly_account_service_date"),
    )

    id             = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id     = Column(String(36), ForeignKey("cloud_accounts.id", ondelete="CASCADE"),
                            nullable=False, index=True)

    service_type   = Column(String(50),  nullable=False, index=True)  # EC2|RDS|S3|Lambda|TOTAL
    record_date    = Column(Date,         nullable=False, index=True)  # the date that spiked

    # Cost values on the anomalous day
    actual_cost    = Column(Float, nullable=False)    # raw daily_cost_usd
    forecast_cost  = Column(Float, nullable=False)    # what FR-2 predicted for this day
    residual       = Column(Float, nullable=False)    # actual − forecast

    # Detection statistics
    z_score        = Column(Float, nullable=False)    # residual / rolling_std
    iqr_flagged    = Column(Boolean, default=False)   # True if IQR check also triggered

    # Classification
    severity       = Column(String(20), nullable=False)   # 'warning' | 'critical'
    direction      = Column(String(10), nullable=False)   # 'spike' | 'drop'

    # Attribution: which service drove this anomaly (shared with FR-2.4 attribution)
    driver_service = Column(String(50), nullable=True)    # service name from attribution helper

    # Resolution state — see docstring above for the immutability contract
    is_resolved    = Column(Boolean, default=False, nullable=False, index=True)
    resolved_at    = Column(DateTime, nullable=True)

    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return (
            f"<Anomaly {self.service_type} {self.record_date} "
            f"z={self.z_score:.2f} [{self.severity}] resolved={self.is_resolved}>"
        )
