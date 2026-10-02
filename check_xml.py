from docx import Document

doc = Document("Refrenced/Cloud_Cost_Monitoring_SRS_v2.docx")
for table in doc.tables:
    for row in table.rows:
        if len(row.cells) > 0 and "FR-4.1" in row.cells[0].text:
            print("Cell 0 xml:", row.cells[0]._tc.tcPr.xml)
            print("Cell 2 xml:", row.cells[2]._tc.tcPr.xml)
            print("Cell 3 xml:", row.cells[3]._tc.tcPr.xml)
