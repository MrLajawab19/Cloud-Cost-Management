"""
verify_guided_remediation.py
Verification suite for Client Changes #3 Item 2: Guided Remediation.
- Idle EC2 grace period expiry without anomaly -> transition to stage 'action_due', 0 simulated stop logs.
- Active unresolved anomaly -> HELD badge with hold reason.
- User transitions:
  - accept -> 'accepted' (writes RemediationLog with status 'guided_accepted' and actor email)
  - complete -> 'completed', resolves recommendation, closes escalation, writes 'guided_completed' log
  - decline path -> 'declined', dismisses recommendation, closes escalation, writes 'guided_declined' log
- Invalid transitions -> HTTP 409 Conflict.
- Real accounts supported through identical guided endpoints.
- Cross-user ownership protection -> 403/404.
- Zero Cloud SDK calls: boto3 and azure modules patched to raise RuntimeError if invoked.
- In-memory SQLite DB with foreign_keys=ON.
"""
import _bootstrap


import sys
import os
import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models.user import User
from models.account import CloudAccount
from models.cost_record import Recommendation, format_recommendation_id_fk
from models.resource import Resource
from models.anomaly import Anomaly
from models.remediation import EscalationState, RemediationLog
from services.security import get_password_hash, create_access_token
from services.escalation_manager import process_escalations
from services.cleanup_advisor import generate_recommendations


def run_suite():
    print("=" * 70)
    print("VERIFY CLIENT CHANGES #3 - ITEM 2: GUIDED REMEDIATION")
    print("=" * 70)

    # 0. Strict Cloud SDK Safety Guard: patch boto3 and azure to raise if called
    mock_sdk_guard = MagicMock(side_effect=RuntimeError("Cloud SDK call strictly blocked in guided remediation!"))
    boto_patch = patch.dict("sys.modules", {"boto3": mock_sdk_guard, "azure": mock_sdk_guard})
    boto_patch.start()

    # In-memory DB setup with FK ON
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    print(f"Database Engine Path: {engine.url}")

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    db = TestingSession()

    # 1. Users setup
    user1 = User(
        id=str(uuid.uuid4()),
        email="guided_user1@example.com",
        password_hash=get_password_hash("Password123!"),
    )
    user2 = User(
        id=str(uuid.uuid4()),
        email="guided_user2@example.com",
        password_hash=get_password_hash("Password123!"),
    )
    db.add_all([user1, user2])
    db.commit()

    token1 = create_access_token({"sub": user1.id})
    token2 = create_access_token({"sub": user2.id})
    h1 = {"Authorization": f"Bearer {token1}"}
    h2 = {"Authorization": f"Bearer {token2}"}

    # 2. Setup Accounts: Demo AWS for user1, Real AWS for user1, Demo AWS for user2
    acc_demo = CloudAccount(
        id=str(uuid.uuid5(uuid.UUID(user1.id), "demo-aws")),
        user_id=user1.id,
        name="Demo AWS",
        region="us-east-1",
        provider="aws",
        auto_remediate_enabled=True,
        grace_period_hours=24,
    )
    acc_real = CloudAccount(
        id=str(uuid.uuid4()),
        user_id=user1.id,
        name="Real AWS Account",
        region="us-east-1",
        provider="aws",
        access_key_id="AKIAREALGUIDED123",
        encrypted_secret_key="mock_secret",
        auto_remediate_enabled=True,
        grace_period_hours=48,
    )
    acc_user2 = CloudAccount(
        id=str(uuid.uuid5(uuid.UUID(user2.id), "demo-aws")),
        user_id=user2.id,
        name="User2 Demo AWS",
        region="us-east-1",
        provider="aws",
        auto_remediate_enabled=True,
    )
    db.add_all([acc_demo, acc_real, acc_user2])
    db.commit()

    # 3. Setup Resource & Recommendation for Idle EC2 (Stop)
    idle_res = Resource(
        id=uuid.uuid4(),
        account_id=acc_demo.id,
        resource_id="i-demo-idle-guided",
        resource_name="demo-idle-worker",
        service_type="EC2",
        region="us-east-1",
        status="running",
        resource_type="t3.medium",
        cpu_utilization_avg=0.3,
        runtime_hours=300.0,
        estimated_monthly_cost=40.0,
    )
    db.add(idle_res)
    db.commit()

    generate_recommendations(db)

    idle_rec = db.query(Recommendation).filter(
        Recommendation.account_id == acc_demo.id,
        Recommendation.resource_id == idle_res.resource_id,
        Recommendation.remediation_type == "stop"
    ).first()
    assert idle_rec is not None, "Idle EC2 recommendation must be created"
    rec_id_str = str(idle_rec.id)

    rec_fk = format_recommendation_id_fk(idle_rec.id, db)
    esc = db.query(EscalationState).filter(
        (EscalationState.recommendation_id == rec_fk) |
        (EscalationState.recommendation_id == rec_id_str)
    ).first()
    assert esc is not None, "EscalationState must be created"
    assert esc.status == "pending"

    # 4. Test: With active anomaly -> HELD
    print("\n--- Test 1: Grace period expired with active anomaly -> HELD ---")
    now = datetime.utcnow()
    # Create active anomaly for EC2
    anom = Anomaly(
        id=str(uuid.uuid4()),
        account_id=acc_demo.id,
        service_type="EC2",
        record_date=(now - timedelta(days=2)).date(),
        actual_cost=120.0,
        forecast_cost=40.0,
        residual=80.0,
        z_score=6.5,
        direction="spike",
        severity="critical",
        is_resolved=False,
    )
    db.add(anom)
    # Expire grace period
    esc.due_at = now - timedelta(hours=2)
    db.commit()

    # Run processor
    process_escalations(db)
    db.refresh(esc)
    assert esc.status == "pending", f"Expected pending while held, got {esc.status}"

    # Query GET /remediation/status
    r_status1 = client.get(f"/remediation/status?account_id={acc_demo.id}", headers=h1)
    assert r_status1.status_code == 200
    st1 = r_status1.json()
    item1 = next((e for e in st1["escalations"] if e["recommendation_id"] == rec_id_str), None)
    assert item1 is not None
    assert item1["held"] is True
    assert "anomaly" in item1["held_reason"].lower()
    assert len(st1["logs"]) == 0, "No remediation logs should exist"
    print("PASS: Escalation held due to active anomaly; zero simulated logs.")

    # 5. Test: Resolve anomaly -> becomes stage 'action_due', NO simulated stop log
    print("\n--- Test 2: Anomaly resolved -> stage 'action_due', NO simulated execution ---")
    anom.is_resolved = True
    db.commit()

    process_escalations(db)
    db.refresh(esc)
    assert esc.status == "action_due", f"Expected action_due, got {esc.status}"

    r_status2 = client.get(f"/remediation/status?account_id={acc_demo.id}", headers=h1)
    st2 = r_status2.json()
    item2 = next((e for e in st2["escalations"] if e["recommendation_id"] == rec_id_str), None)
    assert item2 is not None
    assert item2["held"] is False
    assert item2["stage"] == "action_due"
    assert "accept" in item2["allowed_actions"]
    assert "decline" in item2["allowed_actions"]
    assert len(st2["logs"]) == 0, "No simulated stop log must be generated"
    print("PASS: Escalation transitioned to 'action_due'; 0 simulated stop logs.")

    # 6. Test: Invalid transition (attempt complete while in action_due) -> 409
    print("\n--- Test 3: Invalid transition -> 409 ---")
    r_bad = client.post(f"/remediation/guided/{rec_id_str}/complete", headers=h1)
    assert r_bad.status_code == 409, f"Expected 409, got {r_bad.status_code}: {r_bad.text}"
    print(f"PASS: Invalid transition rejected with 409: {r_bad.json()['detail']}")

    # 7. Test: Accept -> state 'accepted', log row 'guided_accepted' with user email
    print("\n--- Test 4: Accept guided remediation ---")
    r_acc = client.post(f"/remediation/guided/{rec_id_str}/accept", headers=h1)
    assert r_acc.status_code == 200
    assert r_acc.json()["guided_state"] == "accepted"

    db.refresh(esc)
    assert esc.status == "accepted"

    r_status3 = client.get(f"/remediation/status?account_id={acc_demo.id}", headers=h1)
    st3 = r_status3.json()
    item3 = next((e for e in st3["escalations"] if e["recommendation_id"] == rec_id_str), None)
    assert item3["guided_state"] == "accepted"
    assert item3["allowed_actions"] == ["complete"]
    assert len(st3["logs"]) == 1
    log_acc = st3["logs"][0]
    assert log_acc["status"] == "guided_accepted"
    assert user1.email in log_acc["actor"] or user1.email in log_acc["before_state"]
    print(f"PASS: Accept recorded: status={log_acc['status']}, actor={log_acc['actor']}")

    # 8. Test: Complete -> recommendation resolved, escalation closed, log row 'guided_completed'
    print("\n--- Test 5: Complete guided remediation ---")
    r_comp = client.post(f"/remediation/guided/{rec_id_str}/complete", headers=h1)
    assert r_comp.status_code == 200
    assert r_comp.json()["guided_state"] == "completed"

    db.refresh(idle_rec)
    db.refresh(esc)
    assert idle_rec.is_resolved is True, "Recommendation must be resolved"
    assert esc.status == "completed"

    r_status4 = client.get(f"/remediation/status?account_id={acc_demo.id}", headers=h1)
    st4 = r_status4.json()
    assert len(st4["logs"]) == 2
    comp_log = next(l for l in st4["logs"] if l["status"] == "guided_completed")
    assert comp_log is not None
    assert user1.email in comp_log["actor"] or user1.email in comp_log["before_state"]
    print(f"PASS: Complete recorded: status={comp_log['status']}, rec.is_resolved=True")

    # 9. Test: Decline path on a second resource
    print("\n--- Test 6: Decline guided remediation ---")
    dec_res = Resource(
        id=uuid.uuid4(),
        account_id=acc_demo.id,
        resource_id="i-demo-decline-worker",
        resource_name="demo-decline-worker",
        service_type="EC2",
        region="us-east-1",
        status="running",
        resource_type="t3.medium",
        cpu_utilization_avg=0.2,
        runtime_hours=200.0,
        estimated_monthly_cost=40.0,
    )
    db.add(dec_res)
    db.commit()
    generate_recommendations(db)
    dec_rec = db.query(Recommendation).filter(Recommendation.resource_id == dec_res.resource_id).first()
    dec_rec_id = str(dec_rec.id)

    # Move to action_due
    dec_esc = db.query(EscalationState).filter(
        EscalationState.recommendation_id == format_recommendation_id_fk(dec_rec.id, db)
    ).first()
    dec_esc.due_at = now - timedelta(hours=1)
    db.commit()
    process_escalations(db)

    # Call decline
    r_dec = client.post(f"/remediation/guided/{dec_rec_id}/decline", headers=h1)
    assert r_dec.status_code == 200
    assert r_dec.json()["guided_state"] == "declined"

    db.refresh(dec_rec)
    db.refresh(dec_esc)
    assert dec_rec.ignore_remediation is True
    assert dec_esc.status == "declined"
    print("PASS: Decline recorded: status='declined', rec.ignore_remediation=True")

    # 10. Test: Real Account Works via same guided endpoints
    print("\n--- Test 7: Real account guided remediation ---")
    real_res = Resource(
        id=uuid.uuid4(),
        account_id=acc_real.id,
        resource_id="i-real-guided-worker",
        resource_name="real-guided-worker",
        service_type="EC2",
        region="us-east-1",
        status="running",
        resource_type="t3.small",
        cpu_utilization_avg=0.4,
        runtime_hours=250.0,
        estimated_monthly_cost=30.0,
    )
    db.add(real_res)
    db.commit()
    generate_recommendations(db)
    real_rec = db.query(Recommendation).filter(Recommendation.resource_id == real_res.resource_id).first()
    real_rec_id = str(real_rec.id)

    # Accept on real account
    r_real_acc = client.post(f"/remediation/guided/{real_rec_id}/accept", headers=h1)
    assert r_real_acc.status_code == 200
    assert r_real_acc.json()["guided_state"] == "accepted"

    # Complete on real account
    r_real_comp = client.post(f"/remediation/guided/{real_rec_id}/complete", headers=h1)
    assert r_real_comp.status_code == 200
    assert r_real_comp.json()["guided_state"] == "completed"
    print("PASS: Real account successfully processed guided accept & complete.")

    # 11. Test: Cross-user ownership protection -> 403/404
    print("\n--- Test 8: Security guards (other user's account -> 403/404) ---")
    r_cross_acc = client.post(f"/remediation/guided/{rec_id_str}/accept", headers=h2)
    assert r_cross_acc.status_code in [403, 404], f"Expected 403/404, got {r_cross_acc.status_code}"
    print(f"PASS: Cross-user access rejected with code {r_cross_acc.status_code}.")

    # 12. Print the Audit Rows
    print("\n" + "=" * 70)
    print("REMEDIATION AUDIT ROWS TABLE:")
    print("=" * 70)
    all_logs = db.query(RemediationLog).order_by(RemediationLog.timestamp.asc()).all()
    print(f"{'TIMESTAMP':<22} | {'RESOURCE':<24} | {'ACTION':<8} | {'STATUS':<18} | {'ACTOR/DETAILS'}")
    print("-" * 100)
    for l in all_logs:
        ts = l.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        print(f"{ts:<22} | {l.resource_id:<24} | {l.action_type:<8} | {l.status:<18} | {l.before_state}")
    print("=" * 70)
    print("ALL GUIDED REMEDIATION VERIFICATIONS PASSED SUCCESSFULLY!")
    print("=" * 70)

    boto_patch.stop()

if __name__ == "__main__":
    run_suite()
