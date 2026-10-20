"""
backend/verify_demo_pipeline.py
Verification suite for Stage 1 Demo Pipeline:
 1) Network/SDK: patch socket, boto3, ClientSecretCredential -> no exceptions, 0 calls
 2) Real accounts: garbage ciphertext gets 0 new rows / never demo data; stubbed real works
 3) Per demo account: resources, recs, forecast MAPE/winner, anomaly driver, SP, simulation, escalation, sources
 4) Determinism: identical hash across 2 generations
 5) Idempotence: ensure x2 and reset x2 -> still 2 accounts, identical counts
 6) TestClient DELETE on demo account -> 403, rows preserved
"""

import hashlib
import json
import os
import socket
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import scheduler
from database import Base, get_db
from main import app
import models.user
import models.account
import models.resource
import models.cost_record
import models.remediation
import models.anomaly
from models.user import User
from models.account import CloudAccount
from models.resource import Resource
from models.cost_record import CostRecord, Recommendation, format_recommendation_id_fk
from models.remediation import EscalationState, RemediationLog
from models.anomaly import Anomaly
from services.security import encrypt_secret, create_access_token
from services.demo_data import (
    ensure_demo_accounts,
    reset_demo_account,
    generate_demo_resources,
)
from services.cost_estimator import is_aws_real, is_azure_real
from services.ml_predictor import predict_costs
from services.what_if_simulator import run_simulation
from services.escalation_manager import process_escalations


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


def run_suite(engine, is_copy_db: bool = False):
    print(f"\n{'='*20} RUNNING DEMO PIPELINE VERIFICATION {'='*20}")
    print(f"Engine URL: {engine.url}")

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

    # Create test user
    user_id = str(uuid.uuid4())
    user = User(id=user_id, email=f"demo_user_{user_id[:6]}@example.com", password_hash="hash")
    db.add(user)
    db.commit()

    token = create_access_token({"sub": user.id})
    headers = {"Authorization": f"Bearer {token}"}

    # Ensure demo accounts
    acc_aws, acc_azure = ensure_demo_accounts(db, user.id)
    reset_demo_account(db, acc_aws)
    reset_demo_account(db, acc_azure)

    print("\n[Check 1] Network/SDK isolation for demo accounts")
    with patch("socket.socket.connect", side_effect=RuntimeError("NETWORK_BLOCKED")), \
         patch("boto3.client", side_effect=RuntimeError("BOTO3_BLOCKED")), \
         patch("boto3.Session", side_effect=RuntimeError("BOTO3_BLOCKED")), \
         patch("azure.identity.ClientSecretCredential", side_effect=RuntimeError("AZURE_BLOCKED")):
        
        # Run collection for demo AWS and demo Azure
        try:
            scheduler.run_collection_pipeline(user_id=user.id, account_id=acc_aws.id)
            scheduler.run_collection_pipeline(user_id=user.id, account_id=acc_azure.id)
            print("  PASS: Zero network/SDK calls made during demo collection.")
        except Exception as e:
            print(f"  FAIL: Demo collection triggered network/SDK call: {e}")
            raise

    print("\n[Check 2] Real accounts dispatch & failure isolation")
    # Real account with garbage ciphertext
    acc_garbage = CloudAccount(
        id=f"acc-garbage-{user_id[:6]}",
        user_id=user.id,
        name="Real AWS Garbage",
        provider="aws",
        access_key_id="AKIA_GARBAGE_KEY",
        encrypted_secret_key="invalid_ciphertext_not_fernet",
        region="us-east-1",
    )
    # Real account with valid-looking ciphertext
    real_secret = encrypt_secret("my_valid_secret")
    acc_valid = CloudAccount(
        id=f"acc-valid-{user_id[:6]}",
        user_id=user.id,
        name="Real AWS Valid",
        provider="aws",
        access_key_id="AKIA_VALID_KEY_1234",
        encrypted_secret_key=real_secret,
        region="us-east-1",
    )
    db.add_all([acc_garbage, acc_valid])
    db.commit()

    # Pre-seed one resource in garbage account to verify rows are preserved
    pre_res = Resource(
        id=uuid.uuid4(),
        account_id=acc_garbage.id,
        resource_id="i-pre-existing-preserved",
        resource_name="preserved-res",
        service_type="EC2",
        region="us-east-1",
        status="running",
    )
    db.add(pre_res)
    db.commit()

    # Stub real collector for valid account
    stub_resources = [
        {
            "resource_id": "i-stubbed-real-ec2",
            "resource_name": "real-stubbed-api",
            "service_type": "EC2",
            "region": "us-east-1",
            "status": "running",
            "estimated_monthly_cost": 50.0,
            "runtime_hours": 200.0,
            "cpu_utilization_avg": 50.0,
        }
    ]

    for env_val in ["true", "false"]:
        with patch.dict(os.environ, {"DEMO_MODE": env_val}):
            with patch("services.aws_collector.collect_all", return_value=(stub_resources, [])):
                scheduler.run_collection_pipeline(user_id=user.id, account_id=acc_garbage.id)
                scheduler.run_collection_pipeline(user_id=user.id, account_id=acc_valid.id)

    # Check garbage account: MUST NOT have demo data, pre-existing row preserved
    garbage_recs = db.query(Recommendation).filter(Recommendation.account_id == acc_garbage.id).count()
    garbage_cost = db.query(CostRecord).filter(CostRecord.account_id == acc_garbage.id).count()
    garbage_res = db.query(Resource).filter(Resource.account_id == acc_garbage.id).all()
    assert len(garbage_res) == 1 and garbage_res[0].resource_id == "i-pre-existing-preserved"
    assert garbage_recs == 0 and garbage_cost == 0
    print(f"  PASS: Garbage ciphertext account has 0 new resources, 0 cost rows, 0 recs (never demo data).")

    # Check valid account: has stubbed real resource
    valid_res = db.query(Resource).filter(Resource.account_id == acc_valid.id).all()
    assert len(valid_res) == 1 and valid_res[0].resource_id == "i-stubbed-real-ec2"
    print(f"  PASS: Valid account received only stubbed real collector data.")

    print("\n[Check 3] Demo Accounts Details")
    for demo_acc, label in [(acc_aws, "AWS"), (acc_azure, "Azure")]:
        print(f"\n  --- Demo {label} Account ({demo_acc.id}) ---")
        res_by_svc = db.query(Resource.service_type, func.count(Resource.id))\
            .filter(Resource.account_id == demo_acc.id)\
            .group_by(Resource.service_type).all()
        print(f"  Resources by service_type: {dict(res_by_svc)}")

        recs = db.query(Recommendation).filter(Recommendation.account_id == demo_acc.id).all()
        print(f"  Recommendations ({len(recs)}):")
        for r in recs:
            print(f"    - [{r.remediation_type}] {r.issue}: savings=${r.potential_savings_usd}")

        pred = predict_costs(db, [demo_acc.id])
        comp = pred.get("model_comparison") or {}
        print(f"  Forecast Winner: {comp.get('winner', 'N/A')} (HW MAPE={comp.get('hw_mape')}%, Poly MAPE={comp.get('poly_mape')}%)")

        sources = db.query(CostRecord.source).filter(CostRecord.account_id == demo_acc.id).distinct().all()
        sources_list = [s[0] for s in sources]
        print(f"  Distinct cost_records.source: {sources_list}")

        if label == "AWS":
            # Assert AWS has zero AzureVM resources or cost rows
            az_in_aws_res = db.query(Resource).filter(Resource.account_id == demo_acc.id, Resource.service_type == "AzureVM").count()
            az_in_aws_cost = db.query(CostRecord).filter(CostRecord.account_id == demo_acc.id, CostRecord.service_type == "AzureVM").count()
            assert az_in_aws_res == 0, f"AWS demo account contains {az_in_aws_res} AzureVM resources"
            assert az_in_aws_cost == 0, f"AWS demo account contains {az_in_aws_cost} AzureVM cost records"
            print("  PASS: Provider separation: AWS demo account has ZERO AzureVM resources/cost rows.")

            assert demo_acc.grace_period_hours == 1, f"Expected grace_period_hours=1, got {demo_acc.grace_period_hours}"
            winner_mape = comp.get("poly_mape") if comp.get("winner") == "Polynomial Regression" else comp.get("hw_mape")
            assert 3.0 <= winner_mape <= 12.0, f"Expected AWS winner MAPE 3-12%, got {winner_mape}"

            anoms = db.query(Anomaly).filter(Anomaly.account_id == demo_acc.id).all()
            print(f"  Anomalies ({len(anoms)}):")
            for a in anoms:
                print(f"    - {a.service_type} on {a.record_date}: z={a.z_score:.2f} sev={a.severity} driver={a.driver_service}")
            assert len(anoms) <= 4, f"Expected <= 4 anomalies, got {len(anoms)}"
            for a in anoms:
                assert a.severity in ["warning", "critical"], f"Unexpected severity {a.severity}"
                assert (datetime.now(timezone.utc).date() - a.record_date).days <= 16, f"Anomaly too early in history: {a.record_date}"

            ec2_anom = [a for a in anoms if a.service_type == "EC2"]
            tot_anom = [a for a in anoms if a.service_type == "TOTAL"]
            assert len(ec2_anom) >= 1 and len(tot_anom) >= 1, "EC2 and TOTAL must be flagged"
            for a in tot_anom:
                assert a.driver_service == "EC2", f"Expected driver EC2, got {a.driver_service}"
            crit_lam_s3 = [a for a in anoms if a.service_type in ["Lambda", "S3"] and a.severity == "critical"]
            assert len(crit_lam_s3) == 0, f"Critical anomaly found on Lambda/S3: {crit_lam_s3}"
            # Idle EC2 simulation and escalation check
            idle_rec = db.query(Recommendation).filter(
                Recommendation.account_id == demo_acc.id,
                Recommendation.issue == "Idle EC2 Instance"
            ).first()
            assert idle_rec is not None, "Expected Idle EC2 recommendation"
            sim = run_simulation(db, demo_acc.id, idle_rec.id)
            print(f"  Simulation on idle rec: baseline=${sim.baseline_30d_usd}, simulated=${sim.simulated_30d_usd}, delta=${sim.delta_usd}")

            esc = db.query(EscalationState).filter(
                EscalationState.recommendation_id.in_([format_recommendation_id_fk(idle_rec.id, db), str(idle_rec.id)])
            ).first()
            assert esc is not None and esc.status == "pending", f"Expected pending escalation, got {esc}"
            assert (esc.due_at - esc.created_at).total_seconds() <= 3601, f"Expected ~1h grace period, got {(esc.due_at - esc.created_at).total_seconds()}"
            print(f"  EscalationState pending: id={esc.id}, due_at={esc.due_at}")

            # Advance time past due_at
            class MockFutureDt(datetime):
                @classmethod
                def utcnow(cls):
                    return esc.due_at + timedelta(hours=1)

            # Advance time while anomaly is active: FR-7.6 defers execution
            with patch("services.escalation_manager.datetime", MockFutureDt):
                process_escalations(db)

            db.refresh(esc)
            assert esc.status == "pending", f"Expected deferred pending escalation due to active anomaly, got {esc.status}"
            print("  PASS: FR-7.6 Anomaly exclusion verified: escalation deferred while EC2 anomaly is active.")

            # Resolve the anomaly and process again
            for a in anoms:
                a.is_resolved = True
            db.commit()

            with patch("services.escalation_manager.datetime", MockFutureDt):
                process_escalations(db)

            db.refresh(esc)
            assert esc.status == "resolved", f"Expected resolved escalation, got {esc.status}"
            log = db.query(RemediationLog).filter(RemediationLog.resource_id == idle_rec.resource_id).first()
            assert log is not None and log.status == "simulated"
            print(f"  PASS: RemediationLog written with status='simulated', escalation closed.")

        elif label == "Azure":
            # Assert Azure demo account has ONLY AzureVM
            non_az_res = db.query(Resource).filter(Resource.account_id == demo_acc.id, Resource.service_type != "AzureVM").count()
            non_az_cost = db.query(CostRecord).filter(CostRecord.account_id == demo_acc.id, CostRecord.service_type != "AzureVM").count()
            assert non_az_res == 0, f"Azure demo account contains non-AzureVM resources: {non_az_res}"
            assert non_az_cost == 0, f"Azure demo account contains non-AzureVM cost records: {non_az_cost}"
            print("  PASS: Provider separation: Azure demo account has ONLY AzureVM resources and cost records.")

            assert demo_acc.grace_period_hours == 1, f"Expected grace_period_hours=1, got {demo_acc.grace_period_hours}"
            winner_mape = comp.get("poly_mape") if comp.get("winner") == "Polynomial Regression" else comp.get("hw_mape")
            assert 3.0 <= winner_mape <= 12.0, f"Expected Azure winner MAPE 3-12%, got {winner_mape}"

            anoms = db.query(Anomaly).filter(Anomaly.account_id == demo_acc.id).all()
            print(f"  Anomalies ({len(anoms)}):")
            for a in anoms:
                print(f"    - {a.service_type} on {a.record_date}: z={a.z_score:.2f} sev={a.severity} driver={a.driver_service}")
            assert len(anoms) <= 4, f"Expected <= 4 anomalies, got {len(anoms)}"
            for a in anoms:
                assert a.severity in ["warning", "critical"], f"Unexpected severity {a.severity}"
                assert (datetime.now(timezone.utc).date() - a.record_date).days <= 16, f"Anomaly too early in history: {a.record_date}"

            az_anom = [a for a in anoms if a.service_type == "AzureVM"]
            tot_anom = [a for a in anoms if a.service_type == "TOTAL"]
            assert len(az_anom) >= 1 and len(tot_anom) >= 1, "AzureVM and TOTAL must be flagged"
            for a in tot_anom:
                assert a.driver_service == "AzureVM", f"Expected driver AzureVM, got {a.driver_service}"

            # Idle AzureVM simulation
            idle_az = db.query(Recommendation).filter(
                Recommendation.account_id == demo_acc.id,
                Recommendation.issue == "Idle AzureVM"
            ).first()
            assert idle_az is not None, "Expected Idle AzureVM recommendation"
            sim_az = run_simulation(db, demo_acc.id, idle_az.id)
            print(f"  Simulation on idle AzureVM: baseline=${sim_az.baseline_30d_usd}, simulated=${sim_az.simulated_30d_usd}, delta=${sim_az.delta_usd}")

    print("\n[Check 4] Determinism check (2 consecutive generations)")
    reset_demo_account(db, acc_aws)
    res_1 = db.query(Resource.resource_id, Resource.estimated_monthly_cost).filter(Resource.account_id == acc_aws.id).order_by(Resource.resource_id).all()
    costs_1 = db.query(CostRecord.record_date, CostRecord.service_type, CostRecord.daily_cost_usd).filter(CostRecord.account_id == acc_aws.id).order_by(CostRecord.record_date, CostRecord.service_type).all()
    hash_1 = hashlib.sha256(json.dumps([(r[0], r[1]) for r in res_1] + [(str(c[0]), c[1], c[2]) for c in costs_1]).encode()).hexdigest()

    reset_demo_account(db, acc_aws)
    res_2 = db.query(Resource.resource_id, Resource.estimated_monthly_cost).filter(Resource.account_id == acc_aws.id).order_by(Resource.resource_id).all()
    costs_2 = db.query(CostRecord.record_date, CostRecord.service_type, CostRecord.daily_cost_usd).filter(CostRecord.account_id == acc_aws.id).order_by(CostRecord.record_date, CostRecord.service_type).all()
    hash_2 = hashlib.sha256(json.dumps([(r[0], r[1]) for r in res_2] + [(str(c[0]), c[1], c[2]) for c in costs_2]).encode()).hexdigest()

    assert hash_1 == hash_2, f"Hashes mismatch: {hash_1} vs {hash_2}"
    print(f"  PASS: Identical dataset generated across runs. Hash={hash_1[:16]}")

    print("\n[Check 5] Idempotence check (ensure x2, reset x2)")
    ensure_demo_accounts(db, user.id)
    ensure_demo_accounts(db, user.id)
    reset_demo_account(db, acc_aws)
    reset_demo_account(db, acc_aws)
    demo_count = db.query(CloudAccount).filter(CloudAccount.user_id == user.id, CloudAccount.name.like("Demo %")).count()
    assert demo_count == 2, f"Expected 2 demo accounts, got {demo_count}"
    print(f"  PASS: Exactly {demo_count} demo accounts per user after repeated ensure/reset.")

    print("\n[Check 6] TestClient DELETE on demo account (403 test)")
    res_del = client.delete(f"/accounts/{acc_aws.id}", headers=headers)
    assert res_del.status_code == 403, f"Expected 403, got {res_del.status_code} ({res_del.text})"
    acc_check = db.query(CloudAccount).filter(CloudAccount.id == acc_aws.id).first()
    assert acc_check is not None, "Demo account was deleted"
    demo_res_count = db.query(Resource).filter(Resource.account_id == acc_aws.id).count()
    assert demo_res_count > 0, "Demo rows were deleted"
    print(f"  PASS: DELETE on demo account returned 403 Forbidden; demo rows preserved.")

    # Legacy account check if running against DB copy
    legacy_id = "00000000-0000-0000-0000-demoaccount01"
    legacy_acc = db.query(CloudAccount).filter(CloudAccount.id == legacy_id).first()
    if legacy_acc:
        print(f"\n[Legacy Account Inspection: {legacy_id}]")
        b_res = db.query(Resource).filter(Resource.account_id == legacy_id).count()
        b_cost = db.query(CostRecord).filter(CostRecord.account_id == legacy_id).count()
        b_rec = db.query(Recommendation).filter(Recommendation.account_id == legacy_id).count()
        b_anom = db.query(Anomaly).filter(Anomaly.account_id == legacy_id).count()
        print(f"  BEFORE reset: resources={b_res}, costs={b_cost}, recs={b_rec}, anoms={b_anom}")
        reset_demo_account(db, legacy_acc)
        a_res = db.query(Resource).filter(Resource.account_id == legacy_id).count()
        a_cost = db.query(CostRecord).filter(CostRecord.account_id == legacy_id).count()
        a_rec = db.query(Recommendation).filter(Recommendation.account_id == legacy_id).count()
        a_anom = db.query(Anomaly).filter(Anomaly.account_id == legacy_id).count()
        print(f"  AFTER reset:  resources={a_res}, costs={a_cost}, recs={a_rec}, anoms={a_anom}")
    else:
        print(f"\n[Legacy Account: {legacy_id} not present in this in-memory test DB]")

    db.close()
    print("\nALL 6 CHECKS PASSED.")


def main():
    # 1. Run in-memory
    mem_engine = build_test_engine("sqlite:///:memory:")
    run_suite(mem_engine, is_copy_db=False)

    # 2. Run on copy of live DB if DATABASE_URL points to a copy
    copy_url = os.environ.get("DATABASE_URL")
    if copy_url and not copy_url.endswith("/cloud_cost.db"):
        print("\n\n" + "#" * 60)
        print(f"RUNNING SUITE ON COPY OF LIVE DB: {copy_url}")
        print("#" * 60)
        copy_engine = build_test_engine(copy_url)
        run_suite(copy_engine, is_copy_db=True)


if __name__ == "__main__":
    main()
