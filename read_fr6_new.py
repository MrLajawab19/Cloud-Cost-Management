from docx import Document

doc = Document("Refrenced/Cloud_Cost_Monitoring_SRS_v2.docx")
found = False
for table in doc.tables:
    for row in table.rows:
        if len(row.cells) > 3:
            cell0 = row.cells[0].text
            if "FR-6" in cell0:
                found = True
                print(f"[{cell0}] -> [{row.cells[1].text[:30]}] -> [{row.cells[2].text}]")
if not found:
    print("Could not find FR-6 in any cell0 with length > 3")
