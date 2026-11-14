"""
backend/tests/verify_azure_demo_services.py
Verification suite for Client Changes #4 Item 1:
- Azure demo expanded with AzureBlob, AzureSQL, and AzureFunctions
- Provider separation (AWS has 0 Azure* rows, Demo Azure has only Azure* types)
- Resources by service type
- Recommendations by issue
- Anomalies and driver attribution
- Forecast comparison & winner MAPE
- Costs explain narratives for the 4 Azure services
- What-If simulations (Blob delete, SQL pause, Function delete)
- Savings Optimiser eligibility (AzureVM, AzureSQL eligible; AzureBlob, AzureFunctions no commitment)
- Real AWS and Real Azure accounts return 200
"""

import sys
import os
import uuid
import json
import hashlib
from datetime import datetime, date, timedelta, timezone

# Bootstrap sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models.user import User
from models.account import CloudAccount
from models.resource import Resource
from models.cost_record import CostRecord, Recommendation
from models.anomaly import Anomaly
from services.security import create_access_token
from services.demo_data import ensure_demo_accounts, reset_demo_account, generate_demo_resources, seed_demo_history
from services.cleanup_advisor import generate_recommendations
from services.savings_plan_optimiser import generate_sp_recommendations
from services.anomaly_detector import detect_anomalies
from routes.predictions import get_predictions
from routes.costs import explain_costs
from routes.simulations import simulate_resource, ResourceSimulateRequest
from routes.savings_optimiser import get_savings_plans


def build_test_environment():
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
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSession()
    return db


def run_suite():
    print("=" * 70)
    print("RUNNING VERIFICATION: Azure Demo Services Expansion (Item 1)")
    print("=" * 70)

    db = build_test_environment()

    # 1. Setup User and Accounts
    test_user = User(
        id=str(uuid.uuid4()),
        email="azure_client@example.com",
        password_hash="fakehash123"
    )
    db.add(test_user)
    db.commit()

    acc_aws, acc_azure = ensure_demo_accounts(db, test_user.id)
    reset_demo_account(db, acc_aws)
    reset_demo_account(db, acc_azure)

    # Add mock real accounts to test 200 response
    acc_real_aws = CloudAccount(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        name="Real AWS Reader",
        provider="aws",
        region="us-east-1",
        access_key_id="AKIA_REAL_MOCK",
        encrypted_secret_key="mock_secret"
    )
    acc_real_azure = CloudAccount(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        name="Real Azure Reader",
        provider="azure",
        region="eastus",
        tenant_id="mock_tenant",
        client_id="mock_client",
        encrypted_client_secret="mock_secret",
        subscription_id="mock_sub"
    )
    db.add_all([acc_real_aws, acc_real_azure])
    db.commit()

    print("[Check 1] Provider separation & Resource counts by service type")
    aws_az_res = db.query(Resource).filter(Resource.account_id == acc_aws.id, Resource.service_type.like("Azure%")).count()
    aws_az_costs = db.query(CostRecord).filter(CostRecord.account_id == acc_aws.id, CostRecord.service_type.like("Azure%")).count()
    assert aws_az_res == 0, f"AWS demo account contains {aws_az_res} Azure resources"
    assert aws_az_costs == 0, f"AWS demo account contains {aws_az_costs} Azure cost records"
    print(f"  PASS: AWS Demo has ZERO Azure* resources/costs (res={aws_az_res}, costs={aws_az_costs}).")

    az_resources = db.query(Resource).filter(Resource.account_id == acc_azure.id).all()
    non_az_res = [r for r in az_resources if not r.service_type.startswith("Azure")]
    assert len(non_az_res) == 0, f"Demo Azure contains non-Azure resources: {non_az_res}"
    print(f"  PASS: Demo Azure contains ONLY Azure* resources ({len(az_resources)} total).")

    res_by_type = {}
    for r in az_resources:
        res_by_type[r.service_type] = res_by_type.get(r.service_type, 0) + 1
    print(f"  Demo Azure Resources by service type: {res_by_type}")
    assert res_by_type.get("AzureVM") == 4, f"Expected 4 AzureVMs, got {res_by_type.get('AzureVM')}"
    assert res_by_type.get("AzureBlob") == 3, f"Expected 3 AzureBlobs, got {res_by_type.get('AzureBlob')}"
    assert res_by_type.get("AzureSQL") == 3, f"Expected 3 AzureSQL DBs, got {res_by_type.get('AzureSQL')}"
    assert res_by_type.get("AzureFunctions") == 2, f"Expected 2 AzureFunctions apps, got {res_by_type.get('AzureFunctions')}"
    print("  PASS: Exact resource distribution confirmed (4 VMs, 3 Blobs, 3 SQL, 2 Functions).")

    print("\n[Check 2] Cleanup Advisor Recommendations by Issue")
    recs = db.query(Recommendation).filter(Recommendation.account_id == acc_azure.id, Recommendation.is_resolved == False).all()
    recs_by_issue = {}
    for rec in recs:
        recs_by_issue[rec.issue] = recs_by_issue.get(rec.issue, 0) + 1
    print(f"  Demo Azure Recommendations ({len(recs)} total):")
    for issue, count in sorted(recs_by_issue.items()):
        print(f"    - {issue}: {count}")

    # Assert expected issues are present
    expected_issues = [
        "Idle AzureVM",
        "Underutilized AzureVM",
        "Empty Azure Blob Storage",
        "Large Unused Blob Storage",
        "Idle Azure SQL Database",
        "Paused Azure SQL Database (storage cost)",
        "Unused Azure Function App"
    ]
    for exp in expected_issues:
        assert exp in recs_by_issue, f"Expected recommendation issue '{exp}' missing from {list(recs_by_issue.keys())}"
    print("  PASS: All expected Azure cleanup recommendation issues generated.")

    print("\n[Check 3] Anomalies, Driver Attribution, and Timing")
    anoms = db.query(Anomaly).filter(Anomaly.account_id == acc_azure.id).all()
    print(f"  Demo Azure Anomalies ({len(anoms)}):")
    for a in anoms:
        print(f"    - {a.service_type} on {a.record_date}: z={a.z_score:.2f}, sev={a.severity}, driver={a.driver_service}")
    assert len(anoms) <= 4, f"Expected <= 4 anomalies, got {len(anoms)}"
    for a in anoms:
        assert a.severity in ["warning", "critical"], f"Unexpected anomaly severity: {a.severity}"
        days_ago = (date.today() - a.record_date).days
        assert days_ago <= 16, f"Anomaly occurred in the first 14 days of history: {a.record_date} ({days_ago} days ago)"

    vm_anoms = [a for a in anoms if a.service_type == "AzureVM"]
    tot_anoms = [a for a in anoms if a.service_type == "TOTAL"]
    assert len(vm_anoms) >= 1, "AzureVM spike must be flagged"
    assert len(tot_anoms) >= 1, "TOTAL spike must be flagged"
    for a in tot_anoms:
        assert a.driver_service == "AzureVM", f"Expected driver AzureVM, got {a.driver_service}"
    print("  PASS: Anomaly targets met: <=4 total, driver AzureVM, none in first 14 days.")

    print("\n[Check 4] Forecast Model Comparison & Winner MAPE", flush=True)
    fc_data = get_predictions(account_id=acc_azure.id, current_user=test_user, db=db)
    comp = fc_data.get("model_comparison", {})
    winner = comp.get("winner")
    poly_mape = comp.get("poly_mape")
    hw_mape = comp.get("hw_mape")
    print(f"  Forecast: winner='{winner}', poly_mape={poly_mape}%, hw_mape={hw_mape}%", flush=True)
    winner_mape = poly_mape if comp.get("winner_key") == "poly" else hw_mape
    assert 3.0 <= winner_mape <= 12.0, f"Winner MAPE {winner_mape}% outside expected 3-12% window"
    print("  PASS: Forecast winner MAPE within 3-12% range.", flush=True)

    print("\n[Check 5] Costs Explain Narratives for 4 Azure Services")
    exp_data = explain_costs(account_id=acc_azure.id, current_user=test_user, db=db)
    svcs = exp_data.get("services", [])
    svc_names = {s["service"] for s in svcs}
    assert svc_names == {"AzureVM", "AzureSQL", "AzureBlob", "AzureFunctions"}, f"Unexpected service set: {svc_names}"
    for s in svcs:
        assert s.get("narrative"), f"Missing narrative for service {s['service']}"
        assert len(s.get("top_resources", [])) >= 1, f"Missing top resources for {s['service']}"
        print(f"  Explain narrative for {s['service']}: {s['narrative'][:80]}...")
    print("  PASS: Deterministic explain narratives generated for all 4 Azure services.")

    print("\n[Check 6] What-If Simulation per Resource (Blob delete, SQL pause, Function delete)")
    # 6.1 Blob Delete
    blob_res = next(r for r in az_resources if r.service_type == "AzureBlob" and r.storage_size_gb and r.storage_size_gb > 500)
    blob_body = simulate_resource(ResourceSimulateRequest(resource_id=blob_res.resource_id, action="delete"), current_user=test_user, db=db)
    assert blob_body["monthly_saving"] == blob_res.estimated_monthly_cost
    assert blob_body["remaining_cost_after_action"] == 0.0
    print(f"  Blob Delete: monthly_saving=${blob_body['monthly_saving']}, remaining=${blob_body['remaining_cost_after_action']}")

    # 6.2 SQL Pause
    sql_res = next(r for r in az_resources if r.service_type == "AzureSQL" and r.status == "running" and r.cpu_utilization_avg < 1.0)
    sql_body = simulate_resource(ResourceSimulateRequest(resource_id=sql_res.resource_id, action="stop"), current_user=test_user, db=db)
    assert sql_body["remaining_cost_after_action"] > 0, "Storage cost must remain when SQL is paused"
    assert sql_body["monthly_saving"] > 0
    print(f"  SQL Pause: monthly_saving=${sql_body['monthly_saving']}, remaining_storage=${sql_body['remaining_cost_after_action']}")

    # 6.3 Function Delete
    fn_res = next(r for r in az_resources if r.service_type == "AzureFunctions" and (r.request_count or 0) > 0)
    fn_body = simulate_resource(ResourceSimulateRequest(resource_id=fn_res.resource_id, action="delete"), current_user=test_user, db=db)
    assert fn_body["monthly_saving"] == fn_res.estimated_monthly_cost
    assert fn_body["remaining_cost_after_action"] == 0.0
    print(f"  Function Delete: monthly_saving=${fn_body['monthly_saving']}, remaining=${fn_body['remaining_cost_after_action']}")
    print("  PASS: What-If simulations for Blob, SQL, and Functions verified.")

    print("\n[Check 7] Savings Optimiser Cards & Eligibility")
    plans_data = get_savings_plans(account_id=acc_azure.id, current_user=test_user, db=db)
    opt_svcs = plans_data.get("services", [])
    opt_map = {s["service"]: s for s in opt_svcs}

    assert "AzureVM" in opt_map and opt_map["AzureVM"]["has_commitment_option"] is True
    assert "AzureSQL" in opt_map and opt_map["AzureSQL"]["has_commitment_option"] is True
    assert "AzureBlob" in opt_map and opt_map["AzureBlob"]["has_commitment_option"] is False
    assert opt_map["AzureBlob"]["recommended"] == "No commitment option for this service"
    assert "AzureFunctions" in opt_map and opt_map["AzureFunctions"]["has_commitment_option"] is False
    assert opt_map["AzureFunctions"]["recommended"] == "No commitment option for this service"
    print("  PASS: Savings Optimiser cards: AzureVM & AzureSQL eligible; AzureBlob & AzureFunctions show 'No commitment option'.")

    print("\n[Check 8] Real Accounts Accessibility")
    exp_real_aws = explain_costs(account_id=acc_real_aws.id, current_user=test_user, db=db)
    assert exp_real_aws is not None
    exp_real_azure = explain_costs(account_id=acc_real_azure.id, current_user=test_user, db=db)
    assert exp_real_azure is not None
    print("  PASS: Real AWS and Real Azure accounts return 200 without side effects.")

    print("\n" + "=" * 70)
    print("ALL CHECKS PASSED FOR ITEM 1 (AZURE DEMO SERVICES EXPANSION)!")
    print("=" * 70)


if __name__ == "__main__":
    run_suite()
