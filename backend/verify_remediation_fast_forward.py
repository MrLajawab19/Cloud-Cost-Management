"""
backend/verify_remediation_fast_forward.py
Verification script for Item Q: Demo fast-forward endpoint.
- In-memory DB with PRAGMA foreign_keys=ON
- TestClient testing:
  1. Demo AWS pending escalation + spike anomaly active -> fast-forward -> held=True, status=pending, no log
  2. Resolve anomaly -> fast-forward again -> log 'simulated', escalation resolved
  3. Real account ID -> 403
  4. Another user's demo account ID -> 403/404
  5. Unknown account ID -> 404
"""

import json
import os
import sys
import uuid
from pathlib import Path

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import scheduler
from database import Base, get_db
from main import app
from models.user import User
from models.account import CloudAccount
from models.cost_record import Recommendation
from models.remediation import EscalationState
from models.anomaly import Anomaly
from services.security import create_access_token, encrypt_secret
from services.demo_data import ensure_demo_accounts, reset_demo_account


def build_test_engine(db_url: str = "sqlite:///:memory:"):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False} if db_url.startswith("sqlite") else {},
        poolclass=StaticPool if db_url == "sqlite:///:memory:" else None,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return engine


def verify_fast_forward():
    print("=" * 60)
    print("VERIFYING ITEM Q: DEMO FAST-FORWARD ENDPOINT")
    print("=" * 60)

    db_url = os.environ.get("DATABASE_URL", "sqlite:///:memory:")
    engine = build_test_engine(db_url)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    scheduler.SessionLocal = Session

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    db = Session()

    # 1. Setup User 1 and User 2
    u1_id = str(uuid.uuid4())
    user1 = User(id=u1_id, email="user1@example.com", password_hash="hash1")
    u2_id = str(uuid.uuid4())
    user2 = User(id=u2_id, email="user2@example.com", password_hash="hash2")
    db.add_all([user1, user2])
    db.commit()

    token1 = create_access_token({"sub": user1.id})
    headers1 = {"Authorization": f"Bearer {token1}"}

    # Ensure demo accounts for user 1 and user 2
    acc1_aws, acc1_azure = ensure_demo_accounts(db, user1.id)
    reset_demo_account(db, acc1_aws)
    reset_demo_account(db, acc1_azure)

    acc2_aws, acc2_azure = ensure_demo_accounts(db, user2.id)
    reset_demo_account(db, acc2_aws)
    reset_demo_account(db, acc2_azure)

    # Check Idle EC2 rec and pending escalation on acc1_aws
    idle_rec = db.query(Recommendation).filter(
        Recommendation.account_id == acc1_aws.id,
        Recommendation.issue == "Idle EC2 Instance"
    ).first()
    assert idle_rec is not None, "Expected Idle EC2 recommendation generated"

    anoms = db.query(Anomaly).filter(Anomaly.account_id == acc1_aws.id).all()
    assert len(anoms) > 0, "Expected active anomalies on acc1_aws"

    esc = db.query(EscalationState).filter(
        EscalationState.status == "pending"
    ).first()
    assert esc is not None, "Expected pending escalation generated"

    print("\n--- Test 1: Fast-forward with active spike anomaly ---")
    resp1 = client.post(f"/remediation/demo/fast-forward?account_id={acc1_aws.id}", headers=headers1)
    assert resp1.status_code == 200, f"Expected 200, got {resp1.status_code}: {resp1.text}"
    data1 = resp1.json()
    print("Response (trimmed):", json.dumps({
        "escalations": data1.get("escalations"),
        "logs": data1.get("logs"),
        "processed": data1.get("processed"),
    }, indent=2))

    # Assertions for Test 1
    assert len(data1["escalations"]) >= 1, "Expected escalation in response"
    target_esc1 = next(e for e in data1["escalations"] if e["recommendation_id"] == str(idle_rec.id))
    assert target_esc1["status"] == "pending", f"Expected pending, got {target_esc1['status']}"
    assert target_esc1["held"] is True, f"Expected held=True due to active anomaly, got {target_esc1['held']}"
    assert "Unresolved anomaly on EC2" in (target_esc1["held_reason"] or "")
    assert len(data1["logs"]) == 0, f"Expected 0 logs executed, got {len(data1['logs'])}"
    print("PASS Test 1: Anomaly exclusion held escalation in pending state, zero logs generated.")

    print("\n--- Test 2: Resolve anomaly and fast-forward again ---")
    for a in anoms:
        a.is_resolved = True
    db.commit()

    resp2 = client.post(f"/remediation/demo/fast-forward?account_id={acc1_aws.id}", headers=headers1)
    assert resp2.status_code == 200, f"Expected 200, got {resp2.status_code}: {resp2.text}"
    data2 = resp2.json()
    print("Response (trimmed):", json.dumps({
        "escalations": data2.get("escalations"),
        "logs": data2.get("logs"),
        "processed": data2.get("processed"),
    }, indent=2))

    # Assertions for Test 2
    target_esc2 = next(e for e in data2["escalations"] if e["recommendation_id"] == str(idle_rec.id))
    assert target_esc2["status"] == "resolved", f"Expected resolved, got {target_esc2['status']}"
    assert target_esc2["held"] is False
    assert len(data2["logs"]) >= 1, "Expected remediation log created"
    log2 = data2["logs"][0]
    assert log2["status"] == "simulated", f"Expected status='simulated', got {log2['status']}"
    assert log2["action_type"] == "stop"
    print("PASS Test 2: Escalation resolved and remediation logged with status='simulated'.")

    print("\n--- Test 3: Real account ID -> 403 ---")
    real_acc = CloudAccount(
        id=f"real-acc-{u1_id[:8]}",
        user_id=user1.id,
        name="Real AWS Test",
        provider="aws",
        region="us-east-1",
        access_key_id="AKIA_REAL_TEST",
        encrypted_secret_key=encrypt_secret("secret123"),
    )
    db.add(real_acc)
    db.commit()

    resp3 = client.post(f"/remediation/demo/fast-forward?account_id={real_acc.id}", headers=headers1)
    print(f"Real account response: {resp3.status_code} ({resp3.json()})")
    assert resp3.status_code == 403, f"Expected 403, got {resp3.status_code}"
    print("PASS Test 3: Real account rejected with 403.")

    print("\n--- Test 4: Another user's demo account -> 403/404 ---")
    resp4 = client.post(f"/remediation/demo/fast-forward?account_id={acc2_aws.id}", headers=headers1)
    print(f"Other user's demo account response: {resp4.status_code} ({resp4.json()})")
    assert resp4.status_code in [403, 404], f"Expected 403 or 404, got {resp4.status_code}"
    print("PASS Test 4: Other user's demo account rejected with 403/404.")

    print("\n--- Test 5: Unknown account ID -> 404 ---")
    resp5 = client.post(f"/remediation/demo/fast-forward?account_id=unknown-uuid-1234", headers=headers1)
    print(f"Unknown account response: {resp5.status_code} ({resp5.json()})")
    assert resp5.status_code == 404, f"Expected 404, got {resp5.status_code}"
    print("PASS Test 5: Unknown account ID rejected with 404.")

    db.close()
    print("\nALL FAST-FORWARD TESTS PASSED SUCCESSFULLY.")


if __name__ == "__main__":
    verify_fast_forward()
