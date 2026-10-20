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
import time
from typing import List, Dict, Any, Optional
from datetime import date

from services.exceptions import CollectionFailed
from config import CURRENCY_FIXED_RATES

logger = logging.getLogger(__name__)

# Module-level cache for Azure Cost Management data per subscription_id
# Structure: {subscription_id: {"data": usage_costs_dict, "timestamp": unix_time}}
_COST_CACHE: Dict[str, Dict[str, Any]] = {}


def query_cost_management(cost_client, subscription_id: str) -> Optional[Dict[str, float]]:
    """
    Query Azure Cost Management for the past 30 days per resource with retries and caching.
    - Up to 3 attempts.
    - On 429: wait is the largest integer in response headers ending with 'retry-after' capped at 60s,
      otherwise 10 * 2^attempt s.
    - On final failure return None (distinct from a successful empty result {}).
    - Caches successful results with a 3h TTL.
    - On failure, reuses a cache entry up to 24h old, otherwise returns None.
    """
    global _COST_CACHE
    now_ts = time.time()

    # 1. Check fresh cache (3h TTL)
    if subscription_id in _COST_CACHE:
        entry = _COST_CACHE[subscription_id]
        if now_ts - entry["timestamp"] <= 3 * 3600:
            logger.info(
                f"Using cached Azure Cost Management data for subscription {subscription_id} "
                f"(age: {int(now_ts - entry['timestamp'])}s)"
            )
            return entry["data"]

    from datetime import datetime, timedelta

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            scope = f"/subscriptions/{subscription_id}"
            now = datetime.utcnow()
            start_date = now - timedelta(days=30)

            query_parameters = {
                "type": "ActualCost",
                "timeframe": "Custom",
                "timePeriod": {
                    "from": start_date.replace(microsecond=0).isoformat() + "Z",
                    "to": now.replace(microsecond=0).isoformat() + "Z",
                },
                "dataset": {
                    "granularity": "None",
                    "aggregation": {
                        "totalCost": {"name": "PreTaxCost", "function": "Sum"}
                    },
                    "grouping": [{"type": "Dimension", "name": "ResourceId"}],
                },
            }
            cost_result = cost_client.query.usage(scope, query_parameters)
            usage_costs: Dict[str, Dict[str, Any]] = {}
            if cost_result and cost_result.rows:
                cost_idx = 0
                res_idx = 1
                curr_idx = None
                for i, col in enumerate(cost_result.columns):
                    col_name = getattr(col, "name", str(col))
                    if col_name == "PreTaxCost":
                        cost_idx = i
                    elif col_name == "ResourceId":
                        res_idx = i
                    elif col_name == "Currency":
                        curr_idx = i

                for row in cost_result.rows:
                    if len(row) > max(cost_idx, res_idx) and row[res_idx]:
                        raw_cost = float(row[cost_idx]) if row[cost_idx] is not None else 0.0
                        res_id = str(row[res_idx]).lower()
                        currency = (
                            str(row[curr_idx]).strip().upper()
                            if (curr_idx is not None and len(row) > curr_idx and row[curr_idx] is not None)
                            else "USD"
                        )

                        rate = CURRENCY_FIXED_RATES.get(currency)
                        if rate is None:
                            logger.warning(
                                f"Unknown currency '{currency}' for Azure resource '{res_id}'; cost set to None"
                            )
                            cost_usd = None
                        else:
                            cost_usd = round(raw_cost * rate, 2)

                        if res_id not in usage_costs:
                            usage_costs[res_id] = {
                                "cost_usd": cost_usd,
                                "original_amount": raw_cost,
                                "currency": currency,
                            }
                        else:
                            existing = usage_costs[res_id]
                            if cost_usd is None or existing["cost_usd"] is None:
                                existing["cost_usd"] = None
                            else:
                                existing["cost_usd"] = round(existing["cost_usd"] + cost_usd, 2)
                            if existing["currency"] == currency:
                                existing["original_amount"] = round(existing["original_amount"] + raw_cost, 2)
                            else:
                                existing["original_amount"] = None
                                existing["currency"] = "MIXED"

            # Cache successful result (3h TTL)
            _COST_CACHE[subscription_id] = {"data": usage_costs, "timestamp": time.time()}
            return usage_costs

        except Exception as e:
            status_code = getattr(e, "status_code", None)
            if not status_code and hasattr(e, "response"):
                status_code = getattr(e.response, "status_code", None)
            is_429 = (status_code == 429) or ("429" in str(e))
            if is_429 and attempt < max_attempts - 1:
                headers = getattr(getattr(e, "response", None), "headers", {}) or {}
                retry_vals = []
                for k, v in headers.items():
                    if k.lower().endswith("retry-after"):
                        try:
                            retry_vals.append(int(v))
                        except (ValueError, TypeError):
                            pass
                if retry_vals:
                    wait_sec = min(60, max(retry_vals))
                else:
                    wait_sec = min(60, 10 * (2 ** attempt))
                logger.warning(
                    f"Cost Management query returned 429 for subscription {subscription_id}. "
                    f"Retrying in {wait_sec}s (attempt {attempt + 1}/{max_attempts})"
                )
                time.sleep(wait_sec)
            else:
                logger.warning(
                    f"Could not fetch Azure Cost Management data for subscription {subscription_id}: {e}"
                )
                if attempt == max_attempts - 1:
                    break

    # 2. On failure, check stale cache fallback (up to 24h old)
    if subscription_id in _COST_CACHE:
        entry = _COST_CACHE[subscription_id]
        if now_ts - entry["timestamp"] <= 24 * 3600:
            logger.info(
                f"Reusing stale cached Cost Management data for subscription {subscription_id} "
                f"(age: {int(now_ts - entry['timestamp'])}s)"
            )
            return entry["data"]

    return None


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
        from datetime import datetime, timedelta, timezone

        credential = ClientSecretCredential(tenant_id, client_id, client_secret)
        compute_client = ComputeManagementClient(credential, subscription_id)
        cost_client = CostManagementClient(credential)
        metrics_client = MetricsQueryClient(credential)

        # 1. Fetch Cost Management Data (Last 30 Days) via cached/retried helper
        usage_costs = query_cost_management(cost_client, subscription_id)
            
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
        try:
            vm_items = list(compute_client.virtual_machines.list_all())
        except Exception as e:
            logger.error(f"Azure VM listing failed for account {account_id}: {e}")
            raise CollectionFailed(f"Azure VM listing failed: {e}") from e

        for vm in vm_items:
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
                
                # Launch time & runtime hours (same semantics as EC2)
                launch_time = getattr(vm, "time_created", None)
                runtime_hours = None
                if launch_time:
                    if status == "running":
                        now_tz = datetime.now(timezone.utc) if launch_time.tzinfo else datetime.utcnow()
                        delta = now_tz - launch_time
                        runtime_hours = max(0.0, round(delta.total_seconds() / 3600, 2))
                    else:
                        runtime_hours = 0.0

                # Fetch Real Metrics & Costs
                # Per VM: cost found -> value; query OK but VM absent from rows -> None; query failed -> None
                daily_cost = None
                est_monthly = None
                orig_amount = None
                orig_currency = None

                if usage_costs is not None:
                    cost_info = usage_costs.get(vm_id.lower())
                    if cost_info is not None:
                        monthly_cost = cost_info.get("cost_usd")
                        if monthly_cost is not None:
                            daily_cost = round(monthly_cost / 30.0, 4)
                            est_monthly = round(monthly_cost, 2)
                        orig_amount = cost_info.get("original_amount")
                        orig_currency = cost_info.get("currency")

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
                    "runtime_hours":       runtime_hours,
                    "launch_time":         launch_time,
                    "storage_size_gb":     storage_size,
                    "request_count":       None,
                    "daily_cost_usd":      daily_cost,
                    "estimated_monthly_cost": est_monthly,
                    "original_cost_amount": orig_amount,
                    "cost_currency":       orig_currency,
                    "record_date":         str(datetime.utcnow().date()),
                })
            except Exception as e:
                logger.error(f"Error processing VM {vm.name if hasattr(vm, 'name') else 'unknown'}: {e}")
                
    except CollectionFailed:
        raise
    except Exception as e:
        logger.error(f"Azure collection failed for account {account_id}: {e}")
        raise CollectionFailed(f"Azure collection failed: {e}") from e

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
            "cpu_utilization_avg": 0.4,
            "runtime_hours":       1440.0,
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
            "runtime_hours":       0.0,
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
            "cpu_utilization_avg": 0.8,
            "runtime_hours":       960.0,
            "storage_size_gb":     256.0,
            "request_count":       None,
            "daily_cost_usd":      9.80,
            "estimated_monthly_cost": 294.0,
            "record_date":         today,
        },
    ]
