"""
services/azure_collector.py
============================
Azure VM resource collector stub for FR-1.2.

STATUS: DESIGNED / DEFERRED
-----------------------------
Implementation is deferred to future work. The collector interface, field-mapping
contract, and auth flow are fully specified here so that (a) the scheduler can
dispatch to this module once credentials are available, and (b) future implementors
have a clear, unambiguous spec to build against.

DEFERRAL REASON: No Azure subscription credentials are provisioned in this project
environment. The live collection path requires real Service Principal credentials
(tenant_id, client_id, client_secret) and a subscription_id. The demo path
(collect_demo_data) returns synthetic AzureVM data and is the only path exercised
in this phase.

REQUIRED PACKAGES (not yet installed):
    azure-identity          # ClientSecretCredential
    azure-mgmt-compute      # ComputeManagementClient (VM listing)
    azure-mgmt-costmanagement  # CostManagementClient (cost/usage)
    azure-mgmt-resource     # SubscriptionClient (account validation at create-time)

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
  Currency returned by API      -> assume USD; log WARNING if API returns non-USD
  Cost value                    -> CostRecord.daily_cost_usd (raw numeric, no conversion)

CPU utilization:
  Requires azure-monitor-query (separate SDK, DEFERRED).
  Resource.cpu_utilization_avg will be None for all AzureVM rows in this phase.
  cleanup_advisor idle/resize rules are already gated on service_type == 'EC2'
  so they will not fire against AzureVM rows.

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
    """
    Collect Azure VM resources for a single subscription.

    Returns a list of resource dicts compatible with the existing
    upsert_resources() pipeline. Each dict must contain:
        account_id, resource_id, resource_name, service_type,
        region, status, resource_type, cpu_utilization_avg,
        storage_size_gb, request_count

    IMPLEMENTATION DEFERRED -- see module docstring.
    When implemented, use:
        from azure.identity import ClientSecretCredential
        from azure.mgmt.compute import ComputeManagementClient
        credential = ClientSecretCredential(tenant_id, client_id, client_secret)
        compute_client = ComputeManagementClient(credential, subscription_id)
        vms = compute_client.virtual_machines.list_all()
        # Map each vm to the field contract above.
    """
    raise NotImplementedError(
        "azure_collector.collect_all() is not yet implemented. "
        "Use collect_demo_data() in demo mode, or install azure-identity "
        "and azure-mgmt-compute and implement the live path."
    )


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
            "record_date":         today,
        },
    ]
