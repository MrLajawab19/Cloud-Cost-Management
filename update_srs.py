from docx import Document

try:
    doc = Document("Refrenced/Cloud_Cost_Monitoring_SRS_v2.docx")

    for table in doc.tables:
        for row in table.rows:
            if len(row.cells) >= 3:
                cell0 = row.cells[0].text

                # FR-4 / FR-5
                if "FR-4.1" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented via services/what_if_simulator.py and routes/simulations.py. Monthly savings are correctly projected without x30 multiplier, payback_days is optional/null for resize events, and UI integration verified."
                if "FR-5.3" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented through What-If Simulator integration (Simulate button in Recommendations UI), enabling financial impact evaluation before action."

                # FR-6
                if "FR-6.1" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented via _MOCK_PRICING dictionary in savings_plan_optimiser.py, comparing forecasted on-demand baseline against 30% discount / 50% upfront pricing parameters."
                elif "FR-6.2" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented calculation logic for break-even point: upfront_cost / monthly_savings. Integrated denominator guard to handle invalid paths."
                elif "FR-6.3" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented configurable horizon filtering: candidates are recommended only if the computed break_even_months is <= 8.0 months."
                elif "FR-6.4" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented exclusion check: resources with unresolved anomalies (FR-3) within a 14-day lookback window are excluded from SP recommendations."

                # FR-7 — with AzureVM exclusion note on 7.2 and 7.4
                elif "FR-7.1" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented budget_threshold_usd on CloudAccount; trigger mechanism for alerts prepared in backend. Applies to AWS accounts only."
                elif "FR-7.2" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented auto-resize for 'Underutilized EC2 Instance' recommendations (1% <= CPU < 5%). Bypasses escalation, immediate simulated execution. SCOPE: AWS EC2 only. AzureVM resources are explicitly excluded from FR-7 remediation in this phase (Azure deallocated/stopped distinction does not map onto AWS EBS-accrual logic). (NOTE: Real-boto3 execution unreachable since no sandbox provisioned; operates in simulated mode)."
                elif "FR-7.3" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented EscalationState tracking. Background process manages transition from pending to escalated. Applies to AWS EC2 stop candidates only."
                elif "FR-7.4" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented auto-stop for 'Idle EC2 Instance' (CPU < 1%). Triggers after configurable grace_period_hours on CloudAccount (default 48h). SCOPE: AWS EC2 only. AzureVM resources are explicitly excluded from FR-7 remediation in this phase. (NOTE: Real-boto3 execution unreachable; operates in simulated mode)."
                elif "FR-7.5" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented cancellation logic: if recommendation is resolved (or resource state recovers) before grace period, escalation is aborted."
                elif "FR-7.6" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented FR-3 anomaly exclusion: auto-stops are deferred if the service has an active 14-day anomaly. Applies to AWS EC2 stop candidates only."
                elif "FR-7.7" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented RemediationLog table capturing account_id, resource_id, action_type, before/after state, status, and timestamp."
                elif "FR-7.8" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented dual opt-out: global auto_remediate_enabled flag on CloudAccount, and per-resource ignore_remediation flag on Recommendation."

                # FR-1 — 1.1 stays Completed; 1.2/1.3/1.4 -> Designed/Future Work
                elif "FR-1.1" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "AWS daily resource and cost collection implemented via aws_collector.py. CloudAccount model (Option A unified design) supports both AWS and Azure account types."
                elif "FR-1.2" in cell0:
                    row.cells[1].text = "Designed / Future Work"
                    row.cells[2].text = "Azure VM collection designed but deferred. Collector interface fully specified in services/azure_collector.py: collect_all(tenant_id, client_id, client_secret, subscription_id, region, account_id) and collect_demo_data(). Field-mapping contract documented: AzureVM service_type, deallocated->stopped, USD currency assumption with non-USD warning. Deferral reason: no Azure subscription credentials provisioned in project environment. Requires: azure-identity, azure-mgmt-compute, azure-mgmt-costmanagement."
                elif "FR-1.3" in cell0:
                    row.cells[1].text = "Designed / Future Work"
                    row.cells[2].text = "Normalization schema designed: Azure VM resources use service_type='AzureVM' (not 'EC2') to prevent FR-7 remediation rules from firing. resource_type stores VM size (e.g. Standard_D2s_v3). status='stopped' maps from Azure 'deallocated'. cpu_utilization_avg=None (Azure Monitor SDK deferred). Cost in USD assumed; non-USD flagged via WARNING log. Single-subscription-per-CloudAccount assumed; multi-subscription support deferred."
                elif "FR-1.4" in cell0:
                    row.cells[1].text = "Designed / Future Work"
                    row.cells[2].text = "Scheduler dispatch logic designed for Azure branch (see azure_collector.py docstring). CloudAccount.provider field ('aws'|'azure') routes collection to appropriate collector. Deferral reason: azure_collector.collect_all() not yet implemented; requires live Azure credentials for verification. Demo path (collect_demo_data) is code-complete."

    doc.save("Refrenced/Cloud_Cost_Monitoring_SRS_v2.docx")
    print("SRS updated successfully.")

    # Read-back verification
    print("\n--- READ-BACK VERIFICATION ---")
    doc_verify = Document("Refrenced/Cloud_Cost_Monitoring_SRS_v2.docx")
    for table in doc_verify.tables:
        for row in table.rows:
            if len(row.cells) >= 3:
                cell0 = row.cells[0].text
                if any(x in cell0 for x in ["FR-1.", "FR-6.", "FR-7."]):
                    status = row.cells[1].text
                    note_preview = row.cells[2].text[:80].replace("\n", " ")
                    print(f"[{cell0}] -> [{status}] -> [{note_preview}...]")

except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"Error: {e}")
