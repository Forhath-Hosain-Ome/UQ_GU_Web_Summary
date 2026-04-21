"""
top5/extractor.py
------------------
Core extraction + template-writing logic.
Ported from the original processor.py / extract_data_dynamic.py / helpers.
Works entirely in-memory — accepts an openpyxl workbook, returns a BytesIO buffer.
"""
import io
import openpyxl

# ── mapping (was mapping.json) ────────────────────────────────────────────────

EXTRACT_SETTINGS = {
    "min_row": 12,
    "column_letter": "L",
}

MAPPINGS = {
    "Final": {
        "cells": {
            "Shipping":           "T4",
            "Audit":              "U4",
            "Defect":             "W4",
            "Percent":            "X4",
            "defect_catagory_1":  "L6",
            "defect_catagory_2":  "L7",
            "defect_catagory_3":  "L8",
            "defect_catagory_4":  "L9",
            "defect_catagory_5":  "L10",
            "defect_item_1":      "M6",
            "defect_item_2":      "M7",
            "defect_item_3":      "M8",
            "defect_item_4":      "M9",
            "defect_item_5":      "M10",
            "defect_percent_1":   "N6",
            "defect_percent_2":   "N7",
            "defect_percent_3":   "N8",
            "defect_percent_4":   "N9",
            "defect_percent_5":   "N10",
            "defect_qty_1":       "O6",
            "defect_qty_2":       "O7",
            "defect_qty_3":       "O8",
            "defect_qty_4":       "O9",
            "defect_qty_5":       "O10",
        },
        "template_targets": {
            "Total_audit":        "C17",
            "Item_name":          "B18",
            "Shipping":           "E17",
            "Audit":              "H17",
            "Defect":             "K17",
            "Percent":            "M17",
            "defect_catagory_1":  "C20",
            "defect_catagory_2":  "C21",
            "defect_catagory_3":  "C22",
            "defect_catagory_4":  "C23",
            "defect_catagory_5":  "C24",
            "defect_item_1":      "D20",
            "defect_item_2":      "D21",
            "defect_item_3":      "D22",
            "defect_item_4":      "D23",
            "defect_item_5":      "D24",
            "defect_percent_1":   "E20",
            "defect_percent_2":   "E21",
            "defect_percent_3":   "E22",
            "defect_percent_4":   "E23",
            "defect_percent_5":   "E24",
            "defect_qty_1":       "F20",
            "defect_qty_2":       "F21",
            "defect_qty_3":       "F22",
            "defect_qty_4":       "F23",
            "defect_qty_5":       "F24",
        },
    },
    "Re-Final": {
        "cells": {
            "Shipping":           "T4",
            "Audit":              "U4",
            "defect_catagory_1":  "L6",
            "defect_catagory_2":  "L7",
            "defect_catagory_3":  "L8",
            "defect_catagory_4":  "L9",
            "defect_catagory_5":  "L10",
            "defect_item_1":      "M6",
            "defect_item_2":      "M7",
            "defect_item_3":      "M8",
            "defect_item_4":      "M9",
            "defect_item_5":      "M10",
            "defect_percent_1":   "N6",
            "defect_percent_2":   "N7",
            "defect_percent_3":   "N8",
            "defect_percent_4":   "N9",
            "defect_percent_5":   "N10",
            "defect_qty_1":       "O6",
            "defect_qty_2":       "O7",
            "defect_qty_3":       "O8",
            "defect_qty_4":       "O9",
            "defect_qty_5":       "O10",
        },
        # Re-Final writes to same template targets as Final
        # (original code always used 'Final' mapping_key for template_targets)
        "template_targets": {
            "Total_audit":        "C17",
            "Item_name":          "B18",
            "Shipping":           "E17",
            "Audit":              "H17",
            "defect_catagory_1":  "C20",
            "defect_catagory_2":  "C21",
            "defect_catagory_3":  "C22",
            "defect_catagory_4":  "C23",
            "defect_catagory_5":  "C24",
            "defect_item_1":      "D20",
            "defect_item_2":      "D21",
            "defect_item_3":      "D22",
            "defect_item_4":      "D23",
            "defect_item_5":      "D24",
            "defect_percent_1":   "E20",
            "defect_percent_2":   "E21",
            "defect_percent_3":   "E22",
            "defect_percent_4":   "E23",
            "defect_percent_5":   "E24",
            "defect_qty_1":       "F20",
            "defect_qty_2":       "F21",
            "defect_qty_3":       "F22",
            "defect_qty_4":       "F23",
            "defect_qty_5":       "F24",
        },
    },
}


# ── helpers (was count.py / unique.py) ────────────────────────────────────────

def _count(ws, column_letter, min_row):
    """Count non-empty cells in a column from min_row downward."""
    col_idx = openpyxl.utils.column_index_from_string(column_letter)
    total = 0
    for (cell,) in ws.iter_rows(min_row=min_row, min_col=col_idx, max_col=col_idx):
        if cell.value is not None:
            total += 1
    return total


def _unique(ws, column_letter, min_row):
    """Return unique non-empty values from a column starting at min_row."""
    col_idx = openpyxl.utils.column_index_from_string(column_letter)
    seen = set()
    for (cell,) in ws.iter_rows(min_row=min_row, min_col=col_idx, max_col=col_idx):
        if cell.value is not None:
            seen.add(cell.value)
    return list(seen)


# ── main extract ──────────────────────────────────────────────────────────────

def extract_data(wb, sheet_name):
    """
    Extract all data from the source sheet.
    Returns a dict ready to be written into the template.
    """
    ws     = wb[sheet_name]
    cfg    = MAPPINGS[sheet_name]
    data   = {}

    # Static cells
    for key, coord in cfg["cells"].items():
        data[key] = ws[coord].value

    # Dynamic column L data
    col    = EXTRACT_SETTINGS["column_letter"]
    start  = EXTRACT_SETTINGS["min_row"]
    unique_items  = _unique(ws, col, start)
    data["Item_name"]   = ", ".join(str(i) for i in unique_items)
    data["Total_audit"] = _count(ws, col, start)

    return data


# ── write to template ─────────────────────────────────────────────────────────

def process(source_file_bytes, template_path):
    """
    Main entry point.

    Parameters
    ----------
    source_file_bytes : bytes
        Raw bytes of the uploaded Excel file.
    template_path : str | Path
        Absolute path to the template.xlsx on disk.

    Returns
    -------
    BytesIO
        In-memory Excel workbook ready to stream as a download.
    """
    wb_source = openpyxl.load_workbook(
        io.BytesIO(source_file_bytes), data_only=True
    )

    # Detect sheet
    if "Final" in wb_source.sheetnames:
        sheet_name = "Final"
    elif "Re-Final" in wb_source.sheetnames:
        sheet_name = "Re-Final"
    else:
        raise ValueError(
            f"No 'Final' or 'Re-Final' sheet found. "
            f"Available sheets: {wb_source.sheetnames}"
        )

    data    = extract_data(wb_source, sheet_name)
    targets = MAPPINGS[sheet_name]["template_targets"]

    wb_template = openpyxl.load_workbook(template_path)
    ws_template = wb_template.active

    for key, cell_ref in targets.items():
        if key in data:
            ws_template[cell_ref] = data[key]

    buf = io.BytesIO()
    wb_template.save(buf)
    buf.seek(0)
    return buf