"""
verify_collection_resilience.py
─────────────────────────────────
Verifies that failed cloud collections do not delete existing inventory.
Tests 4 cases in an in-memory SQLite database:
  (1) Azure collector raises CollectionFailed -> existing rows unchanged, still present
  (2) Azure returns [] successfully -> rows cleared
  (3) AWS with Lambda in failed_services -> existing Lambda rows preserved, EC2 rows replaced
  (4) AWS credential failure (CollectionFailed) -> nothing deleted
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timezone

from database import Base
import scheduler
from services import aws_collector, azure_collector
from services.exceptions import CollectionFailed
from models.user import User
from models.account import CloudAccount
from models.resource import Resource
from services.security import encrypt_secret


def setup_in_memory_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return engine, Session


def main():
    print("=" * 60)
    print("RUNNING COLLECTION RESILIENCE VERIFICATION")
    print("=" * 60)

    engine, Session = setup_in_memory_db()

    # Monkeypatch scheduler SessionLocal
    scheduler.SessionLocal = Session

    db = Session()

    # Create dummy user
    user = User(id="user-resilience-1", email="resilience@example.com", password_hash="dummy")
    db.add(user)
    db.commit()
    db.refresh(user)

    # Create dummy accounts
    acc_azure = CloudAccount(
        id="acc-azure-resilience",
        user_id=user.id,
        name="Azure Test Account",
        provider="azure",
        region="eastus",
        tenant_id="dummy-tenant",
        client_id="dummy-client",
        encrypted_client_secret=encrypt_secret("dummy-secret"),
        subscription_id="sub-12345",
    )
    acc_aws = CloudAccount(
        id="acc-aws-resilience",
        user_id=user.id,
        name="AWS Test Account",
        provider="aws",
        region="us-east-1",
        access_key_id="AKIA_DUMMY",
        encrypted_secret_key=encrypt_secret("dummy-secret"),
    )
    db.add(acc_azure)
    db.add(acc_aws)
    db.commit()

    # ─────────────────────────────────────────────────────────────
    # CASE 1: Azure collector raises CollectionFailed
    # ─────────────────────────────────────────────────────────────
    print("\n--- CASE 1: Azure collector raises CollectionFailed ---")
    # Seed 2 Azure VM rows
    vm1 = Resource(
        resource_id="/subscriptions/sub-12345/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1",
        account_id=acc_azure.id,
        resource_name="rg/vm-1",
        service_type="AzureVM",
        region="eastus",
        status="running",
        last_seen=datetime.now(timezone.utc),
    )
    vm2 = Resource(
        resource_id="/subscriptions/sub-12345/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-2",
        account_id=acc_azure.id,
        resource_name="rg/vm-2",
        service_type="AzureVM",
        region="eastus",
        status="running",
        last_seen=datetime.now(timezone.utc),
    )
    db.add(vm1)
    db.add(vm2)
    db.commit()

    count_before = db.query(Resource).filter(Resource.account_id == acc_azure.id).count()
    print(f"Row count before collection: {count_before}")

    def mock_azure_raises(*args, **kwargs):
        raise CollectionFailed("Simulated Azure Auth/Listing Error")

    azure_collector.collect_all = mock_azure_raises

    scheduler.run_collection_pipeline(user_id=user.id, account_id=acc_azure.id)

    count_after = db.query(Resource).filter(Resource.account_id == acc_azure.id).count()
    print(f"Row count after collection:  {count_after}")
    assert count_after == count_before == 2, f"Expected 2 rows preserved, got {count_after}"
    print("Result: PASS (Azure collector raised -> existing rows for account unchanged)")

    # ─────────────────────────────────────────────────────────────
    # CASE 2: Azure returns [] successfully
    # ─────────────────────────────────────────────────────────────
    print("\n--- CASE 2: Azure returns [] successfully ---")
    count_before = db.query(Resource).filter(Resource.account_id == acc_azure.id).count()
    print(f"Row count before collection: {count_before}")

    def mock_azure_empty(*args, **kwargs):
        return []

    azure_collector.collect_all = mock_azure_empty

    scheduler.run_collection_pipeline(user_id=user.id, account_id=acc_azure.id)

    count_after = db.query(Resource).filter(Resource.account_id == acc_azure.id).count()
    print(f"Row count after collection:  {count_after}")
    assert count_after == 0, f"Expected 0 rows (cleared), got {count_after}"
    print("Result: PASS (Azure returned [] successfully -> rows cleared)")

    # ─────────────────────────────────────────────────────────────
    # CASE 3: AWS with Lambda in failed_services
    # ─────────────────────────────────────────────────────────────
    print("\n--- CASE 3: AWS with Lambda in failed_services ---")
    # Seed 1 EC2 row and 1 Lambda row
    ec2_old = Resource(
        resource_id="i-old-ec2",
        account_id=acc_aws.id,
        resource_name="old-ec2",
        service_type="EC2",
        region="us-east-1",
        status="running",
        last_seen=datetime.now(timezone.utc),
    )
    lambda_existing = Resource(
        resource_id="arn:aws:lambda:us-east-1:123456789012:function:my-func",
        account_id=acc_aws.id,
        resource_name="my-func",
        service_type="Lambda",
        region="us-east-1",
        status="active",
        last_seen=datetime.now(timezone.utc),
    )
    db.add(ec2_old)
    db.add(lambda_existing)
    db.commit()

    count_before_ec2 = db.query(Resource).filter(Resource.account_id == acc_aws.id, Resource.service_type == "EC2").count()
    count_before_lam = db.query(Resource).filter(Resource.account_id == acc_aws.id, Resource.service_type == "Lambda").count()
    count_before_tot = db.query(Resource).filter(Resource.account_id == acc_aws.id).count()
    print(f"Row count before collection: Total={count_before_tot} (EC2={count_before_ec2}, Lambda={count_before_lam})")

    def mock_aws_partial(*args, **kwargs):
        # EC2 returned a new instance; Lambda collection failed
        return [
            {
                "account_id": acc_aws.id,
                "resource_id": "i-new-ec2",
                "resource_name": "new-ec2",
                "service_type": "EC2",
                "region": "us-east-1",
                "status": "running",
            }
        ], ["Lambda"]

    aws_collector.collect_all = mock_aws_partial

    scheduler.run_collection_pipeline(user_id=user.id, account_id=acc_aws.id)

    count_after_ec2 = db.query(Resource).filter(Resource.account_id == acc_aws.id, Resource.service_type == "EC2").count()
    count_after_lam = db.query(Resource).filter(Resource.account_id == acc_aws.id, Resource.service_type == "Lambda").count()
    count_after_tot = db.query(Resource).filter(Resource.account_id == acc_aws.id).count()

    # Check that i-new-ec2 is present and i-old-ec2 is gone
    ec2_new = db.query(Resource).filter(Resource.resource_id == "i-new-ec2").first()
    ec2_old_check = db.query(Resource).filter(Resource.resource_id == "i-old-ec2").first()
    lam_check = db.query(Resource).filter(Resource.resource_id == "arn:aws:lambda:us-east-1:123456789012:function:my-func").first()

    print(f"Row count after collection:  Total={count_after_tot} (EC2={count_after_ec2}, Lambda={count_after_lam})")
    assert ec2_new is not None, "i-new-ec2 should be present"
    assert ec2_old_check is None, "i-old-ec2 should be deleted as stale"
    assert lam_check is not None, "my-func Lambda should be preserved because Lambda failed"
    print("Result: PASS (Lambda in failed_services -> Lambda preserved, EC2 replaced normally)")

    # ─────────────────────────────────────────────────────────────
    # CASE 4: AWS credential failure
    # ─────────────────────────────────────────────────────────────
    print("\n--- CASE 4: AWS credential failure ---")
    count_before = db.query(Resource).filter(Resource.account_id == acc_aws.id).count()
    print(f"Row count before collection: {count_before}")

    def mock_aws_cred_failure(*args, **kwargs):
        raise CollectionFailed("Simulated STS Auth / Invalid Credentials")

    aws_collector.collect_all = mock_aws_cred_failure

    scheduler.run_collection_pipeline(user_id=user.id, account_id=acc_aws.id)

    count_after = db.query(Resource).filter(Resource.account_id == acc_aws.id).count()
    print(f"Row count after collection:  {count_after}")
    assert count_after == count_before, f"Expected nothing deleted ({count_before} rows), got {count_after}"
    print("Result: PASS (AWS credential failure -> nothing deleted)")

    print("\nAll 4 resilience test cases PASSED successfully.")
    db.close()


if __name__ == "__main__":
    main()
