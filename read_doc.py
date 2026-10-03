from docx import Document

doc = Document("Refrenced/Cloud_Cost_Monitoring_SRS_v2.docx")
print("TABLES:")
for i, table in enumerate(doc.tables):
    for j, row in enumerate(table.rows):
        cells = [c.text.replace("\n", " ").strip() for c in row.cells]
        if any("FR" in c for c in cells):
            print(f"Table {i} Row {j}: {cells}")
