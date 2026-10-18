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


def test_azure_cost_handling():
    print("\n=== PART 3: Item A Azure Cost Handling ===")
    import time
    from services.azure_collector import query_cost_management, _COST_CACHE
    from services.cost_estimator import record_daily_costs
    from azure.core.exceptions import HttpResponseError
    
    _COST_CACHE.clear()
    recorded_sleeps = []
    
    orig_sleep = time.sleep
    time.sleep = lambda s: recorded_sleeps.append(s)

    try:
        class FakeResponse:
            def __init__(self, headers):
                self.headers = headers
                self.status_code = 429
                self.reason = "Too Many Requests"

        class FakeColumn:
            def __init__(self, name):
                self.name = name

        class FakeQueryResult:
            def __init__(self, rows):
                self.columns = [FakeColumn("PreTaxCost"), FakeColumn("ResourceId"), FakeColumn("Currency")]
                self.rows = rows

        class FakeCostClientRetry:
            def __init__(self):
                self.calls = 0
                self.query = self

            def usage(self, scope, params):
                self.calls += 1
                if self.calls == 1:
                    err = HttpResponseError(
                        message="Too many requests",
                        response=FakeResponse({"x-ms-ratelimit-clienttype-retry-after": "7"})
                    )
                    err.status_code = 429
                    raise err
                return FakeQueryResult([[150.0, "/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm-1", "USD"]])

        # (1) 429 with fake retry-after "7" then success -> sleeps [7], costs returned
        fake_client_1 = FakeCostClientRetry()
        costs_1 = query_cost_management(fake_client_1, "sub-1")
        print(f"Test 1 - Calls: {fake_client_1.calls}, Sleeps: {recorded_sleeps}, Costs: {costs_1}")
        assert fake_client_1.calls == 2, f"Expected 2 calls, got {fake_client_1.calls}"
        assert recorded_sleeps == [7], f"Expected sleeps [7], got {recorded_sleeps}"
        assert costs_1 is not None and len(costs_1) == 1
        print("  Test 1: 429 retry with sleep [7] and costs returned (PASSED)")

        # (3) second call within TTL makes 0 API calls
        calls_before = fake_client_1.calls
        costs_cached = query_cost_management(fake_client_1, "sub-1")
        calls_after = fake_client_1.calls
        new_calls = calls_after - calls_before
        print(f"Test 3 - Cached call within TTL made {new_calls} API calls")
        assert new_calls == 0, f"Expected 0 API calls within TTL, got {new_calls}"
        assert costs_cached == costs_1
        print("  Test 3: TTL caching made 0 API calls (PASSED)")

        # (2) 429 x3 -> None, resources get None cost, 0 CostRecord rows, 0 Azure recs, previously known cost preserved
        _COST_CACHE.clear()
        recorded_sleeps.clear()

        class FakeCostClientAlways429:
            def __init__(self):
                self.calls = 0
                self.query = self

            def usage(self, scope, params):
                self.calls += 1
                err = HttpResponseError(
                    message="Too many requests",
                    response=FakeResponse({"x-ms-ratelimit-clienttype-retry-after": "5"})
                )
                err.status_code = 429
                raise err

        fake_client_2 = FakeCostClientAlways429()
        costs_2 = query_cost_management(fake_client_2, "sub-always-429")
        print(f"Test 2 - Calls: {fake_client_2.calls}, Result: {costs_2}")
        assert fake_client_2.calls == 3, f"Expected 3 calls, got {fake_client_2.calls}"
        assert costs_2 is None, f"Expected None on 3x 429, got {costs_2}"

        # Test DB behavior with None costs
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        db = Session()

        u = User(id="u2", email="u2@example.com", password_hash="hash")
        db.add(u)
        db.commit()

        acc = CloudAccount(id="acc-az-test2", user_id="u2", name="Az Test", provider="azure", encrypted_client_secret="gAAAAABtest")
        db.add(acc)
        db.commit()

        # Step A: insert resource with known cost $150.0
        res_initial = [{
            "account_id": acc.id,
            "resource_id": "vm-preserve",
            "resource_name": "vm-preserve",
            "service_type": "AzureVM",
            "resource_type": "Standard_B1s",
            "region": "eastus",
            "status": "running",
            "cpu_utilization_avg": 0.2,
            "runtime_hours": 200.0,
            "storage_size_gb": 32.0,
            "daily_cost_usd": 5.0,
            "estimated_monthly_cost": 150.0,
        }]
        upsert_resources(db, res_initial, [acc.id])
        r_saved = db.query(Resource).filter(Resource.resource_id == "vm-preserve").first()
        assert r_saved.estimated_monthly_cost == 150.0

        # Step B: new collection with None cost (query failed)
        res_none_cost = [
            {
                "account_id": acc.id,
                "resource_id": "vm-preserve",
                "resource_name": "vm-preserve",
                "service_type": "AzureVM",
                "resource_type": "Standard_B1s",
                "region": "eastus",
                "status": "running",
                "cpu_utilization_avg": 0.2,
                "runtime_hours": 200.0,
                "storage_size_gb": 32.0,
                "daily_cost_usd": None,
                "estimated_monthly_cost": None,
            },
            {
                "account_id": acc.id,
                "resource_id": "vm-new-unknown",
                "resource_name": "vm-new-unknown",
                "service_type": "AzureVM",
                "resource_type": "Standard_B1s",
                "region": "eastus",
                "status": "running",
                "cpu_utilization_avg": 0.2,
                "runtime_hours": 200.0,
                "storage_size_gb": 32.0,
                "daily_cost_usd": None,
                "estimated_monthly_cost": None,
            }
        ]
        upsert_resources(db, res_none_cost, [acc.id])
        r_preserved = db.query(Resource).filter(Resource.resource_id == "vm-preserve").first()
        assert r_preserved.estimated_monthly_cost == 150.0, f"Expected 150.0 preserved, got {r_preserved.estimated_monthly_cost}"
        r_new = db.query(Resource).filter(Resource.resource_id == "vm-new-unknown").first()
        assert r_new.estimated_monthly_cost is None, f"Expected None for new VM, got {r_new.estimated_monthly_cost}"
        print(f"  Test 2: previously known cost preserved ($150.0) and new VM has None (PASSED)")

        # Verify record_daily_costs skips resources with daily_cost None
        records_count = record_daily_costs(db, res_none_cost)
        assert records_count == 0, f"Expected 0 daily cost records, got {records_count}"
        db_records = db.query(CostRecord).all()
        assert len(db_records) == 0, f"Expected 0 CostRecord rows, got {len(db_records)}"
        print(f"  Test 2: 0 CostRecord rows written for None daily_cost (PASSED)")

        # Verify cleanup_advisor skips VM with None cost
        db.query(Recommendation).delete()
        db.query(Resource).filter(Resource.resource_id == "vm-preserve").delete()
        db.commit()
        generate_recommendations(db)
        recs = db.query(Recommendation).all()
        assert len(recs) == 0, f"Expected 0 Azure recs for VM with None cost, got {len(recs)}"
        print(f"  Test 2: 0 Azure recs generated when cost is None (PASSED)")

    finally:
        time.sleep = orig_sleep

    print("\nALL ITEM A TESTS PASSED!")


if __name__ == "__main__":
    test_azure_fixes()
    test_azure_cost_handling()
