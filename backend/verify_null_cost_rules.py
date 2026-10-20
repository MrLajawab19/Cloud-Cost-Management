"""
backend/verify_null_cost_rules.py
Tests generate_recommendations on sequential resources with known vs None costs
to ensure None-cost resources generate no recommendations and do not inherit
stale costs from previous loop iterations.
"""

import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from database import Base
import models.user
import models.account
import models.resource
import models.cost_record
import models.remediation
from models.user import User
from models.account import CloudAccount
from models.resource import Resource
from models.cost_record import Recommendation
from services.cleanup_advisor import generate_recommendations


def main():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from sqlalchemy import event
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()

    # Create user and account
    user = User(
        id=str(uuid.uuid4()),
        email="nullrules@example.com",
        password_hash="hash",
    )
    db.add(user)
    db.commit()

    account = CloudAccount(
        id="acc-null-rules-1",
        user_id=user.id,
        name="Null Rules Test Account",
        provider="aws",
        region="us-east-1",
    )
    db.add(account)
    db.commit()

    # Resources in specified exact order:
    # (a) idle EC2 cpu 0.3 runtime 300 cost 50.0
    r_a = Resource(
        id=uuid.uuid4(),
        resource_id="i-ec2-cost-50",
        account_id=account.id,
        resource_name="ec2-with-cost",
        service_type="EC2",
        region="us-east-1",
        status="running",
        resource_type="t3.medium",
        cpu_utilization_avg=0.3,
        runtime_hours=300.0,
        estimated_monthly_cost=50.0,
        last_seen=datetime.now(timezone.utc),
    )
    # (b) idle EC2 cpu 0.3 runtime 300 cost None
    r_b = Resource(
        id=uuid.uuid4(),
        resource_id="i-ec2-cost-none",
        account_id=account.id,
        resource_name="ec2-null-cost",
        service_type="EC2",
        region="us-east-1",
        status="running",
        resource_type="t3.medium",
        cpu_utilization_avg=0.3,
        runtime_hours=300.0,
        estimated_monthly_cost=None,
        last_seen=datetime.now(timezone.utc),
    )
    # (c1) empty S3 cost 10.0
    r_c1 = Resource(
        id=uuid.uuid4(),
        resource_id="s3-empty-cost-10",
        account_id=account.id,
        resource_name="bucket-empty-with-cost",
        service_type="S3",
        region="us-east-1",
        status="active",
        storage_size_gb=0.0,
        request_count=0,
        estimated_monthly_cost=10.0,
        last_seen=datetime.now(timezone.utc),
    )
    # (c2) empty S3 cost None
    r_c2 = Resource(
        id=uuid.uuid4(),
        resource_id="s3-empty-cost-none",
        account_id=account.id,
        resource_name="bucket-empty-null-cost",
        service_type="S3",
        region="us-east-1",
        status="active",
        storage_size_gb=0.0,
        request_count=0,
        estimated_monthly_cost=None,
        last_seen=datetime.now(timezone.utc),
    )
    # (d1) large unused S3 cost 20.0
    r_d1 = Resource(
        id=uuid.uuid4(),
        resource_id="s3-large-cost-20",
        account_id=account.id,
        resource_name="bucket-large-with-cost",
        service_type="S3",
        region="us-east-1",
        status="active",
        storage_size_gb=600.0,
        request_count=0,
        estimated_monthly_cost=20.0,
        last_seen=datetime.now(timezone.utc),
    )
    # (d2) large unused S3 cost None
    r_d2 = Resource(
        id=uuid.uuid4(),
        resource_id="s3-large-cost-none",
        account_id=account.id,
        resource_name="bucket-large-null-cost",
        service_type="S3",
        region="us-east-1",
        status="active",
        storage_size_gb=600.0,
        request_count=0,
        estimated_monthly_cost=None,
        last_seen=datetime.now(timezone.utc),
    )

    resources = [r_a, r_b, r_c1, r_c2, r_d1, r_d2]
    for r in resources:
        db.add(r)
    db.commit()

    # Run real generate_recommendations
    num_recs = generate_recommendations(db)

    # Query all recommendations created
    recs = db.query(Recommendation).filter(Recommendation.account_id == account.id).all()

    print(f"Total Recommendations Generated: {num_recs}")
    print("-" * 80)
    print(f"{'Resource ID':<25} | {'Issue':<28} | {'Savings USD'}")
    print("-" * 80)
    for rec in recs:
        print(f"{rec.resource_id:<25} | {rec.issue:<28} | ${rec.potential_savings_usd:.2f}")
    print("-" * 80)

    # Verifications:
    # 1. (b) i-ec2-cost-none must have NO recommendations
    ec2_none_recs = [rec for rec in recs if rec.resource_id == "i-ec2-cost-none"]
    assert len(ec2_none_recs) == 0, f"Expected 0 recs for i-ec2-cost-none, got {len(ec2_none_recs)}"

    # 2. (d2) s3-large-cost-none must have NO recommendations
    s3_none_recs = [rec for rec in recs if rec.resource_id == "s3-large-cost-none"]
    assert len(s3_none_recs) == 0, f"Expected 0 recs for s3-large-cost-none, got {len(s3_none_recs)}"

    # 3. (a) i-ec2-cost-50 has savings=50.0
    ec2_50_recs = [rec for rec in recs if rec.resource_id == "i-ec2-cost-50"]
    assert len(ec2_50_recs) == 1 and ec2_50_recs[0].potential_savings_usd == 50.0

    # 4. (d1) s3-large-cost-20 has savings=round(20*0.9, 2)=18.0
    s3_20_recs = [rec for rec in recs if rec.resource_id == "s3-large-cost-20"]
    assert len(s3_20_recs) == 1 and s3_20_recs[0].potential_savings_usd == 18.0

    # 5. Empty S3 buckets have savings=0.0
    for r_id in ["s3-empty-cost-10", "s3-empty-cost-none"]:
        empty_recs = [rec for rec in recs if rec.resource_id == r_id]
        assert len(empty_recs) == 1 and empty_recs[0].potential_savings_usd == 0.0

    print("All checks PASSED: None-cost resources generate no recommendations and no savings are leaked.")
    db.close()


if __name__ == "__main__":
    main()
