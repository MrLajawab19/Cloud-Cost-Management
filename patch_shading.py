with open('fix_srs_shading.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Keep everything up to and including line 129 (0-indexed: 128)
kept = lines[:129]

new_tail = (
    "\n"
    "    print('\\n-- READ-BACK VERIFICATION --')\n"
    "    doc2 = Document(SRS_PATH)\n"
    "    fill_mismatches = []\n"
    "    font_mismatches = []\n"
    "    for table in doc2.tables:\n"
    "        for row in table.rows:\n"
    "            if len(row.cells) < 3:\n"
    "                continue\n"
    '            row_id = row.cells[0].text.strip()\n'
    '            status = row.cells[1].text.strip()\n'
    '            if not (row_id.startswith("FR-") or row_id.startswith("NFR-")):\n'
    "                continue\n"
    "            expected_fill = STATUS_COLORS.get(status)\n"
    "            expected_font = STATUS_FONT_COLORS.get(status)\n"
    "            if not expected_fill:\n"
    "                continue\n"
    "            tc = row.cells[1]._tc\n"
    '            tcPr = tc.find(qn("w:tcPr"))\n'
    '            shd = tcPr.find(qn("w:shd")) if tcPr is not None else None\n'
    '            actual_fill = shd.get(qn("w:fill")) if shd is not None else "NONE"\n'
    "            if actual_fill.upper() != expected_fill.upper():\n"
    '                fill_mismatches.append((row_id, status, "fill", expected_fill, actual_fill))\n'
    "            if expected_font:\n"
    "                para = row.cells[1].paragraphs[0]\n"
    "                for run in para.runs:\n"
    '                    rPr = run._r.find(qn("w:rPr"))\n'
    '                    color_el = rPr.find(qn("w:color")) if rPr is not None else None\n'
    '                    actual_font = color_el.get(qn("w:val")) if color_el is not None else "NONE"\n'
    "                    if actual_font.upper() != expected_font.upper():\n"
    '                        font_mismatches.append((row_id, status, "font", expected_font, actual_font))\n'
    "                    break\n"
    "\n"
    "    all_issues = fill_mismatches + font_mismatches\n"
    "    if not all_issues:\n"
    '        print("PASS -- All rows: fill AND font color consistent with status text.")\n'
    "    else:\n"
    '        print("FAIL -- Mismatches remain:")\n'
    "        for m in all_issues:\n"
    '            print(f"  {m[0]}: status={m[1]}, type={m[2]}, expected={m[3]}, got={m[4]}")\n'
    "\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    main()\n"
)

with open('fix_srs_shading.py', 'w', encoding='utf-8') as f:
    f.writelines(kept)
    f.write(new_tail)

print('Patch written successfully.')
