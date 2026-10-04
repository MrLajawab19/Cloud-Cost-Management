"""
models/account.py - Unified cloud account model (AWS and Azure).

Implements Option A from the FR-1 design decision: a single CloudAccount table
with a provider enum and provider-specific nullable credential fields.

AWS accounts use:  access_key_id (plaintext) + encrypted_secret_key (Fernet)
Azure accounts use: tenant_id (plaintext) + client_id (plaintext)
                    + encrypted_client_secret (Fernet) + subscription_id (plaintext)

FR-7 remediation fields (auto_remediate_enabled, grace_period_hours, etc.) apply
to AWS accounts only. AzureVM resources are explicitly excluded from FR-7
remediation in this phase -- see escalation_manager.py and cleanup_advisor.py.
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Float, Integer
import uuid
from datetime import datetime

from database import Base


class CloudAccount(Base):
    """
    One row = one cloud account added by a user.
    provider = 'aws'   -> AWS IAM access key credentials
    provider = 'azure' -> Azure Service Principal credentials
    """
    __tablename__ = "cloud_accounts"

    id      = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)

    name     = Column(String(255), nullable=False)
    region   = Column(String(50),  nullable=False, default="us-east-1")
    provider = Column(String(10),  nullable=False, default="aws")  # 'aws' | 'azure'

    # AWS credentials (nullable for Azure accounts)
    access_key_id        = Column(String(255), nullable=True)  # plaintext
    encrypted_secret_key = Column(String(500), nullable=True)  # Fernet-encrypted

    # Azure credentials (nullable for AWS accounts)
    tenant_id               = Column(String(255), nullable=True)  # plaintext
    client_id               = Column(String(255), nullable=True)  # plaintext
    encrypted_client_secret = Column(String(500), nullable=True)  # Fernet-encrypted
    subscription_id         = Column(String(255), nullable=True)  # plaintext

    # FR-7 automated remediation settings
    # Note: remediation applies to AWS EC2 resources only in this phase.
    # AzureVM resources are explicitly excluded -- see FR-7 SRS note.
    auto_remediate_enabled = Column(Boolean, default=False)
    budget_threshold_usd   = Column(Float,   nullable=True)
    grace_period_hours     = Column(Integer,  default=48)

    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<CloudAccount [{self.provider.upper()}] {self.name} ({self.region})>"


# Backward-compatibility alias: any file that still imports AWSAccount by name
# continues to work without modification. Remove after all references are updated.
AWSAccount = CloudAccount
