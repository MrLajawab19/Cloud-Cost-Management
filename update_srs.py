from docx import Document

try:
    doc = Document("Refrenced/Cloud_Cost_Monitoring_SRS_v2.docx")
    
    # Update FR-4 and FR-5
    for table in doc.tables:
        for row in table.rows:
            if len(row.cells) >= 3:
                cell0 = row.cells[0].text
                if "FR-4.1" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented via services/what_if_simulator.py and routes/simulations.py. Monthly savings are correctly projected without x30 multiplier, payback_days is optional/null for resize events, and UI integration verified."
                if "FR-5.3" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented through What-If Simulator integration (Simulate button in Recommendations UI), enabling financial impact evaluation before action."
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
                
                # Update FR-7
                elif "FR-7.1" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented budget_threshold_usd on AWSAccount; trigger mechanism for alerts prepared in backend."
                elif "FR-7.2" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented auto-resize for 'Underutilized EC2 Instance' recommendations (CPU < 5%). Bypasses escalation, immediate simulated execution. (NOTE: Real-boto3 execution unreachable since no sandbox provisioned; operates in simulated mode)."
                elif "FR-7.3" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented EscalationState tracking. Background process manages transition from pending to escalated."
                elif "FR-7.4" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented auto-stop for 'Idle EC2 Instance' (CPU < 1%). Triggers after configurable grace_period_hours on AWSAccount (default 48). (NOTE: Real-boto3 execution unreachable; operates in simulated mode)."
                elif "FR-7.5" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented cancellation logic: if recommendation is resolved (or resource state recovers) before grace period, escalation is aborted."
                elif "FR-7.6" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented FR-3 anomaly exclusion: auto-stops are deferred if the service has an active 14-day anomaly."
                elif "FR-7.7" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented RemediationLog table capturing account_id, resource_id, action_type, before/after state, status, and timestamp."
                elif "FR-7.8" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Implemented dual opt-out: global auto_remediate_enabled flag on AWSAccount, and per-resource ignore_remediation flag on Recommendation."
                
    doc.save("Refrenced/Cloud_Cost_Monitoring_SRS_v2.docx")
    print("SRS updated successfully.")
    
    # Verification Step
    print("\n--- READ-BACK VERIFICATION ---")
    doc_verify = Document("Refrenced/Cloud_Cost_Monitoring_SRS_v2.docx")
    for table in doc_verify.tables:
        for row in table.rows:
            if len(row.cells) >= 3:
                cell0 = row.cells[0].text
                if "FR-6." in cell0 or "FR-7." in cell0:
                    print(f"[{cell0}] -> [{row.cells[1].text}] -> [{row.cells[2].text}]")

except Exception as e:
    print(f"Error: {e}")
