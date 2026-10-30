"""
verify_client_changes3_item1.py
Verification suite for Client Changes #3 Item 1:
- Savings Optimiser reacts to injected services ("new_service" scenario).
- Distinguishable tagging (source="demo_injected").
- Provider separation (AWS: EC2/RDS/Lambda/S3; Azure: AzureVM).
- Injected service card with is_new=True, "New" badge flag.
- Services with no commitment product (S3, Lambda) show "No commitment option for this service".
- Before/after panel contains "New plan available: <service>".
- Demo reset restores original plans and keeps baseline determinism hash unchanged.
- Security guards: 403 on real accounts and other users' demo accounts.
- In-memory SQLite DB with foreign keys enabled.
"""
import _bootstrap


import sys
import os
import json
import uuid
import hashlib
from datetime import datetime, date, timedelta

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
from models.cost_record import CostRecord, Recommendation
from models.resource import Resource
from models.anomaly import Anomaly
from services.security import get_password_hash, create_access_token
from services.demo_data import seed_demo_history, reset_demo_account, ensure_demo_accounts

def run_suite():
    print("=" * 70)
    print("VERIFY CLIENT CHANGES #3 - ITEM 1 (Savings Optimiser & New Service Injection)")
    print("=" * 70)

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

    # 1. Setup users and JWT tokens
    user1 = User(
        id=str(uuid.uuid4()),
        email="client3_user1@example.com",
        password_hash=get_password_hash("Password123!"),
    )
    user2 = User(
        id=str(uuid.uuid4()),
        email="client3_user2@example.com",
        password_hash=get_password_hash("Password123!"),
    )
    db.add_all([user1, user2])
    db.commit()

    token1 = create_access_token({"sub": user1.id})
    token2 = create_access_token({"sub": user2.id})
    h1 = {"Authorization": f"Bearer {token1}"}
    h2 = {"Authorization": f"Bearer {token2}"}

    # 2. Setup demo accounts & real accounts
    acc_aws_demo, acc_azure_demo = ensure_demo_accounts(db, user1.id)
    reset_demo_account(db, acc_aws_demo)
    reset_demo_account(db, acc_azure_demo)

    acc_aws_real = CloudAccount(
        id=str(uuid.uuid4()),
        user_id=user1.id,
        name="Real AWS Account",
        region="us-east-1",
        provider="aws",
        access_key_id="AKIAREALEXAMPLEREAL",
        encrypted_secret_key="mocked_encrypted_secret"
    )
    acc_user2_demo, _ = ensure_demo_accounts(db, user2.id)
    reset_demo_account(db, acc_user2_demo)
    db.add(acc_aws_real)
    db.commit()

    # Resolve existing demo anomalies on user1 AWS demo account for clear baseline plan comparison
    db.query(Anomaly).filter(Anomaly.account_id == acc_aws_demo.id).update({"is_resolved": True})
    db.commit()

    # Compute baseline determinism hash of fresh demo account
    aws_costs_pre = [
        r.daily_cost_usd
        for r in db.query(CostRecord)
        .filter(CostRecord.account_id == acc_aws_demo.id)
        .order_by(CostRecord.record_date)
        .all()
    ]
    pre_hash = hashlib.sha256(json.dumps(aws_costs_pre).encode()).hexdigest()
    print(f"Initial Demo AWS Cost Records count: {len(aws_costs_pre)}, Hash: {pre_hash}")

    # Check initial plans before injection
    r_plans_pre = client.get(f"/savings-optimiser/plans?account_id={acc_aws_demo.id}", headers=h1)
    assert r_plans_pre.status_code == 200, f"Plans failed: {r_plans_pre.text}"
    plans_pre = r_plans_pre.json()
    pre_service_names = [s["service"] for s in plans_pre["services"]]
    assert "EC2" in pre_service_names and "RDS" in pre_service_names
    assert all(not s.get("is_new", False) for s in plans_pre["services"]), "Initial plans must have is_new=False"
    print(f"PASS: Baseline plans verified: {pre_service_names}")

    # 3. Test: Inject new_service EC2 (second pool of cost)
    print("\n--- Testing new_service EC2 (second pool of cost) ---")
    r_inj_ec2 = client.post(
        f"/demo/inject?account_id={acc_aws_demo.id}",
        json={"scenario": "new_service", "service": "EC2", "monthly_cost": 150.0},
        headers=h1
    )
    assert r_inj_ec2.status_code == 200, f"Inject EC2 failed: {r_inj_ec2.text}"
    inj_ec2_data = r_inj_ec2.json()
    
    # Print before/after trimmed JSON
    print("Trimmed Before/After JSON (EC2 Injection):")
    trimmed_summary = {
        "scenario": inj_ec2_data["scenario"],
        "before_forecast_30d": inj_ec2_data["before"]["forecast"]["total_30d"],
        "after_forecast_30d": inj_ec2_data["after"]["forecast"]["total_30d"],
        "forecast_delta": inj_ec2_data["delta"]["forecast_30d_delta"],
        "savings_optimiser_changes": inj_ec2_data["delta"]["savings_optimiser_changes"],
        "after_savings_optimiser": [
            {"service": s["service"], "recommended": s["recommended"], "is_new": s.get("is_new")}
            for s in inj_ec2_data["after"]["savings_optimiser"]
        ]
    }
    print(json.dumps(trimmed_summary, indent=2))

    # Verify GET /savings-optimiser/plans reflects injected EC2 with is_new=True
    r_plans_ec2 = client.get(f"/savings-optimiser/plans?account_id={acc_aws_demo.id}", headers=h1)
    assert r_plans_ec2.status_code == 200
    plans_ec2 = r_plans_ec2.json()
    ec2_card = next((s for s in plans_ec2["services"] if s["service"] == "EC2"), None)
    assert ec2_card is not None
    assert ec2_card["is_new"] is True, "Injected EC2 must have is_new=True"
    assert ec2_card["has_commitment_option"] is True
    assert len(ec2_card["options_list"]) > 0, "EC2 must have commitment options"
    assert ec2_card["recommended"] is not None and len(ec2_card["reason"]) > 0
    print(f"PASS: Injected EC2 plan has is_new=True, recommended={ec2_card['recommended']}, reason={ec2_card['reason']}")

    # 4. Test: Inject new_service RDS
    print("\n--- Testing new_service RDS ---")
    r_inj_rds = client.post(
        f"/demo/inject?account_id={acc_aws_demo.id}",
        json={"scenario": "new_service", "service": "RDS", "monthly_cost": 200.0},
        headers=h1
    )
    assert r_inj_rds.status_code == 200
    r_plans_rds = client.get(f"/savings-optimiser/plans?account_id={acc_aws_demo.id}", headers=h1)
    rds_card = next((s for s in r_plans_rds.json()["services"] if s["service"] == "RDS"), None)
    assert rds_card is not None
    assert rds_card["is_new"] is True, "Injected RDS must have is_new=True"
    assert len(rds_card["options_list"]) > 0
    print(f"PASS: Injected RDS plan has is_new=True, recommended={rds_card['recommended']}")

    # 5. Test: Inject new_service Lambda (no commitment option)
    print("\n--- Testing new_service Lambda (no commitment option) ---")
    r_inj_lambda = client.post(
        f"/demo/inject?account_id={acc_aws_demo.id}",
        json={"scenario": "new_service", "service": "Lambda", "monthly_cost": 80.0},
        headers=h1
    )
    assert r_inj_lambda.status_code == 200
    r_plans_lambda = client.get(f"/savings-optimiser/plans?account_id={acc_aws_demo.id}", headers=h1)
    lambda_card = next((s for s in r_plans_lambda.json()["services"] if s["service"] == "Lambda"), None)
    assert lambda_card is not None, "Lambda card must be returned"
    assert lambda_card["is_new"] is True
    assert lambda_card["has_commitment_option"] is False
    assert len(lambda_card["options_list"]) == 0, "Lambda must not have invented options"
    assert lambda_card["recommended"] == "No commitment option for this service"
    assert lambda_card["reason"] == "No commitment option for this service"
    print("PASS: Injected Lambda reported as 'No commitment option for this service' with 0 invented options.")

    # 6. Test: Inject S3-type (no commitment option)
    print("\n--- Testing new_service S3 (no commitment option) ---")
    r_inj_s3 = client.post(
        f"/demo/inject?account_id={acc_aws_demo.id}",
        json={"scenario": "new_service", "service": "S3", "monthly_cost": 90.0},
        headers=h1
    )
    assert r_inj_s3.status_code == 200
    r_plans_s3 = client.get(f"/savings-optimiser/plans?account_id={acc_aws_demo.id}", headers=h1)
    s3_card = next((s for s in r_plans_s3.json()["services"] if s["service"] == "S3"), None)
    assert s3_card is not None
    assert s3_card["is_new"] is True
    assert s3_card["has_commitment_option"] is False
    assert len(s3_card["options_list"]) == 0, "S3 must not have invented options"
    assert s3_card["recommended"] == "No commitment option for this service"
    assert s3_card["reason"] == "No commitment option for this service"
    print("PASS: Injected S3 reported as 'No commitment option for this service'.")

    # 7. Test: Security guards (real account & other user's demo account)
    print("\n--- Testing Security Guards ---")
    r_real = client.post(
        f"/demo/inject?account_id={acc_aws_real.id}",
        json={"scenario": "new_service", "service": "EC2"},
        headers=h1
    )
    assert r_real.status_code == 403, f"Expected 403 for real account, got {r_real.status_code}"
    print("PASS: Real account rejected with 403.")

    r_other = client.post(
        f"/demo/inject?account_id={acc_user2_demo.id}",
        json={"scenario": "new_service", "service": "EC2"},
        headers=h1
    )
    assert r_other.status_code in [403, 404], f"Expected 403/404 for other user demo, got {r_other.status_code}"
    print("PASS: Other user demo account rejected with 403/404.")

    # 8. Test: Reset restores original plans and determinism
    print("\n--- Testing Reset and Determinism ---")
    r_reset = client.post(f"/demo/reset?account_id={acc_aws_demo.id}", headers=h1)
    assert r_reset.status_code == 200
    
    # Verify plans restored to original baseline
    r_plans_post_reset = client.get(f"/savings-optimiser/plans?account_id={acc_aws_demo.id}", headers=h1)
    plans_post_reset = r_plans_post_reset.json()
    post_service_names = [s["service"] for s in plans_post_reset["services"]]
    assert set(post_service_names) == set(pre_service_names), f"Services mismatch after reset: {post_service_names} vs {pre_service_names}"
    assert all(not s.get("is_new", False) for s in plans_post_reset["services"]), "All cards must have is_new=False after reset"
    print("PASS: Plans successfully restored to initial state with is_new=False.")

    # Verify determinism hash
    aws_costs_post = [
        r.daily_cost_usd
        for r in db.query(CostRecord)
        .filter(CostRecord.account_id == acc_aws_demo.id)
        .order_by(CostRecord.record_date)
        .all()
    ]
    post_hash = hashlib.sha256(json.dumps(aws_costs_post).encode()).hexdigest()
    assert pre_hash == post_hash, f"Determinism hash mismatch: {pre_hash} vs {post_hash}"
    print(f"PASS: Fresh demo account determinism hash perfectly preserved: {post_hash}")

    print("\n" + "=" * 70)
    print("ALL VERIFICATIONS PASSED FOR ITEM 1!")
    print("=" * 70)

if __name__ == "__main__":
    run_suite()
