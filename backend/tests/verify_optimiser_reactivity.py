"""
backend/tests/verify_optimiser_reactivity.py
Verification suite for Savings Plan Optimiser usage-behavior reactivity (Item 2).
Uses in-memory SQLite with PRAGMA foreign_keys=ON.
No live DB writes, no cloud calls.
"""
import os
import sys
import uuid
import numpy as np
from datetime import datetime, date, timedelta, timezone
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Bootstrap sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import Base
from models.user import User
from models.account import CloudAccount
from models.resource import Resource
from models.cost_record import CostRecord, Recommendation
from models.anomaly import Anomaly
from services.demo_data import ensure_demo_accounts, reset_demo_account
from routes.savings_optimiser import compute_savings_plans, get_savings_plans, ILLUSTRATIVE_BEHAVIOR_HEURISTICS


def build_test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    print(f"Database Engine Path: {engine.url}", flush=True)

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    return db


def run_suite():
    print("=" * 70)
    print("RUNNING VERIFICATION: Savings Optimiser Reactivity (Item 2)")
    print("=" * 70)

    db = build_test_db()

    # Create test user and accounts
    test_user = User(
        id=str(uuid.uuid4()),
        email="optimiser_test@example.com",
        password_hash="dummy123"
    )
    db.add(test_user)
    db.commit()

    acc_aws, acc_azure = ensure_demo_accounts(db, test_user.id)
    reset_demo_account(db, acc_aws)
    reset_demo_account(db, acc_azure)

    acc_real_aws = CloudAccount(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        name="Mock Real AWS",
        provider="aws",
        region="us-east-1",
        access_key_id="AKIA_TEST",
        encrypted_secret_key="secret"
    )
    acc_real_azure = CloudAccount(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        name="Mock Real Azure",
        provider="azure",
        region="eastus",
        tenant_id="tenant",
        client_id="client",
        encrypted_client_secret="secret",
        subscription_id="sub"
    )
    db.add_all([acc_real_aws, acc_real_azure])
    db.commit()

    # ------------------------------------------------------------------
    # 1. Fresh Demo: EC2 and AzureVM both steady
    # ------------------------------------------------------------------
    print("\n[Check 1] Fresh Demo: EC2 and AzureVM steady baseline")
    # Resolve seeded demo anomalies to evaluate baseline steady commitment recommendations
    db.query(Anomaly).filter(Anomaly.account_id.in_([acc_aws.id, acc_azure.id])).update({"is_resolved": True})
    db.commit()

    plans_aws = compute_savings_plans(db, acc_aws)
    plans_az = compute_savings_plans(db, acc_azure)

    ec2 = next(s for s in plans_aws["services"] if s["service"] == "EC2")
    az_vm = next(s for s in plans_az["services"] if s["service"] == "AzureVM")

    print(f"  EC2: CV={ec2['cv']:.3f}, coverage={ec2['coverage_pct']}%, rec={ec2['recommended']}")
    print(f"  AzureVM: CV={az_vm['cv']:.3f}, coverage={az_vm['coverage_pct']}%, rec={az_vm['recommended']}")

    assert ec2["cv"] <= 0.10, f"Expected EC2 CV <= 0.10, got {ec2['cv']}"
    assert ec2["coverage_pct"] >= 80, f"Expected EC2 coverage >= 80%, got {ec2['coverage_pct']}%"
    assert ec2["recommended"] in ["1y_partial_upfront", "1y_all_upfront"]
    assert ec2["options"][ec2["recommended"]]["saving_vs_payg_12m"] > 0
    assert ec2["preview_if_resolved"] is None

    assert az_vm["cv"] <= 0.10, f"Expected AzureVM CV <= 0.10, got {az_vm['cv']}"
    assert az_vm["coverage_pct"] >= 80, f"Expected AzureVM coverage >= 80%, got {az_vm['coverage_pct']}%"
    assert az_vm["recommended"] in ["1y_partial_upfront", "1y_all_upfront"]
    assert az_vm["options"][az_vm["recommended"]]["saving_vs_payg_12m"] > 0
    print("  PASS: Fresh demo has steady CV <= 0.10, coverage >= 80%, net savings > 0.")

    # ------------------------------------------------------------------
    # 2. Simulated drop (trend <= -0.10): triggers 1y_no_upfront even if CV is low
    # ------------------------------------------------------------------
    print("\n[Check 2] Simulated drop (trend <= -10%) triggers 1y_no_upfront")
    # Apply a smooth downward drift across the 30 days to keep CV low (<= 0.25) while trend <= -10%
    all_ec2 = (
        db.query(CostRecord)
        .filter(CostRecord.account_id == acc_aws.id, CostRecord.service_type == "EC2")
        .order_by(CostRecord.record_date.desc())
        .limit(30)
        .all()
    )
    all_ec2.sort(key=lambda x: x.record_date)
    # Downward linear slope
    for idx, r in enumerate(all_ec2):
        scale = 1.0 - (0.20 * idx / len(all_ec2))  # gradual 20% drop from oldest to newest
        r.daily_cost_usd = round(r.daily_cost_usd * scale, 4)
    db.commit()

    plans_drop = compute_savings_plans(db, acc_aws)
    ec2_drop = next(s for s in plans_drop["services"] if s["service"] == "EC2")
    print(f"  EC2 after drop: trend={ec2_drop['trend_pct']}%, CV={ec2_drop['cv']}, rec={ec2_drop['recommended']}")
    assert ec2_drop["cv"] <= 0.25, f"Expected CV <= 0.25 for clean trend test, got {ec2_drop['cv']}"
    assert ec2_drop["trend_pct"] <= -10.0, f"Expected trend <= -10.0%, got {ec2_drop['trend_pct']}%"
    assert ec2_drop["recommended"] == "1y_no_upfront", f"Expected 1y_no_upfront, got {ec2_drop['recommended']}"
    assert "trend" in ec2_drop["reason"].lower() or "declining" in ec2_drop["reason"].lower()
    print("  PASS: Simulated drop triggers 1y_no_upfront with trend explanation.")

    # ------------------------------------------------------------------
    # 3. Simulated drift / volatile usage (cv > 0.25): triggers 1y_no_upfront
    # ------------------------------------------------------------------
    print("\n[Check 3] Volatile usage (CV > 0.25) triggers 1y_no_upfront & coverage < 85%")
    # Apply alternating +/- 40% on AzureVM over 16 days
    today = date.today()
    for d in range(16, -1, -1):
        r_date = today - timedelta(days=d)
        rec = (
            db.query(CostRecord)
            .filter(CostRecord.account_id == acc_azure.id, CostRecord.service_type == "AzureVM", CostRecord.record_date == r_date)
            .first()
        )
        if rec:
            factor = 1.40 if (d % 2 == 0) else 0.60
            rec.daily_cost_usd = round(rec.daily_cost_usd * factor, 4)
    db.commit()

    plans_vol = compute_savings_plans(db, acc_azure)
    az_vol = next(s for s in plans_vol["services"] if s["service"] == "AzureVM")
    print(f"  AzureVM volatile: CV={az_vol['cv']}, coverage={az_vol['coverage_pct']}%, rec={az_vol['recommended']}")
    assert az_vol["cv"] > 0.25, f"Expected CV > 0.25, got {az_vol['cv']}"
    assert az_vol["recommended"] == "1y_no_upfront", f"Expected 1y_no_upfront, got {az_vol['recommended']}"
    assert az_vol["coverage_pct"] < 85, f"Expected coverage < 85%, got {az_vol['coverage_pct']}%"
    assert "volatile" in az_vol["reason"].lower() or "cv" in az_vol["reason"].lower()
    print("  PASS: Volatile usage (CV > 0.25) triggers 1y_no_upfront and lower coverage floor.")

    # ------------------------------------------------------------------
    # 4. Anomaly hold: recent unresolved anomaly in last 14 days
    # ------------------------------------------------------------------
    print("\n[Check 4] Anomaly hold on recent unresolved spike")
    # Reset AWS account first and resolve baseline anomalies
    reset_demo_account(db, acc_aws)
    db.query(Anomaly).filter(Anomaly.account_id == acc_aws.id).update({"is_resolved": True})
    db.commit()

    anom_date = today - timedelta(days=3)
    spike_anom = Anomaly(
        account_id=acc_aws.id,
        service_type="EC2",
        record_date=anom_date,
        actual_cost=45.0,
        forecast_cost=10.0,
        residual=35.0,
        z_score=6.5,
        severity="critical",
        direction="spike",
        driver_service="EC2",
        is_resolved=False
    )
    db.add(spike_anom)
    db.commit()

    plans_anom = compute_savings_plans(db, acc_aws)
    ec2_anom = next(s for s in plans_anom["services"] if s["service"] == "EC2")
    print(f"  EC2 with anomaly: rec={ec2_anom['recommended']}, preview={ec2_anom['preview_if_resolved']}")
    assert ec2_anom["recommended"] == "pay_as_you_go"
    assert str(anom_date) in ec2_anom["reason"]
    assert ec2_anom["preview_if_resolved"] is not None
    assert ec2_anom["preview_if_resolved"]["recommended"] in ["1y_partial_upfront", "1y_all_upfront"]
    print("  PASS: Anomaly hold sets recommended to pay_as_you_go with preview_if_resolved.")

    # ------------------------------------------------------------------
    # 5. Resolve anomaly -> hold lifts, preview_if_resolved is None
    # ------------------------------------------------------------------
    print("\n[Check 5] Resolve anomaly -> hold lifts")
    spike_anom.is_resolved = True
    db.commit()

    plans_res = compute_savings_plans(db, acc_aws)
    ec2_res = next(s for s in plans_res["services"] if s["service"] == "EC2")
    print(f"  EC2 resolved: rec={ec2_res['recommended']}, preview={ec2_res['preview_if_resolved']}")
    assert ec2_res["recommended"] in ["1y_partial_upfront", "1y_all_upfront"]
    assert ec2_res["preview_if_resolved"] is None
    print("  PASS: Resolving anomaly lifts hold; preview_if_resolved is None.")

    # ------------------------------------------------------------------
    # 6. Fewer than 14 days of history: is_new=True, recommended=pay_as_you_go
    # ------------------------------------------------------------------
    print("\n[Check 6] Fewer than 14 days history -> is_new=True, PAYG")
    # Delete older records of EC2 leaving only 8 days
    all_ec2 = (
        db.query(CostRecord)
        .filter(CostRecord.account_id == acc_aws.id, CostRecord.service_type == "EC2")
        .order_by(CostRecord.record_date.desc())
        .all()
    )
    for r in all_ec2[8:]:
        db.delete(r)
    db.commit()

    plans_new = compute_savings_plans(db, acc_aws)
    ec2_new = next(s for s in plans_new["services"] if s["service"] == "EC2")
    print(f"  EC2 with 8 days: is_new={ec2_new['is_new']}, rec={ec2_new['recommended']}, reason={ec2_new['reason']}")
    assert ec2_new["is_new"] is True
    assert ec2_new["recommended"] == "pay_as_you_go"
    assert "fewer than 14 days" in ec2_new["reason"].lower()
    print("  PASS: Fewer than 14 days marks is_new=True and recommends pay_as_you_go.")

    # ------------------------------------------------------------------
    # 7. Reset returns to baseline state
    # ------------------------------------------------------------------
    print("\n[Check 7] Reset returns to baseline state")
    reset_demo_account(db, acc_aws)
    reset_demo_account(db, acc_azure)
    db.query(Anomaly).filter(Anomaly.account_id.in_([acc_aws.id, acc_azure.id])).update({"is_resolved": True})
    db.commit()

    plans_rst_aws = compute_savings_plans(db, acc_aws)
    plans_rst_az = compute_savings_plans(db, acc_azure)
    ec2_rst = next(s for s in plans_rst_aws["services"] if s["service"] == "EC2")
    az_rst = next(s for s in plans_rst_az["services"] if s["service"] == "AzureVM")

    assert ec2_rst["cv"] <= 0.10
    assert ec2_rst["coverage_pct"] >= 80
    assert ec2_rst["recommended"] in ["1y_partial_upfront", "1y_all_upfront"]

    assert az_rst["cv"] <= 0.10
    assert az_rst["coverage_pct"] >= 80
    assert az_rst["recommended"] in ["1y_partial_upfront", "1y_all_upfront"]
    print("  PASS: Demo reset cleanly restores steady commitment recommendations.")

    # ------------------------------------------------------------------
    # 8. Real AWS/Azure accounts return 200 without error
    # ------------------------------------------------------------------
    print("\n[Check 8] Real accounts return valid response dict without error")
    real_aws_plans = get_savings_plans(account_id=acc_real_aws.id, current_user=test_user, db=db)
    real_az_plans = get_savings_plans(account_id=acc_real_azure.id, current_user=test_user, db=db)
    assert real_aws_plans["account_id"] == acc_real_aws.id
    assert real_az_plans["account_id"] == acc_real_azure.id
    print("  PASS: Real accounts return valid plans structure.")

    print("\n" + "=" * 70)
    print("ALL 8 CHECKS PASSED FOR ITEM 2 (SAVINGS OPTIMISER REACTIVITY)!")
    print("=" * 70)


if __name__ == "__main__":
    run_suite()
