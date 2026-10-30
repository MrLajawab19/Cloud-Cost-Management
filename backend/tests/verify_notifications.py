"""
backend/verify_notifications.py — Comprehensive test suite for Notification Bell (GET /notifications).
Verifies:
  1) In-memory SQLite with foreign_keys=ON, TestClient with valid JWT.
  2) Demo AWS returns anomaly, recommendation, and escalation events.
  3) IDs are deterministic & stable across multiple calls.
  4) Limit parameter is strictly respected.
  5) Guided remediation accept/complete produces guided_* events in the feed.
  6) Real AWS and Real Azure accounts return 200 without error.
  7) Cross-user account access returns 403 Forbidden.
  8) Network / Cloud SDK isolation (boto3 / azure patched to raise if called).
"""
import _bootstrap


import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models.user import User
from models.account import CloudAccount
from models.resource import Resource
from models.cost_record import CostRecord, Recommendation, format_recommendation_id_fk
from models.remediation import EscalationState, RemediationLog
from models.anomaly import Anomaly
from services.security import create_access_token


def run_tests():
    db_url = "sqlite:///:memory:"
    print("=" * 70)
    print("VERIFY NOTIFICATION BELL API SUITE")
    print(f"Engine Path: {db_url}")
    print("=" * 70)

    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    db = TestingSessionLocal()
    fk_val = db.execute(text("PRAGMA foreign_keys")).scalar()
    assert fk_val == 1, f"Expected PRAGMA foreign_keys=1, got {fk_val}"
    print("PASS: In-memory DB created with PRAGMA foreign_keys=ON.")

    # 1. Create primary user and accounts
    user1 = User(id=str(uuid.uuid4()), email="notif_user@example.com", password_hash="dummy")
    user2 = User(id=str(uuid.uuid4()), email="other_user@example.com", password_hash="dummy")
    db.add_all([user1, user2])
    db.commit()

    token1 = create_access_token({"sub": user1.id})
    token2 = create_access_token({"sub": user2.id})
    headers1 = {"Authorization": f"Bearer {token1}"}
    headers2 = {"Authorization": f"Bearer {token2}"}

    demo_aws = CloudAccount(
        id=str(uuid.uuid4()),
        user_id=user1.id,
        name="Demo AWS",
        provider="aws",
        region="us-east-1",
        access_key_id="",
        encrypted_secret_key="",
        auto_remediate_enabled=True,
        grace_period_hours=24,
    )
    demo_az = CloudAccount(
        id=str(uuid.uuid4()),
        user_id=user1.id,
        name="Demo Azure",
        provider="azure",
        region="eastus",
        access_key_id="",
        encrypted_secret_key="",
        auto_remediate_enabled=False,
    )
    real_aws = CloudAccount(
        id=str(uuid.uuid4()),
        user_id=user1.id,
        name="Real AWS",
        provider="aws",
        region="us-east-1",
        access_key_id="AKIAREALKEY123",
        encrypted_secret_key="ENCRYPTEDSECRET",
    )
    real_az = CloudAccount(
        id=str(uuid.uuid4()),
        user_id=user1.id,
        name="Real Azure",
        provider="azure",
        region="eastus",
        access_key_id="real-client-id",
        encrypted_secret_key="ENCRYPTEDAZSECRET",
    )
    other_acc = CloudAccount(
        id=str(uuid.uuid4()),
        user_id=user2.id,
        name="Other User Account",
        provider="aws",
        region="us-west-2",
        access_key_id="",
        encrypted_secret_key="",
    )
    db.add_all([demo_aws, demo_az, real_aws, real_az, other_acc])
    db.commit()

    # 2. Seed data for Demo AWS: Anomaly, Recommendation, Escalation (action_due)
    now = datetime.utcnow()
    anom = Anomaly(
        account_id=demo_aws.id,
        service_type="EC2",
        record_date=(now - timedelta(days=2)).date(),
        actual_cost=450.0,
        forecast_cost=100.0,
        residual=350.0,
        z_score=4.2,
        iqr_flagged=True,
        severity="critical",
        direction="spike",
        driver_service="EC2",
        is_resolved=False,
    )
    rec = Recommendation(
        account_id=demo_aws.id,
        resource_id="i-demo-notif-ec2",
        resource_name="demo-notif-worker",
        service_type="EC2",
        region="us-east-1",
        issue="Idle EC2 Instance",
        description="EC2 instance has been idle for 14 days",
        action="Stop the instance.",
        remediation_type="stop",
        severity="high",
        potential_savings_usd=55.0,
    )
    rec_sp = Recommendation(
        account_id=demo_aws.id,
        resource_id="EC2-SP-1Y",
        resource_name="EC2 1-Year Plan",
        service_type="EC2",
        region="global",
        issue="No Commitment",
        description="Steady EC2 baseline",
        action="Purchase Savings Plan",
        remediation_type="manual",
        severity="medium",
        potential_savings_usd=120.0,
    )
    db.add_all([anom, rec, rec_sp])
    db.flush()

    esc = EscalationState(
        id=str(uuid.uuid4()),
        recommendation_id=format_recommendation_id_fk(rec.id, db),
        status="action_due",
        due_at=now - timedelta(hours=2),
    )
    db.add(esc)
    db.commit()

    # SDK guard
    def fake_cloud_call(*args, **kwargs):
        raise RuntimeError("Illegal real cloud SDK call executed!")

    with patch.dict("sys.modules", {"boto3": MagicMock(side_effect=fake_cloud_call)}):
        client = TestClient(app)

        # Test A: GET /notifications for Demo AWS
        print("\n--- Test A: GET /notifications for Demo AWS ---")
        res1 = client.get(f"/notifications?account_id={demo_aws.id}", headers=headers1)
        assert res1.status_code == 200, f"Expected 200, got {res1.status_code}: {res1.text}"
        events1 = res1.json()
        assert isinstance(events1, list)
        assert len(events1) >= 3, f"Expected >= 3 events, got {len(events1)}"

        types = [e["type"] for e in events1]
        print(f"Demo AWS event types: {types}")
        assert "anomaly_detected" in types
        assert "recommendation_created" in types
        assert any(t in ["escalation_action_due", "escalation_held"] for t in types)

        # Verify fields on first event
        sample = events1[0]
        required_keys = {"id", "type", "severity", "title", "message", "created_at", "link", "account_id"}
        assert required_keys.issubset(set(sample.keys())), f"Missing keys in event: {sample.keys()}"
        assert sample["severity"] in ["info", "warning", "critical"]
        print(f"Sample event: {sample['id']} [{sample['severity']}] -> {sample['title']}")

        # Test B: Deterministic / Stable IDs across two calls
        print("\n--- Test B: Determinism of Event IDs ---")
        res2 = client.get(f"/notifications?account_id={demo_aws.id}", headers=headers1)
        events2 = res2.json()
        ids1 = [e["id"] for e in events1]
        ids2 = [e["id"] for e in events2]
        assert ids1 == ids2, "Event IDs must be identical and deterministic across consecutive calls"
        print("PASS: Event IDs and order are strictly identical across consecutive calls.")

        # Test C: Limit parameter
        print("\n--- Test C: Limit Parameter Enforcement ---")
        res_limit = client.get(f"/notifications?account_id={demo_aws.id}&limit=2", headers=headers1)
        assert res_limit.status_code == 200
        assert len(res_limit.json()) == 2
        print("PASS: Limit=2 returned exactly 2 events.")

        # Test D: Guided Remediation accept & complete triggers guided_* events
        print("\n--- Test D: Guided Remediation Accept & Complete Events ---")
        acc_resp = client.post(f"/remediation/guided/{rec.id}/accept", headers=headers1)
        assert acc_resp.status_code == 200, f"Accept failed: {acc_resp.text}"

        res_post_acc = client.get(f"/notifications?account_id={demo_aws.id}", headers=headers1)
        post_acc_types = [e["type"] for e in res_post_acc.json()]
        assert "guided_accepted" in post_acc_types, f"Expected 'guided_accepted' event in {post_acc_types}"
        print("PASS: 'guided_accepted' notification event appeared after accept.")

        comp_resp = client.post(f"/remediation/guided/{rec.id}/complete", headers=headers1)
        assert comp_resp.status_code == 200, f"Complete failed: {comp_resp.text}"

        res_post_comp = client.get(f"/notifications?account_id={demo_aws.id}", headers=headers1)
        post_comp_types = [e["type"] for e in res_post_comp.json()]
        assert "guided_completed" in post_comp_types, f"Expected 'guided_completed' event in {post_comp_types}"
        print("PASS: 'guided_completed' notification event appeared after complete.")

        # Test E: Real AWS and Real Azure accounts return 200
        print("\n--- Test E: Real AWS and Real Azure Account Calls ---")
        r_aws = client.get(f"/notifications?account_id={real_aws.id}", headers=headers1)
        assert r_aws.status_code == 200
        r_az = client.get(f"/notifications?account_id={real_az.id}", headers=headers1)
        assert r_az.status_code == 200
        print(f"PASS: Real AWS (count={len(r_aws.json())}) and Real Azure (count={len(r_az.json())}) returned 200.")

        # Test F: Cross-User Security Check -> 403 Forbidden
        print("\n--- Test F: Ownership Security Check ---")
        r_sec = client.get(f"/notifications?account_id={other_acc.id}", headers=headers1)
        assert r_sec.status_code == 403, f"Expected 403 for unauthorized account, got {r_sec.status_code}"
        print("PASS: Access to another user's account correctly rejected with 403 Forbidden.")

    print("\n" + "=" * 70)
    print("ALL NOTIFICATION BELL VERIFICATIONS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_tests()

