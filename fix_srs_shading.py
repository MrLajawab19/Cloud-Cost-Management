"""
fix_srs_shading.py
------------------
One-pass global shading + font-color reconciliation for
Cloud_Cost_Monitoring_SRS_v2.docx.

For every FR/NFR row in the Section 6 traceability tables, reads the current
status text in column 2 and writes:
  1. Matching FILL color to ALL cells in that row.
  2. Matching FONT COLOR to every run in the status cell only.

Canonical fill colors (derived from FR-1.1/FR-5.2/FR-5.1):
  Completed   -> E7F3EA  (soft green)
  Partial     -> FBF1DA  (soft amber)
  Not Started -> F8E9E9  (soft red/pink)

Canonical font colors (derived from FR-1.1/FR-5.1/FR-1.2 status runs):
  Completed   -> 1F6B3A  (dark green)
  Partial     -> 8A6100  (dark amber)
  Not Started -> 8A1F1F  (dark red)

Does NOT touch any cell text content.
"""

from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

SRS_PATH = "Refrenced/Cloud_Cost_Monitoring_SRS_v2.docx"

STATUS_COLORS = {
    "Completed":   "E7F3EA",
    "Partial":     "FBF1DA",
    "Not Started": "F8E9E9",
}

STATUS_FONT_COLORS = {
    "Completed":   "1F6B3A",
    "Partial":     "8A6100",
    "Not Started": "8A1F1F",
}


def set_cell_shading(cell, fill_hex: str):
    """
    Apply a solid fill color to a table cell.
    Works by writing/overwriting the w:shd element inside w:tcPr.
    """
    tc = cell._tc
    tcPr = tc.find(qn("w:tcPr"))
    if tcPr is None:
        tcPr = OxmlElement("w:tcPr")
        tc.insert(0, tcPr)

    shd = tcPr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tcPr.append(shd)

    shd.set(qn("w:val"),   "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"),  fill_hex)


def set_status_font_color(cell, font_hex: str):
    """
    Set the font color of every run in the cell's first paragraph.
    Writes/overwrites the w:color element inside each run's w:rPr.
    """
    para = cell.paragraphs[0]
    for run in para.runs:
        rPr = run._r.find(qn("w:rPr"))
        if rPr is None:
            rPr = OxmlElement("w:rPr")
            run._r.insert(0, rPr)
        color_el = rPr.find(qn("w:color"))
        if color_el is None:
            color_el = OxmlElement("w:color")
            rPr.append(color_el)
        color_el.set(qn("w:val"), font_hex)


def reconcile_shading(doc: Document) -> list:
    changes = []

    for table in doc.tables:
        for row in table.rows:
            if len(row.cells) < 3:
                continue

            row_id = row.cells[0].text.strip()
            status = row.cells[1].text.strip()

            if not (row_id.startswith("FR-") or row_id.startswith("NFR-")):
                continue

            target_fill = STATUS_COLORS.get(status)
            if target_fill is None:
                continue

            tc = row.cells[1]._tc
            tcPr = tc.find(qn("w:tcPr"))
            shd = tcPr.find(qn("w:shd")) if tcPr is not None else None
            old_fill = shd.get(qn("w:fill")) if shd is not None else "NONE"

            for cell in row.cells:
                set_cell_shading(cell, target_fill)

            # Set font color on the status cell (column 1) only
            target_font = STATUS_FONT_COLORS.get(status)
            if target_font:
                set_status_font_color(row.cells[1], target_font)

            changes.append((row_id, status, old_fill, target_fill))

    return changes


def main():
    doc = Document(SRS_PATH)
    changes = reconcile_shading(doc)
    doc.save(SRS_PATH)
    print(f"Shading reconciliation complete. Rows processed: {len(changes)}\n")
    print(f"{'Row ID':<12} {'Status':<15} {'Old Fill':<10} {'New Fill':<10} {'Changed?'}")
    print("-" * 62)
    for row_id, status, old_fill, new_fill in changes:
        changed = "YES" if old_fill.upper() != new_fill.upper() else "  -"
        print(f"{row_id:<12} {status:<15} {old_fill:<10} {new_fill:<10} {changed}")


    print('\n-- READ-BACK VERIFICATION --')
    doc2 = Document(SRS_PATH)
    fill_mismatches = []
    font_mismatches = []
    for table in doc2.tables:
        for row in table.rows:
            if len(row.cells) < 3:
                continue
            row_id = row.cells[0].text.strip()
            status = row.cells[1].text.strip()
            if not (row_id.startswith("FR-") or row_id.startswith("NFR-")):
                continue
            expected_fill = STATUS_COLORS.get(status)
            expected_font = STATUS_FONT_COLORS.get(status)
            if not expected_fill:
                continue
            tc = row.cells[1]._tc
            tcPr = tc.find(qn("w:tcPr"))
            shd = tcPr.find(qn("w:shd")) if tcPr is not None else None
            actual_fill = shd.get(qn("w:fill")) if shd is not None else "NONE"
            if actual_fill.upper() != expected_fill.upper():
                fill_mismatches.append((row_id, status, "fill", expected_fill, actual_fill))
            if expected_font:
                para = row.cells[1].paragraphs[0]
                for run in para.runs:
                    rPr = run._r.find(qn("w:rPr"))
                    color_el = rPr.find(qn("w:color")) if rPr is not None else None
                    actual_font = color_el.get(qn("w:val")) if color_el is not None else "NONE"
                    if actual_font.upper() != expected_font.upper():
                        font_mismatches.append((row_id, status, "font", expected_font, actual_font))
                    break

    all_issues = fill_mismatches + font_mismatches
    if not all_issues:
        print("PASS -- All rows: fill AND font color consistent with status text.")
    else:
        print("FAIL -- Mismatches remain:")
        for m in all_issues:
            print(f"  {m[0]}: status={m[1]}, type={m[2]}, expected={m[3]}, got={m[4]}")


if __name__ == "__main__":
    main()
