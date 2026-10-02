from docx import Document

try:
    doc = Document("Refrenced/Cloud_Cost_Monitoring_SRS_v2.docx")
    
    for table in doc.tables:
        for row in table.rows:
            if len(row.cells) > 3:
                cell0 = row.cells[0].text
                if "FR-4.1" in cell0:
                    row.cells[2].text = "Completed"
                    row.cells[3].text = "Implemented via services/what_if_simulator.py and routes/simulations.py. Monthly savings are correctly projected without x30 multiplier, payback_days is optional/null for resize events, and UI integration verified."
                if "FR-5.3" in cell0:
                    row.cells[2].text = "Completed"
                    row.cells[3].text = "Implemented through What-If Simulator integration (Simulate button in Recommendations UI), enabling financial impact evaluation before action."
                
    doc.save("Refrenced/Cloud_Cost_Monitoring_SRS_v2.docx")
    print("SRS updated successfully.")
except Exception as e:
    print(f"Error: {e}")
