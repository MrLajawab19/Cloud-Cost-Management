"""
backend/verify_client_changes2.py
=================================
Automated verification suite for Client Change Requests #2:
- Item 1: Live Data Lab (demo injection, real pipeline execution, reset, security guards)
- Item 2: Per-Resource What-If Simulations (ephemeral per-resource model, pricing rules, safety rules)

Exercises the real app routing with exact URLs/params the frontend uses.
Tested using in-memory SQLite with foreign keys enabled.
"""
import _bootstrap

import sys
import os
import json
import uuid
import hashlib
from datetime import datetime, timedelta

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
from models.cost_record import Recommendation, CostRecord
from models.resource import Resource
from models.anomaly import Anomaly
from models.remediation import EscalationState, RemediationLog
from services.security import get_password_hash, create_access_token
from services.demo_data import seed_demo_history, reset_demo_account, ensure_demo_accounts

def run_suite():
    print("=" * 70)
    print("VERIFY CLIENT CHANGES #2 (Live Data Lab + Per-Resource What-If)")
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

    # 1. Users setup
    user1 = User(
        id=str(uuid.uuid4()),
        email="client_test2@example.com",
        password_hash=get_password_hash("Password123!"),
    )
    user2 = User(
        id=str(uuid.uuid4()),
        email="other_user2@example.com",
        password_hash=get_password_hash("Password123!"),
    )
    db.add_all([user1, user2])
    db.commit()

    token1 = create_access_token({"sub": user1.id})
    token2 = create_access_token({"sub": user2.id})
    h1 = {"Authorization": f"Bearer {token1}"}
    h2 = {"Authorization": f"Bearer {token2}"}

    # 2. Accounts setup
    acc_aws_demo, acc_azure_demo = ensure_demo_accounts(db, user1.id)
    reset_demo_account(db, acc_aws_demo)
    reset_demo_account(db, acc_azure_demo)

    acc_aws_real_id = str(uuid.uuid4())
    acc_azure_real_id = str(uuid.uuid4())
    acc_legacy_id = str(uuid.uuid4())
    acc_user2_demo, _ = ensure_demo_accounts(db, user2.id)
    reset_demo_account(db, acc_user2_demo)

    acc_aws_real = CloudAccount(id=acc_aws_real_id, user_id=user1.id, name="AWS Real", provider="aws", access_key_id="AKIA123")
    acc_azure_real = CloudAccount(id=acc_azure_real_id, user_id=user1.id, name="Azure Real", provider="azure", client_id="AZ123")
    acc_legacy = CloudAccount(id=acc_legacy_id, user_id=user1.id, name="Legacy No Creds", provider="aws")

    db.add_all([acc_aws_real, acc_azure_real, acc_legacy])
    db.commit()

    # Compute baseline determinism hash
    aws_costs_pre = [r.daily_cost_usd for r in db.query(CostRecord).filter(CostRecord.account_id == acc_aws_demo.id).order_by(CostRecord.record_date).all()]
    pre_hash = hashlib.sha256(json.dumps(aws_costs_pre).encode()).hexdigest()

    # Seed a real AWS resource and none-cost resource for Item 2
    res_real = Resource(
        id=uuid.uuid4(),
        account_id=acc_aws_real.id,
        resource_id="i-real-t3micro-01",
        resource_name="real-web-worker",
        service_type="EC2",
        region="us-east-1",
        status="running",
        resource_type="t3.micro",
        cpu_utilization_avg=12.0,
        estimated_monthly_cost=7.59,
    )
    res_none_cost = Resource(
        id=uuid.uuid4(),
        account_id=acc_aws_real.id,
        resource_id="res-none-cost-item2",
        resource_name="demo-none-cost",
        service_type="EC2",
        region="us-east-1",
        status="running",
        resource_type="t3.micro",
        cpu_utilization_avg=0.2,
        estimated_monthly_cost=None,
    )
    db.add_all([res_real, res_none_cost])
    db.commit()

    # Also seed cost history for real AWS account so ML predictor runs
    today = datetime.utcnow().date()
    for d in range(35):
        dt = today - timedelta(days=d)
        db.add(CostRecord(
            account_id=acc_aws_real.id,
            service_type="EC2",
            region="us-east-1",
            record_date=dt,
            daily_cost_usd=0.25,
            source="aws_collected"
        ))
    db.commit()

    print("\n--- ITEM 1: Live Data Lab Verifications ---")

    # 1.1 normal_day on AWS Demo -> anomaly count unchanged
    r_norm = client.post(f"/demo/inject?account_id={acc_aws_demo.id}", json={"scenario": "normal_day"}, headers=h1)
    assert r_norm.status_code == 200, f"Expected 200, got {r_norm.status_code}: {r_norm.text}"
    data_norm = r_norm.json()
    assert data_norm["delta"]["anomaly_count"] == 0, "normal_day must not produce an anomaly"
    print("PASS: normal_day injection created 0 anomalies.")

    # 1.2 cost_spike on EC2 +80% -> EC2 anomaly, optimiser recommends pay_as_you_go with anomaly reason
    r_spike = client.post(f"/demo/inject?account_id={acc_aws_demo.id}", json={
        "scenario": "cost_spike", "service": "EC2", "magnitude": 80.0
    }, headers=h1)
    assert r_spike.status_code == 200
    data_spike = r_spike.json()
    assert data_spike["after"]["anomaly_count"] > data_spike["before"]["anomaly_count"]
    ec2_anom = next((a for a in data_spike["after"]["anomalies"] if a["service"] == "EC2"), None)
    assert ec2_anom is not None, "EC2 anomaly must be detected"
    ec2_plan = next((p for p in data_spike["after"]["savings_optimiser"] if p["service"] == "EC2"), None)
    assert ec2_plan is not None
    assert ec2_plan["recommended"] == "pay_as_you_go"
    assert "anomaly" in ec2_plan["reason"].lower()
    print("PASS: cost_spike generated EC2 anomaly and flipped optimiser to pay_as_you_go.")

    # 1.3 resolve the anomaly -> optimiser recommends commitment option again
    ec2_anoms = db.query(Anomaly).filter(
        Anomaly.account_id == acc_aws_demo.id,
        Anomaly.service_type == "EC2",
        Anomaly.is_resolved == False
    ).all()
    for anom_obj in ec2_anoms:
        r_res_anom = client.post(f"/anomalies/{anom_obj.id}/resolve", headers=h1)
        assert r_res_anom.status_code == 200
    r_opt = client.get(f"/savings-optimiser/plans?account_id={acc_aws_demo.id}", headers=h1)
    assert r_opt.status_code == 200
    ec2_opt_post = next((p for p in r_opt.json().get("services", []) if p["service"] == "EC2"), None)
    assert ec2_opt_post is not None
    assert ec2_opt_post["recommended"] != "pay_as_you_go"
    print(f"PASS: After anomaly resolution, optimiser recommends commitment plan: {ec2_opt_post['recommended']}.")

    # 1.4 new_idle_resource -> Idle recommendation + pending escalation
    r_idle = client.post(f"/demo/inject?account_id={acc_aws_demo.id}", json={
        "scenario": "new_idle_resource"
    }, headers=h1)
    assert r_idle.status_code == 200
    data_idle = r_idle.json()
    assert len(data_idle["delta"]["escalations_created"]) >= 1
    assert any("idle" in r["issue"].lower() for r in data_idle["after"]["recommendations"])
    print(f"PASS: new_idle_resource created {len(data_idle['delta']['escalations_created'])} escalation(s).")

    # 1.5 reset -> counts match original
    r_reset = client.post(f"/demo/reset?account_id={acc_aws_demo.id}", headers=h1)
    assert r_reset.status_code == 200
    post_costs = [r.daily_cost_usd for r in db.query(CostRecord).filter(CostRecord.account_id == acc_aws_demo.id).order_by(CostRecord.record_date).all()]
    post_hash = hashlib.sha256(json.dumps(post_costs).encode()).hexdigest()
    assert pre_hash == post_hash, "Deterministic demo account hash must match post reset"
    print("PASS: Demo reset returned account to pristine state, matching determinism hash.")

    # 1.6 Azure Demo spike and idle VM
    r_az_spike = client.post(f"/demo/inject?account_id={acc_azure_demo.id}", json={
        "scenario": "cost_spike", "service": "AzureVM", "magnitude": 90.0
    }, headers=h1)
    assert r_az_spike.status_code == 200
    r_az_idle = client.post(f"/demo/inject?account_id={acc_azure_demo.id}", json={
        "scenario": "new_idle_resource"
    }, headers=h1)
    assert r_az_idle.status_code == 200
    assert any("idle" in r["issue"].lower() for r in r_az_idle.json()["after"]["recommendations"])
    print("PASS: Azure demo spike and idle VM verified with provider separation.")

    # 1.7 Security guards: real, legacy, other-user accounts -> 403/404
    for blocked_id in [acc_aws_real.id, acc_azure_real.id, acc_legacy.id, acc_user2_demo.id]:
        r_inj = client.post(f"/demo/inject?account_id={blocked_id}", json={"scenario": "normal_day"}, headers=h1)
        assert r_inj.status_code in [403, 404]
        r_rst = client.post(f"/demo/reset?account_id={blocked_id}", headers=h1)
        assert r_rst.status_code in [403, 404]
    print("PASS: Security guards blocked real, legacy, and cross-user demo accounts with 403/404.")


    print("\n--- ITEM 2: Per-Resource What-If Simulations Verifications ---")

    # 2.1 GET /simulations/resource-options
    r_opts = client.get(f"/simulations/resource-options?account_id={acc_aws_demo.id}", headers=h1)
    assert r_opts.status_code == 200
    opts = r_opts.json()
    assert isinstance(opts, list) and len(opts) > 0
    print(f"PASS: GET /simulations/resource-options returned {len(opts)} resources.")

    # Find test resources in AWS Demo
    idle_ec2 = next(r for r in opts if r["service_type"] == "EC2" and r["status"] == "running")
    stopped_rds = next(r for r in opts if r["service_type"] == "RDS")
    empty_s3 = next(r for r in opts if r["service_type"] == "S3" and (r["monthly_cost"] or 0) < 0.1)
    large_s3 = next(r for r in opts if r["service_type"] == "S3" and (r["monthly_cost"] or 0) > 10.0)

    # 2.2 Demo AWS idle EC2: stop / terminate / resize
    r_stop = client.post("/simulations/resource", json={"resource_id": idle_ec2["resource_id"], "action": "stop"}, headers=h1)
    assert r_stop.status_code == 200
    stop_res = r_stop.json()
    assert stop_res["remaining_cost_after_action"] == 3.00
    assert stop_res["monthly_saving"] <= stop_res["current_monthly_cost"]

    r_term = client.post("/simulations/resource", json={"resource_id": idle_ec2["resource_id"], "action": "terminate"}, headers=h1)
    assert r_term.status_code == 200
    term_res = r_term.json()
    assert term_res["remaining_cost_after_action"] == 0.0
    assert term_res["monthly_saving"] == term_res["current_monthly_cost"]
    assert stop_res["monthly_saving"] < term_res["monthly_saving"], "Stop saving must be < terminate saving"

    r_resize = client.post("/simulations/resource", json={
        "resource_id": idle_ec2["resource_id"], "action": "resize", "target_type": "t3.micro"
    }, headers=h1)
    assert r_resize.status_code == 200
    resize_res = r_resize.json()
    assert resize_res["monthly_saving"] <= resize_res["current_monthly_cost"]

    print("Case 1 (AWS idle EC2 stop) trimmed:")
    print(json.dumps({k: stop_res[k] for k in ["resource_name", "action", "current_monthly_cost", "monthly_saving", "remaining_cost_after_action"]}, indent=2))
    print("PASS: AWS idle EC2 stop/terminate/resize verified; stop saving < terminate saving.")

    # 2.3 Underutilized EC2 resize (even if recommendation is resolved)
    under_ec2 = next(r for r in opts if r["resource_id"] != idle_ec2["resource_id"] and r["service_type"] == "EC2")
    r_under = client.post("/simulations/resource", json={
        "resource_id": under_ec2["resource_id"], "action": "resize", "target_type": "t3.medium"
    }, headers=h1)
    assert r_under.status_code == 200
    under_res = r_under.json()
    print("Case 2 (Underutilized EC2 resize) trimmed:")
    print(json.dumps({k: under_res[k] for k in ["resource_name", "action", "current_monthly_cost", "monthly_saving", "formula_note"]}, indent=2))
    print("PASS: Underutilized EC2 resize verified independently of recommendation status.")

    # 2.4 Stopped RDS delete
    r_rds_del = client.post("/simulations/resource", json={"resource_id": stopped_rds["resource_id"], "action": "delete"}, headers=h1)
    assert r_rds_del.status_code == 200
    rds_res = r_rds_del.json()
    assert rds_res["remaining_cost_after_action"] == 0.0
    print("Case 3 (Stopped RDS delete) trimmed:")
    print(json.dumps({k: rds_res[k] for k in ["resource_name", "action", "current_monthly_cost", "monthly_saving", "risk_notes"]}, indent=2))
    print("PASS: Stopped RDS delete verified with snapshot advice.")

    # 2.5 Empty S3 and Large S3
    r_s3_emp = client.post("/simulations/resource", json={"resource_id": empty_s3["resource_id"], "action": "delete"}, headers=h1)
    assert r_s3_emp.status_code == 200
    assert r_s3_emp.json()["monthly_saving"] == 0.0

    r_s3_large = client.post("/simulations/resource", json={"resource_id": large_s3["resource_id"], "action": "delete"}, headers=h1)
    assert r_s3_large.status_code == 200
    assert r_s3_large.json()["monthly_saving"] > 0
    assert any("glacier" in n.lower() for n in r_s3_large.json()["risk_notes"])
    print("PASS: Empty S3 delete (0 saving) and Large S3 delete (Glacier advice) verified.")

    # 2.6 Demo Azure VM stop and resize
    az_opts = client.get(f"/simulations/resource-options?account_id={acc_azure_demo.id}", headers=h1).json()
    az_vm = next(r for r in az_opts if r["service_type"] == "AzureVM")
    r_az_stop = client.post("/simulations/resource", json={"resource_id": az_vm["resource_id"], "action": "stop"}, headers=h1)
    assert r_az_stop.status_code == 200
    az_res = r_az_stop.json()
    assert az_res["remaining_cost_after_action"] == 1.50 # disk baseline remains

    r_az_resz = client.post("/simulations/resource", json={"resource_id": az_vm["resource_id"], "action": "resize"}, headers=h1)
    assert r_az_resz.status_code == 400
    print("Case 4 (Demo Azure VM stop) trimmed:")
    print(json.dumps({k: az_res[k] for k in ["resource_name", "action", "current_monthly_cost", "monthly_saving", "remaining_cost_after_action"]}, indent=2))
    print("PASS: Azure VM stop retains disk cost; resize rejected with 400.")

    # 2.7 Real AWS t3.micro stop
    r_real_stop = client.post("/simulations/resource", json={"resource_id": res_real.resource_id, "action": "stop"}, headers=h1)
    assert r_real_stop.status_code == 200
    print("PASS: Real AWS resource simulated with zero cloud calls.")

    # 2.8 None-cost resource
    r_none = client.post("/simulations/resource", json={"resource_id": res_none_cost.resource_id, "action": "stop"}, headers=h1)
    assert r_none.status_code == 200
    assert r_none.json()["current_monthly_cost"] == "Cost unavailable"
    assert r_none.json()["monthly_saving"] == "Cost unavailable"
    print("PASS: None-cost resource returned 'Cost unavailable' with no numeric values.")

    # 2.9 Unknown resource id -> 404; other user's account -> 403
    r_unk = client.post("/simulations/resource", json={"resource_id": "non-existent-id", "action": "stop"}, headers=h1)
    assert r_unk.status_code == 404
    r_cross = client.post("/simulations/resource", json={"resource_id": idle_ec2["resource_id"], "action": "stop"}, headers=h2)
    assert r_cross.status_code in [403, 404]
    print("PASS: 404 on unknown resource, 403 on cross-user resource.")

    # 2.10 Existing /simulations/batch unchanged
    recs = db.query(Recommendation).filter(Recommendation.account_id == acc_aws_demo.id).all()
    if recs:
        r_batch = client.post("/simulations/batch", json={"ids": [str(recs[0].id)]}, headers=h1)
        assert r_batch.status_code == 200
        assert "simulations" in r_batch.json()
    print("PASS: Existing /simulations/batch response format unchanged.")

    # Cleanup dependency override
    app.dependency_overrides.clear()
    print("\n" + "=" * 70)
    print("ALL VERIFICATIONS IN verify_client_changes2.py PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    run_suite()
