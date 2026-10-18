"""
backend/verify_azure_fixes.py
Verification script for Item C: AzureVM observation window and metrics.
Uses an in-memory SQLite database to guarantee no writes to the live database.
"""

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models.user import User
from models.account import CloudAccount
from models.resource import Resource
from models.cost_record import CostRecord, Recommendation
from services import azure_collector
from services.cost_estimator import upsert_resources
from services.cleanup_advisor import generate_recommendations

def test_azure_fixes():
    # Create in-memory SQLite database
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    print("=== PART 1: Demo Azure Data Flow ===")
    user = User(id="user-demo", email="demo@example.com", password_hash="hash")
    db.add(user)
    db.commit()

    demo_acc = CloudAccount(
        id="acc-az-demo",
        user_id="user-demo",
        name="Azure Demo",
        provider="azure",
        encrypted_client_secret="",
    )
    db.add(demo_acc)
    db.commit()

    demo_resources = azure_collector.collect_demo_data()
    for r in demo_resources:
        r["account_id"] = demo_acc.id

    upsert_count = upsert_resources(db, demo_resources, [demo_acc.id])
    print(f"Upserted demo resources: {upsert_count}")

    generate_recommendations(db)
    recs = db.query(Recommendation).all()
    print(f"Generated recommendations count: {len(recs)}")
    for rec in recs:
        print(f"  Issue: {rec.issue} | Resource: {rec.resource_id} | Savings: ${rec.potential_savings_usd}")

    # Assertions for demo
    assert len(recs) == 2, f"Expected 2 recs, got {len(recs)}"
    idle_recs = [r for r in recs if r.issue == "Idle AzureVM"]
    assert len(idle_recs) == 2, f"Expected 2 Idle AzureVM recs, got {len(idle_recs)}"
    savings = sorted([r.potential_savings_usd for r in idle_recs])
    assert savings == [126.0, 294.0], f"Expected savings [126.0, 294.0], got {savings}"
    # Verify stopped VM got no recs
    stopped_recs = [r for r in recs if r.resource_id == "azure-vm-002"]
    assert len(stopped_recs) == 0, f"Expected 0 recs for stopped VM, got {len(stopped_recs)}"
    print("Demo Azure assertions passed successfully!")

    print("\n=== PART 2: Synthetic Cases ===")
    test_cases = [
        {"name": "cpu None", "cpu": None, "runtime": 200.0, "status": "running", "cost": 100.0, "expected_issue": None},
        {"name": "cpu 0.3 runtime 24", "cpu": 0.3, "runtime": 24.0, "status": "running", "cost": 100.0, "expected_issue": None},
        {"name": "cpu 0.3 runtime 200", "cpu": 0.3, "runtime": 200.0, "status": "running", "cost": 100.0, "expected_issue": "Idle AzureVM"},
        {"name": "cpu 3.0 runtime 200", "cpu": 3.0, "runtime": 200.0, "status": "running", "cost": 100.0, "expected_issue": "Underutilized AzureVM"},
        {"name": "cpu 0.0 runtime 200", "cpu": 0.0, "runtime": 200.0, "status": "running", "cost": 100.0, "expected_issue": "Idle AzureVM"},
    ]

    for tc in test_cases:
        # Reset DB tables
        db.query(Recommendation).delete()
        db.query(Resource).delete()
        db.commit()

        synth_res = [{
            "account_id": demo_acc.id,
            "resource_id": f"res-{tc['name'].replace(' ', '-')}",
            "resource_name": f"vm-{tc['name']}",
            "service_type": "AzureVM",
            "resource_type": "Standard_B1s",
            "region": "eastus",
            "status": tc["status"],
            "cpu_utilization_avg": tc["cpu"],
            "runtime_hours": tc["runtime"],
            "storage_size_gb": 32.0,
            "daily_cost_usd": tc["cost"] / 30.0,
            "estimated_monthly_cost": tc["cost"],
        }]
        upsert_resources(db, synth_res, [demo_acc.id])
        generate_recommendations(db)
        case_recs = db.query(Recommendation).all()

        if tc["expected_issue"] is None:
            assert len(case_recs) == 0, f"Case '{tc['name']}': expected 0 recs, got {len(case_recs)}"
            print(f"  Case '{tc['name']}': 0 recs as expected (PASSED)")
        else:
            assert len(case_recs) == 1, f"Case '{tc['name']}': expected 1 rec, got {len(case_recs)}"
            assert case_recs[0].issue == tc["expected_issue"], f"Case '{tc['name']}': expected {tc['expected_issue']}, got {case_recs[0].issue}"
            print(f"  Case '{tc['name']}': 1 rec '{case_recs[0].issue}' as expected (PASSED)")

    print("\nALL ITEM C TESTS PASSED!")

if __name__ == "__main__":
    test_azure_fixes()
