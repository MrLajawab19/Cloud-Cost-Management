"""
models/resource.py — ORM model representing a cloud resource (EC2, S3, RDS, Lambda).
Each row is a snapshot of a resource's state at collection time.
"""

from datetime import datetime
from sqlalchemy import Column, String, Float, Boolean, DateTime, Text, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum

from database import Base


class ServiceType(str, enum.Enum):
    EC2 = "EC2"
    S3 = "S3"
    RDS = "RDS"
    LAMBDA = "Lambda"


class ResourceStatus(str, enum.Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    AVAILABLE = "available"
    IDLE = "idle"
    UNKNOWN = "unknown"


class Resource(Base):
    """
    Represents a single cloud resource discovered via AWS API.
    Updated on every collection cycle (upsert by resource_id).
    """
    __tablename__ = "resources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(String(36), ForeignKey("aws_accounts.id", ondelete="CASCADE"), nullable=False, index=True)

    # AWS identifiers
    resource_id   = Column(String(255), unique=True, nullable=False, index=True)
    resource_name = Column(String(255), nullable=True)
    service_type  = Column(String(50),  nullable=False, index=True)   # EC2 | S3 | RDS | Lambda
    region        = Column(String(50),  nullable=False)

    # State
    status        = Column(String(50),  default="unknown")
    resource_type = Column(String(100), nullable=True)   # e.g. "t3.micro" for EC2
    tags          = Column(Text, nullable=True)           # JSON string of AWS tags

    # Usage metrics (updated each collection)
    cpu_utilization_avg    = Column(Float, nullable=True)   # % — EC2 only
    memory_utilization_avg = Column(Float, nullable=True)   # % — EC2 (if CloudWatch agent)
    storage_size_gb        = Column(Float, nullable=True)   # S3 bucket size / RDS storage
    request_count          = Column(Float, nullable=True)   # S3 requests / Lambda invocations
    runtime_hours          = Column(Float, nullable=True)   # EC2/RDS uptime hours

    # Cost
    estimated_monthly_cost = Column(Float, default=0.0)     # USD

    # Flags
    is_idle     = Column(Boolean, default=False)
    is_flagged  = Column(Boolean, default=False)   # Flagged for cleanup review

    # Timestamps
    launch_time  = Column(DateTime, nullable=True)
    last_seen    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at   = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Resource {self.service_type}:{self.resource_id} status={self.status}>"
