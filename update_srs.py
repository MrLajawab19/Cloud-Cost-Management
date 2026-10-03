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
                if "FR-6.1" in cell0 or "FR-6.2" in cell0 or "FR-6.3" in cell0 or "FR-6.4" in cell0:
                    row.cells[1].text = "Completed"
                    row.cells[2].text = "Savings Plan logic implemented in savings_plan_optimiser.py with break-even horizons, denominator guards, and anomaly exclusion. Verified live."
                
    doc.save("Refrenced/Cloud_Cost_Monitoring_SRS_v2.docx")
    print("SRS updated successfully.")
    
    # Verification Step
    print("\n--- READ-BACK VERIFICATION ---")
    doc_verify = Document("Refrenced/Cloud_Cost_Monitoring_SRS_v2.docx")
    for table in doc_verify.tables:
        for row in table.rows:
            if len(row.cells) >= 3:
                cell0 = row.cells[0].text
                if "FR-6." in cell0:
                    print(f"[{cell0}] -> [{row.cells[1].text}] -> [{row.cells[2].text}]")

except Exception as e:
    print(f"Error: {e}")
