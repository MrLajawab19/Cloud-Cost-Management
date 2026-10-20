"""
backend/verify_remediation_status.py
Verification script for Item N:
- In-memory SQLite with foreign_keys=ON.
- TestClient calling GET /remediation/status and GET /recommendations.
- Demo AWS account shows pending escalation.
- After advancing time with unresolved spike anomaly -> held: true with reason.
- After resolving anomaly -> process_escalations writes log 'simulated'.
- DELETE /accounts/{id} on real account with logs/escalation -> 200; demo account -> 403.
"""

import sys
import os
import uuid
import json
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Base, get_db
import scheduler
from main import app
from models.user import User
from models.account import CloudAccount
from models.resource import Resource
from models.cost_record import Recommendation, format_recommendation_id_fk
from models.remediation import EscalationState, RemediationLog
from models.anomaly import Anomaly
from services.security import create_access_token
from services.cleanup_advisor import generate_recommendations
from services.escalation_manager import process_escalations

Base.metadata.create_all(bind=engine)
Session = sessionmaker(bind=engine)
scheduler.SessionLocal = Session

def override_get_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

def run_tests():
    # Mock cloud calls during any startup/pipeline trigger
    with patch("services.aws_collector.collect_all", return_value=[]), \
         patch("services.azure_collector.collect_all", return_value=[]):
        client = TestClient(app)

    db = Session()
    fk_on = db.execute(text("PRAGMA foreign_keys")).fetchone()[0]
    print(f"PRAGMA foreign_keys = {fk_on} (ON)")

    # 1. Create user
    user = User(id=str(uuid.uuid4()), email="test_rem@example.com", password_hash="hash")
    db.add(user)
    db.commit()

    token = create_access_token({"sub": user.id})
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create Demo AWS Account
    demo_acc = CloudAccount(
        id=str(uuid.uuid4()),
        user_id=user.id,
        name="Demo AWS Account",
        provider="aws",
        region="us-east-1",
        access_key_id="",
        encrypted_secret_key="",
        auto_remediate_enabled=True,
        grace_period_hours=24,
    )
    db.add(demo_acc)
    db.commit()

    # 3. Add an Idle EC2 resource that triggers stop recommendation & escalation
    res = Resource(
        id=uuid.uuid4(),
        account_id=demo_acc.id,
        resource_id="i-demo-idle-01",
        resource_name="demo-idle-ec2",
        service_type="EC2",
        region="us-east-1",
        status="running",
        resource_type="t3.medium",
        cpu_utilization_avg=0.0,
        runtime_hours=300.0,
        estimated_monthly_cost=50.0,
        is_idle=True,
    )
    db.add(res)
    db.commit()

    # Generate recommendations
    generate_recommendations(db)

    rec = db.query(Recommendation).filter_by(account_id=demo_acc.id, issue="Idle EC2 Instance").first()
    assert rec is not None, "Idle EC2 Recommendation not generated"
    assert rec.remediation_type == "stop"

    # Add an unresolved EC2 anomaly within 14 days
    anom = Anomaly(
        account_id=demo_acc.id,
        service_type="EC2",
        record_date=datetime.utcnow().date() - timedelta(days=2),
        actual_cost=20.0,
        forecast_cost=5.0,
        residual=15.0,
        z_score=5.2,
        severity="critical",
        direction="spike",
        is_resolved=False,
    )
    db.add(anom)
    db.commit()

    # Check GET /recommendations response fields
    rec_res = client.get(f"/recommendations/?account_id={demo_acc.id}", headers=headers)
    assert rec_res.status_code == 200
    recs_json = rec_res.json()
    assert len(recs_json) >= 1
    sample_rec = recs_json[0]
    print(f"Sample recommendation response fields: {list(sample_rec.keys())}")
    assert "remediation_type" in sample_rec and sample_rec["remediation_type"] == "stop"
    assert "is_resolved" in sample_rec
    assert "resource_name" in sample_rec
    print("PASS: GET /recommendations includes remediation_type, is_resolved, and resource_name.")

    # Check GET /remediation/status: initial pending state
    status_res = client.get(f"/remediation/status?account_id={demo_acc.id}", headers=headers)
    assert status_res.status_code == 200
    status_data = status_res.json()
    print("Initial /remediation/status response:")
    print(json.dumps(status_data, indent=2))
    assert len(status_data["escalations"]) == 1
    esc_item = status_data["escalations"][0]
    assert esc_item["status"] == "pending"
    assert esc_item["held"] is False
    assert esc_item["held_reason"] is None
    assert esc_item["hours_remaining"] > 0

    # Advance time past due_at
    esc_db = db.query(EscalationState).first()
    esc_db.due_at = datetime.utcnow() - timedelta(hours=2)
    db.commit()

    # Query status again with time advanced and anomaly unresolved -> held should be True
    status_res2 = client.get(f"/remediation/status?account_id={demo_acc.id}", headers=headers)
    assert status_res2.status_code == 200
    status_data2 = status_res2.json()
    print("Status response with grace period expired & anomaly active (HELD):")
    print(json.dumps(status_data2, indent=2))
    esc_item2 = status_data2["escalations"][0]
    assert esc_item2["held"] is True
    assert esc_item2["held_reason"] == "Unresolved anomaly on EC2 within 14 days"
    assert esc_item2["hours_remaining"] == 0.0

    # Process escalations while anomaly active -> remains pending
    process_escalations(db)
    db.refresh(esc_db)
    assert esc_db.status == "pending"

    # Resolve anomaly
    anom.is_resolved = True
    db.commit()

    # Process escalations after anomaly resolved -> executes stop remediation and creates log
    process_escalations(db)
    db.refresh(esc_db)
    assert esc_db.status == "resolved"

    status_res3 = client.get(f"/remediation/status?account_id={demo_acc.id}", headers=headers)
    assert status_res3.status_code == 200
    status_data3 = status_res3.json()
    print("Status response after resolving anomaly and execution:")
    print(json.dumps(status_data3, indent=2))
    assert len(status_data3["logs"]) >= 1
    log_item = status_data3["logs"][0]
    assert log_item["status"] == "simulated"
    assert log_item["action_type"] == "stop"

    # Test DELETE /accounts/{id} on real account and demo account
    # Demo account delete -> 403
    del_demo = client.delete(f"/accounts/{demo_acc.id}", headers=headers)
    assert del_demo.status_code == 403, f"Expected 403 on demo delete, got {del_demo.status_code}"
    print("PASS: DELETE on demo account correctly returned 403.")

    # Real account with remediation log & escalation -> delete 200
    real_acc = CloudAccount(
        id=str(uuid.uuid4()),
        user_id=user.id,
        name="Real AWS Account",
        provider="aws",
        region="us-east-1",
        access_key_id="AKIAREALACCOUNT12",
        encrypted_secret_key="ENCRYPTEDSECRET12",
        auto_remediate_enabled=True,
    )
    db.add(real_acc)
    db.commit()

    # Add a remediation log and escalation for real account
    real_rec = Recommendation(
        account_id=real_acc.id,
        resource_id="i-real-01",
        resource_name="real-ec2",
        service_type="EC2",
        region="us-east-1",
        issue="Idle EC2",
        description="Test description",
        action="Stop instance",
        remediation_type="stop",
        severity="high",
        potential_savings_usd=100.0,
    )
    db.add(real_rec)
    db.commit()

    real_esc = EscalationState(
        recommendation_id=format_recommendation_id_fk(real_rec.id, db),
        status="pending",
        due_at=datetime.utcnow() + timedelta(hours=24),
    )
    db.add(real_esc)
    real_log = RemediationLog(
        account_id=real_acc.id,
        resource_id="i-real-01",
        action_type="stop",
        status="simulated",
        trigger_reason="Test",
    )
    db.add(real_log)
    db.commit()

    del_real = client.delete(f"/accounts/{real_acc.id}", headers=headers)
    assert del_real.status_code == 200, f"Expected 200 on real delete, got {del_real.status_code}: {del_real.text}"
    print("PASS: DELETE on real account with remediation logs and escalations returned 200 without FK violation.")

    print("\nVERIFY_REMEDIATION_STATUS COMPLETE: ALL TESTS PASSED.")

if __name__ == "__main__":
    run_tests()
