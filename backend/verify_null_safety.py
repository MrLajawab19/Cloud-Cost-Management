"""
backend/verify_null_safety.py
In-memory SQLite + TestClient + valid JWT verification for null cost safety across
endpoints, simulations, savings plan generation, and remediation/escalation paths.
"""

import sys
import uuid
from pathlib import Path

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timezone, timedelta

from database import Base, get_db
from main import app
from models.user import User
from models.account import CloudAccount
from models.resource import Resource
from models.cost_record import Recommendation
from models.remediation import EscalationState
from services.security import get_password_hash, create_access_token
from services.savings_plan_optimiser import generate_sp_recommendations
from services.remediation_executor import execute_remediation
from services.escalation_manager import process_escalations

# In-memory SQLite with StaticPool so all connections share the same in-memory DB
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


def main():
    db = TestingSessionLocal()

    # 1. User
    user = User(
        id=str(uuid.uuid4()),
        email="nullsafety@example.com",
        password_hash=get_password_hash("password123"),
    )
    db.add(user)
    db.commit()
    user_id = user.id

    # 2. Cloud Accounts (AWS and Azure)
    acc_aws = CloudAccount(
        id="acc-aws-null-1",
        user_id=user.id,
        name="AWS Test Account",
        provider="aws",
        region="us-east-1",
        auto_remediate_enabled=True,
    )
    acc_azure = CloudAccount(
        id="acc-azure-null-1",
        user_id=user.id,
        name="Azure Test Account",
        provider="azure",
        region="eastus",
        auto_remediate_enabled=False,
    )
    db.add(acc_aws)
    db.add(acc_azure)
    db.commit()

    # 3. Resources with estimated_monthly_cost = None
    res_aws = Resource(
        resource_id="i-test-null-ec2",
        account_id=acc_aws.id,
        resource_name="null-ec2",
        service_type="EC2",
        region="us-east-1",
        status="running",
        resource_type="t3.medium",
        cpu_utilization_avg=0.5,
        storage_size_gb=20.0,
        runtime_hours=200.0,
        estimated_monthly_cost=None,
        is_idle=True,
        is_flagged=False,
        launch_time=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
    )
    res_azure = Resource(
        resource_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/null-vm",
        account_id=acc_azure.id,
        resource_name="rg/null-vm",
        service_type="AzureVM",
        region="eastus",
        status="running",
        resource_type="Standard_B2s",
        cpu_utilization_avg=0.2,
        storage_size_gb=30.0,
        runtime_hours=200.0,
        estimated_monthly_cost=None,
        is_idle=True,
        is_flagged=False,
        launch_time=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
    )
    db.add(res_aws)
    db.add(res_azure)
    db.commit()

    # 4. Recommendation for simulation & escalation
    rec_id = uuid.uuid4()
    rec = Recommendation(
        id=rec_id,
        account_id=acc_aws.id,
        resource_id=res_aws.resource_id,
        resource_name=res_aws.resource_name,
        service_type="EC2",
        region="us-east-1",
        issue="Idle EC2 instance",
        description="Stop idle EC2 instance",
        action="Stop instance",
        remediation_type="stop",
        potential_savings_usd=30.0,
        severity="medium",
        is_resolved=False,
    )
    db.add(rec)
    db.commit()

    # 5. Escalation State for escalation path
    esc = EscalationState(
        id=str(uuid.uuid4()),
        recommendation_id=rec.id.hex,
        status="pending",
        due_at=datetime.utcnow() - timedelta(hours=1),  # already due
    )
    db.add(esc)
    db.commit()

    print("=== TESTING SERVICES DIRECTLY WITH NULL COSTS ===")
    # A. Savings-plan generation path
    sp_aws = generate_sp_recommendations(db, acc_aws.id)
    sp_azure = generate_sp_recommendations(db, acc_azure.id)
    print(f"Savings plan generation: AWS={len(sp_aws)} recs, Azure={len(sp_azure)} recs (OK)")

    # B. Remediation executor path
    execute_remediation(
        db,
        account_id=acc_aws.id,
        resource_id=res_aws.resource_id,
        action_type="stop",
        before_state="running",
        trigger_reason="Test null cost execution",
    )
    print("Remediation execution path: OK")

    # C. Escalation manager path
    process_escalations(db)
    print("Escalation processing path: OK")

    db.close()

    # 6. TestClient endpoint verification with valid JWT
    token = create_access_token(data={"sub": user_id})
    headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(app)

    endpoints = [
        ("GET", "/resources/"),
        ("GET", "/costs/summary"),
        ("GET", "/costs/trend"),
        ("GET", "/costs/by-service"),
        ("GET", "/costs/top-resources"),
        ("GET", "/recommendations/"),
        ("GET", "/recommendations/summary"),
        ("GET", "/predictions/"),
        ("GET", "/predictions/per-service"),
        ("GET", "/anomalies/"),
        ("GET", "/anomalies/summary"),
        ("GET", f"/simulations/{rec_id}"),
        ("POST", "/simulations/batch", {"ids": [str(rec_id)]}),
    ]

    print("\n=== NULL-COST ENDPOINT VERIFICATION ===")
    all_passed = True
    for item in endpoints:
        method = item[0]
        ep = item[1]
        json_body = item[2] if len(item) > 2 else None

        if json_body:
            resp = client.request(method, ep, json=json_body, headers=headers)
        else:
            resp = client.request(method, ep, headers=headers)

        status = resp.status_code
        print(f"[{method:4}] {ep:45} -> status: {status}")
        if status >= 500 or (status != 200 and method == "GET"):
            all_passed = False
            print("  Body:", resp.text)

        # Check /costs/summary specifically
        if ep == "/costs/summary":
            data = resp.json()
            print(f"       /costs/summary response: total={data.get('total_monthly_cost_usd')}, unknown={data.get('unknown_cost_resources')}")
            assert data.get("total_monthly_cost_usd") is None, f"Expected total_monthly_cost_usd=None, got {data.get('total_monthly_cost_usd')}"
            assert data.get("unknown_cost_resources") == 2, f"Expected unknown_cost_resources=2, got {data.get('unknown_cost_resources')}"

    assert all_passed, "One or more endpoints failed!"
    print("\nAll endpoints and paths verified successfully with NULL costs.")


if __name__ == "__main__":
    main()
