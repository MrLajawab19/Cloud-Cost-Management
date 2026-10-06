"""
services/azure_collector.py
============================
Azure VM resource collector stub for FR-1.2.

STATUS: IMPLEMENTED (FR-1.2)
-----------------------------
Live collection is fully implemented, querying Compute, Cost Management, and Azure Monitor APIs.

REQUIRED ROLES / PERMISSIONS:
The provided Service Principal (client_id, client_secret) MUST have the following RBAC roles
assigned at the Subscription scope:
  1. Reader (or Virtual Machine Contributor) - to enumerate VMs.
  2. Cost Management Reader - to query usage and cost data.
  3. Monitoring Reader - to query CPU utilization metrics from Azure Monitor.

REQUIRED PACKAGES (added to requirements.txt):
    azure-identity
    azure-mgmt-compute
    azure-mgmt-costmanagement
    azure-monitor-query

AUTH FLOW (for future implementation):
    from azure.identity import ClientSecretCredential
    credential = ClientSecretCredential(tenant_id, client_id, client_secret)
    # Use credential with each management client below.

FIELD MAPPING CONTRACT
-----------------------
Azure concept                   -> Resource field / value
--------------------------------------------------------------
Virtual Machine                 -> service_type = "AzureVM"
VM size (e.g. Standard_D2s_v3) -> resource_type (stored as-is)
VM power state "running"        -> status = "running"
VM power state "deallocated"    -> status = "stopped"
    NOTE: "deallocated" is the Azure equivalent of AWS stopped/terminated.
    EBS-accrual logic from cleanup_advisor does NOT apply to AzureVM rows.
    FR-7 remediation (resize/stop) is explicitly excluded for AzureVM in this phase.
Azure region (e.g. "eastus")    -> region (stored as-is; different naming from AWS)
Resource group name             -> stored in resource_name as prefix, e.g. "rg-prod/myvm"
Subscription ID                 -> stored on the CloudAccount row, not on Resource

Cost Management API:
  Currency returned by API      -> Assume USD
  Cost value                    -> CostRecord.daily_cost_usd (30-day average)

CPU utilization:
  Queried via azure-monitor-query for the last 14 days.
  Feeds directly into cleanup_advisor's idle/resize rules.

SCHEDULER INTEGRATION (prepared, not yet active):
    In scheduler.py run_collection_pipeline(), add:
        elif acc.provider == 'azure':
            resources = azure_collector.collect_all(
                tenant_id=acc.tenant_id,
                client_id=acc.client_id,
                client_secret=decrypt_secret(acc.encrypted_client_secret),
                subscription_id=acc.subscription_id,
                region_name=acc.region,
                account_id=acc.id
            )
"""

import logging
from typing import List, Dict, Any
from datetime import date

logger = logging.getLogger(__name__)


def collect_all(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    subscription_id: str,
    region_name: str,
    account_id: str,
) -> List[Dict[str, Any]]:
    logger.info(f"Starting live Azure resource collection for account {account_id}…")
    resources = []
    try:
        from azure.identity import ClientSecretCredential
        from azure.mgmt.compute import ComputeManagementClient
        from azure.mgmt.costmanagement import CostManagementClient
        from azure.monitor.query import MetricsQueryClient
        from datetime import datetime, timedelta
        
        credential = ClientSecretCredential(tenant_id, client_id, client_secret)
        compute_client = ComputeManagementClient(credential, subscription_id)
        cost_client = CostManagementClient(credential)
        metrics_client = MetricsQueryClient(credential)
        
        # 1. Fetch Cost Management Data (Last 30 Days)
        usage_costs = {}
        try:
            scope = f"/subscriptions/{subscription_id}"
            now = datetime.utcnow()
            start_date = now - timedelta(days=30)
            
            query_parameters = {
                "type": "ActualCost",
                "timeframe": "Custom",
                "timePeriod": {
                    "fromProperty": start_date.replace(microsecond=0).isoformat() + "Z",
                    "to": now.replace(microsecond=0).isoformat() + "Z"
                },
                "dataset": {
                    "granularity": "None",
                    "aggregation": {
                        "totalCost": {"name": "PreTaxCost", "function": "Sum"}
                    },
                    "grouping": [
                        {"type": "Dimension", "name": "ResourceId"}
                    ]
                }
            }
            cost_result = cost_client.query.usage(scope, query_parameters)
            if cost_result and cost_result.rows:
                # Rows generally follow: [Cost, ResourceId, Currency] or similar.
                # Find the index of Cost and ResourceId based on columns metadata if needed,
                # but typically Azure returns Cost at index 0, and grouped dimension at index 1.
                cost_idx = 0
                res_idx = 1
                for i, col in enumerate(cost_result.columns):
                    if col.name == "PreTaxCost": cost_idx = i
                    if col.name == "ResourceId": res_idx = i
                
                for row in cost_result.rows:
                    if len(row) > max(cost_idx, res_idx):
                        cost_val = float(row[cost_idx] or 0.0)
                        res_id = str(row[res_idx]).lower()
                        usage_costs[res_id] = usage_costs.get(res_id, 0.0) + cost_val
        except Exception as e:
            logger.warning(f"Could not fetch Azure Cost Management data for subscription {subscription_id}: {e}")
            
        # Helper for CPU Metrics
        def get_cpu(vm_id: str) -> float:
            try:
                response = metrics_client.query_resource(
                    vm_id,
                    metric_names=["Percentage CPU"],
                    timespan=timedelta(days=14)
                )
                if response.metrics:
                    series = response.metrics[0].timeseries
                    if series and series[0].data:
                        vals = [d.average for d in series[0].data if d.average is not None]
                        if vals:
                            return sum(vals) / len(vals)
            except Exception as e:
                logger.warning(f"Could not fetch Azure metrics for VM {vm_id}: {e}")
            return None

        # 2. Enumerate VMs
        for vm in compute_client.virtual_machines.list_all():
            try:
                vm_id = vm.id
                vm_name = vm.name
                
                parts = vm_id.split('/')
                rg_name = "unknown"
                try:
                    rg_idx = [p.lower() for p in parts].index('resourcegroups')
                    rg_name = parts[rg_idx + 1]
                except ValueError:
                    pass
                
                resource_name = f"{rg_name}/{vm_name}"
                region = vm.location
                
                vm_size = "unknown"
                if vm.hardware_profile and vm.hardware_profile.vm_size:
                    vm_size = vm.hardware_profile.vm_size
                
                status = "unknown"
                try:
                    vm_detailed = compute_client.virtual_machines.get(rg_name, vm_name, expand='instanceView')
                    if vm_detailed.instance_view and vm_detailed.instance_view.statuses:
                        for s in vm_detailed.instance_view.statuses:
                            if s.code and s.code.startswith('PowerState/'):
                                pstate = s.code.split('/')[-1].lower()
                                if pstate == "deallocated":
                                    status = "stopped"
                                else:
                                    status = pstate.replace("vm", "").strip()
                except Exception as e:
                    logger.warning(f"Could not fetch instance view for VM {vm_name}: {e}")
                    
                storage_size = 0.0
                if vm.storage_profile and vm.storage_profile.os_disk and vm.storage_profile.os_disk.disk_size_gb:
                    storage_size = float(vm.storage_profile.os_disk.disk_size_gb)
                
                # Fetch Real Metrics & Costs
                monthly_cost = usage_costs.get(vm_id.lower(), 0.0)
                daily_cost = monthly_cost / 30.0
                
                cpu_avg = None
                if status == "running":
                    cpu_avg = get_cpu(vm_id)
                
                resources.append({
                    "account_id":          account_id,
                    "resource_id":         vm_id,
                    "resource_name":       resource_name,
                    "service_type":        "AzureVM",
                    "resource_type":       vm_size,
                    "region":              region,
                    "status":              status,
                    "cpu_utilization_avg": cpu_avg,
                    "storage_size_gb":     storage_size,
                    "request_count":       None,
                    "daily_cost_usd":      round(daily_cost, 4),
                    "estimated_monthly_cost": round(monthly_cost, 2),
                    "record_date":         str(datetime.utcnow().date()),
                })
            except Exception as e:
                logger.error(f"Error processing VM {vm.name if hasattr(vm, 'name') else 'unknown'}: {e}")
                
    except Exception as e:
        logger.error(f"Azure collection failed for account {account_id}: {e}")
        
    return resources


def collect_demo_data() -> List[Dict[str, Any]]:
    """
    Returns synthetic Azure VM resource data compatible with upsert_resources().
    Used when settings.demo_mode is True and provider == 'azure'.

    All service_type values are 'AzureVM' -- never 'EC2' -- so that
    cleanup_advisor and FR-7 remediation rules (which gate on service_type == 'EC2')
    do not fire against these rows.

    cpu_utilization_avg is None for all rows (Azure Monitor SDK deferred).
    """
    today = str(date.today())
    return [
        {
            "account_id":          "__azure_demo__",
            "resource_id":         "azure-vm-001",
            "resource_name":       "rg-prod/web-server-01",
            "service_type":        "AzureVM",
            "resource_type":       "Standard_D2s_v3",
            "region":              "eastus",
            "status":              "running",
            "cpu_utilization_avg": None,   # Azure Monitor deferred
            "storage_size_gb":     128.0,
            "request_count":       None,
            "daily_cost_usd":      4.20,
            "estimated_monthly_cost": 126.0,
            "record_date":         today,
        },
        {
            "account_id":          "__azure_demo__",
            "resource_id":         "azure-vm-002",
            "resource_name":       "rg-dev/dev-machine-01",
            "service_type":        "AzureVM",
            "resource_type":       "Standard_B2s",
            "region":              "westeurope",
            "status":              "stopped",   # deallocated -> stopped per field-mapping contract
            "cpu_utilization_avg": None,
            "storage_size_gb":     64.0,
            "request_count":       None,
            "daily_cost_usd":      0.05,        # storage-only cost when deallocated
            "estimated_monthly_cost": 1.5,
            "record_date":         today,
        },
        {
            "account_id":          "__azure_demo__",
            "resource_id":         "azure-vm-003",
            "resource_name":       "rg-prod/analytics-worker-01",
            "service_type":        "AzureVM",
            "resource_type":       "Standard_F8s_v2",
            "region":              "eastus",
            "status":              "running",
            "cpu_utilization_avg": None,
            "storage_size_gb":     256.0,
            "request_count":       None,
            "daily_cost_usd":      9.80,
            "estimated_monthly_cost": 294.0,
            "record_date":         today,
        },
    ]
