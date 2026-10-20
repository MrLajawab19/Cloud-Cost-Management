"""
backend/verify_azure_collect_all.py
Offline test of REAL azure_collector.collect_all using monkeypatched fake Azure SDK clients.
Tests 6 distinct cases:
1. VM with tz-aware time_created (48 h old, running)
2. naive time_created
3. time_created=None
4. deallocated VM
5. Monitor returning only None datapoints
6. Cost rows with INR
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock
from datetime import datetime, timedelta, timezone

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import azure.identity
import azure.mgmt.compute
import azure.mgmt.costmanagement
import azure.monitor.query
from services import azure_collector


class FakeColumn:
    def __init__(self, name):
        self.name = name


def build_case_setup(case_num: int, sub_id: str):
    """
    Returns (vm, vm_detailed, metrics_response, cost_result) for the given case.
    """
    vm_name = f"vm-case-{case_num}"
    vm_id = f"/subscriptions/{sub_id}/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/{vm_name}"

    # Base VM object
    vm = MagicMock()
    vm.id = vm_id
    vm.name = vm_name
    vm.location = "eastus"
    vm.hardware_profile = MagicMock(vm_size="Standard_B2s")
    vm.storage_profile = MagicMock(os_disk=MagicMock(disk_size_gb=30.0))

    # Base detailed VM
    vm_detailed = MagicMock()
    vm_detailed.instance_view = MagicMock()

    # Base metrics response
    metrics_response = MagicMock()
    timeseries_mock = MagicMock()
    timeseries_mock.data = [MagicMock(average=14.5), MagicMock(average=15.5)]
    metrics_mock = MagicMock()
    metrics_mock.timeseries = [timeseries_mock]
    metrics_response.metrics = [metrics_mock]

    # Base Cost Result
    cost_result = MagicMock()
    cost_result.columns = [FakeColumn("PreTaxCost"), FakeColumn("ResourceId"), FakeColumn("Currency")]
    cost_result.rows = [[50.0, vm_id, "USD"]]

    if case_num == 1:
        # 1. VM with tz-aware time_created (48 h old, running)
        vm.time_created = datetime.now(timezone.utc) - timedelta(hours=48)
        vm_detailed.instance_view.statuses = [MagicMock(code="PowerState/running")]
    elif case_num == 2:
        # 2. naive time_created
        vm.time_created = datetime.utcnow() - timedelta(hours=24)
        vm_detailed.instance_view.statuses = [MagicMock(code="PowerState/running")]
    elif case_num == 3:
        # 3. time_created=None
        vm.time_created = None
        vm_detailed.instance_view.statuses = [MagicMock(code="PowerState/running")]
    elif case_num == 4:
        # 4. deallocated VM
        vm.time_created = datetime.now(timezone.utc) - timedelta(hours=72)
        vm_detailed.instance_view.statuses = [MagicMock(code="PowerState/deallocated")]
    elif case_num == 5:
        # 5. Monitor returning only None datapoints
        vm.time_created = datetime.now(timezone.utc) - timedelta(hours=24)
        vm_detailed.instance_view.statuses = [MagicMock(code="PowerState/running")]
        timeseries_mock.data = [MagicMock(average=None), MagicMock(average=None)]
    elif case_num == 6:
        # 6. Cost rows with INR
        vm.time_created = datetime.now(timezone.utc) - timedelta(hours=24)
        vm_detailed.instance_view.statuses = [MagicMock(code="PowerState/running")]
        cost_result.rows = [[8300.0, vm_id, "INR"]]

    return vm, vm_detailed, metrics_response, cost_result


def run_offline_test():
    sub_id = "00000000-0000-0000-0000-000000000000"
    results = []

    case_names = {
        1: "tz-aware time_created (48h, running)",
        2: "naive time_created",
        3: "time_created=None",
        4: "deallocated VM",
        5: "Monitor only None datapoints",
        6: "Cost rows with INR",
    }

    for case_num in range(1, 7):
        azure_collector._COST_CACHE.clear()
        vm, vm_detailed, metrics_response, cost_result = build_case_setup(case_num, sub_id)

        # Build mock clients
        fake_compute = MagicMock()
        fake_compute.virtual_machines.list_all.return_value = [vm]
        fake_compute.virtual_machines.get.return_value = vm_detailed

        fake_cost = MagicMock()
        fake_cost.query.usage.return_value = cost_result

        fake_metrics = MagicMock()
        fake_metrics.query_resource.return_value = metrics_response

        # Monkeypatch SDK constructors
        azure.identity.ClientSecretCredential = MagicMock(return_value=MagicMock())
        azure.mgmt.compute.ComputeManagementClient = MagicMock(return_value=fake_compute)
        azure.mgmt.costmanagement.CostManagementClient = MagicMock(return_value=fake_cost)
        azure.monitor.query.MetricsQueryClient = MagicMock(return_value=fake_metrics)

        collected = azure_collector.collect_all(
            tenant_id="fake-tenant",
            client_id="fake-client",
            client_secret="fake-secret",
            subscription_id=sub_id,
            region_name="eastus",
            account_id="acc-offline-test",
        )

        assert len(collected) == 1, f"Expected 1 resource for case {case_num}, got {len(collected)}"
        r = collected[0]
        results.append({
            "case": case_num,
            "description": case_names[case_num],
            "state": r["status"],
            "launch_time": str(r["launch_time"]),
            "runtime_hours": r["runtime_hours"],
            "cpu_utilization_avg": r["cpu_utilization_avg"],
            "estimated_monthly_cost": r["estimated_monthly_cost"],
            "original_cost_amount": r["original_cost_amount"],
            "cost_currency": r["cost_currency"],
        })

    # Print Table
    print("\n" + "=" * 120)
    print(f"{'Case':<5} | {'State':<8} | {'Runtime(h)':<10} | {'CPU Avg':<8} | {'Est Monthly':<11} | {'Orig Amount':<11} | {'Currency':<8} | {'Description'}")
    print("-" * 120)
    for row in results:
        cpu_str = f"{row['cpu_utilization_avg']:.1f}" if row['cpu_utilization_avg'] is not None else "None"
        cost_str = f"${row['estimated_monthly_cost']:.2f}" if row['estimated_monthly_cost'] is not None else "None"
        orig_str = f"{row['original_cost_amount']}" if row['original_cost_amount'] is not None else "None"
        curr_str = str(row['cost_currency'])
        runtime_str = str(row['runtime_hours'])
        print(f"{row['case']:<5} | {row['state']:<8} | {runtime_str:<10} | {cpu_str:<8} | {cost_str:<11} | {orig_str:<11} | {curr_str:<8} | {row['description']}")
    print("=" * 120 + "\n")

    # Assertions
    # Case 1: runtime_hours approx 48.0, running, cpu=15.0
    assert results[0]["state"] == "running"
    assert results[0]["runtime_hours"] is not None and 47.9 <= results[0]["runtime_hours"] <= 48.1
    # Case 2: naive datetime handled without exception, runtime_hours approx 24.0
    assert results[1]["state"] == "running"
    assert results[1]["runtime_hours"] is not None and 23.9 <= results[1]["runtime_hours"] <= 24.1
    # Case 3: launch_time is None -> runtime_hours is None
    assert results[2]["launch_time"] == "None"
    assert results[2]["runtime_hours"] is None
    # Case 4: deallocated VM -> status stopped, runtime_hours 0.0, cpu None
    assert results[3]["state"] == "stopped"
    assert results[3]["runtime_hours"] == 0.0
    assert results[3]["cpu_utilization_avg"] is None
    # Case 5: Monitor returning only None datapoints -> cpu_utilization_avg is None
    assert results[4]["cpu_utilization_avg"] is None
    # Case 6: INR currency converted to USD (8300 * 0.0115 = 95.45), orig=8300, currency=INR
    assert results[5]["estimated_monthly_cost"] == 95.45
    assert results[5]["original_cost_amount"] == 8300.0
    assert results[5]["cost_currency"] == "INR"

    print("All 6 offline cases PASSED verification.")


if __name__ == "__main__":
    run_offline_test()
