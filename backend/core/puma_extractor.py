import pdfplumber
import re
from datetime import datetime
from .enums import FACTORY_CODE
def extract_single_pdf(file_path):

    text_all = ""

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text_all += t + "\n"

    if not text_all.strip():
        raise ValueError("Empty PDF")

    # ---- Inspection Date ----
    m = re.search(r"Inspection Date\s+(\d{2}\s\w{3}\s\d{4})", text_all)
    if m:
        try:
            inspection_date = datetime.strptime(m.group(1), '%d %b %Y').strftime('%Y-%m-%d')
        except:
            inspection_date = m.group(1)
    else:
        inspection_date = ""

    # ---- TOTAL row ----
    total_line = re.search(r"Total\s+.*", text_all, re.IGNORECASE)
    if not total_line:
        raise ValueError("TOTAL row not found")

    nums = list(map(int, re.findall(r"\d+", total_line.group(0))))
    po_qty, actual_qty, inspected_qty = nums[0], nums[1], nums[-1]

    # ---- Defects ----
    major_defect = ""
    minor_defect = ""

    m = re.search(r"Workmanship\s+Pass\s+(\d+\s*/\s*\d+)\s+(\d+\s*/\s*\d+)", text_all)
    if m:
        major_defect = m.group(1).replace(" ", "")
        minor_defect = m.group(2).replace(" ", "")

    # ---- Style ----
    m = re.search(r"1\.\s+(.+?)\s+(\d{6})\s+\d+", text_all)
    if not m:
        raise ValueError("Style not found")

    desc_and_nums = m.group(1)
    style = m.group(2)
    description = desc_and_nums.strip()

    # ---- POs ----
    pos = re.findall(r"\b460\d{7,}\b", text_all)
    if not pos:
        raise ValueError("POs not found")

    # ---- Factory ----
    factory = ""
    factory_code = ""

    m = re.search(
        r"^Factory\s+([A-Z0-9&._()\- ]+?)(?:\s{2,}|Sample Size|QC Stage|Inspection Date|$)",
        text_all,
        re.IGNORECASE | re.MULTILINE
    )

    if m:
        factory_code = m.group(1).strip().upper()
        factory = FACTORY_CODE.get(factory_code, factory_code)

    # ---- Final Customer ----
    m = re.search(r"Inspected\s+\d+\.\s+\d+\s+\d{2}\s\w{3}\s\d{4}\s+(\w+)", text_all)
    final_customer = m.group(1) if m else ""

    return {
        "Inspection Date": inspection_date,
        "Style": style,
        "Description": description,
        "Sample Size": inspected_qty,
        "PO Qty": po_qty,
        "Actual Qty": actual_qty,
        "Inspected Qty": inspected_qty,
        "Major Defect": major_defect,
        "Minor Defect": minor_defect,
        "FactoryCode": factory_code,
        "Factory": factory,
        "Final Customer": final_customer,
        "POs": sorted(pos)
    }