"""
models/account.py - Represents an AWS Account added by a User.
"""

from sqlalchemy import Column, String, DateTime, ForeignKey
import uuid
from datetime import datetime

from database import Base

class AWSAccount(Base):
    __tablename__ = "aws_accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    name = Column(String(255), nullable=False)
    region = Column(String(50), nullable=False, default="us-east-1")
    
    # Credentials
    access_key_id = Column(String(255), nullable=False)
    encrypted_secret_key = Column(String(500), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<AWSAccount {self.name} ({self.region})>"
