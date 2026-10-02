from docx import Document

doc = Document("Refrenced/Cloud_Cost_Monitoring_SRS_v2.docx")
for table in doc.tables:
    for row in table.rows:
        if "FR-6" in row.cells[0].text:
            print(" | ".join([cell.text for cell in row.cells]))
