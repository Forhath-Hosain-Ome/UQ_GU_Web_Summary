"""
top5/extractor.py
------------------
Core extraction + template-writing logic.
Ported from the original processor.py / extract_data_dynamic.py / helpers.
Works entirely in-memory — accepts an openpyxl workbook, returns a BytesIO buffer.
"""
import io
import openpyxl
from utils import _count, _unique

# ── mapping (was mapping.json) ────────────────────────────────────────────────

EXTRACT_SETTINGS = {
    "min_row": 12,
    "item_column": "L",
    "style_column": "M",
}

MAPPINGS = {
    "100%": {
        "cells": {
            "Total_audit": {"type": "count"},
            "Item_name": {"type": "unique"},

            "Check":              "T4",
            "Pass":               "U4",
            "Defect":             "W4",
            "Percent":            "X4",

            # "defect_catagory_1":  "K6",
            # "defect_catagory_2":  "K7",
            # "defect_catagory_3":  "K8",
            # "defect_catagory_4":  "K9",
            # "defect_catagory_5":  "K10",

            # "defect_item_1":      "L6",
            # "defect_item_2":      "L7",
            # "defect_item_3":      "L8",
            # "defect_item_4":      "L9",
            # "defect_item_5":      "L10",

            # "defect_qty_1":       "M6",
            # "defect_qty_2":       "M7",
            # "defect_qty_3":       "M8",
            # "defect_qty_4":       "M9",
            # "defect_qty_5":       "M10",

            # "defect_percent_1":   "N6",
            # "defect_percent_2":   "N7",
            # "defect_percent_3":   "N8",
            # "defect_percent_4":   "N9",
            # "defect_percent_5":   "N10",
        },
        "template_targets": {
            "Total_audit":        "C4",
            "Item_name":          "B5",

            "Check":              "E4",
            "Pass":               "H4",
            "Defect":             "K4",
            "Percent":            "M4",

            # "defect_catagory_1":  "C10",
            # "defect_catagory_2":  "C11",
            # "defect_catagory_3":  "C12",
            # "defect_catagory_4":  "C13",
            # "defect_catagory_5":  "C14",

            # "defect_item_1":      "D10",
            # "defect_item_2":      "D11",
            # "defect_item_3":      "D12",
            # "defect_item_4":      "D13",
            # "defect_item_5":      "D14",

            # "defect_qty_1":       "E10",
            # "defect_qty_2":       "E11",
            # "defect_qty_3":       "E12",
            # "defect_qty_4":       "E13",
            # "defect_qty_5":       "E14",

            # "defect_percent_1":   "F10",
            # "defect_percent_2":   "F11",
            # "defect_percent_3":   "F12",
            # "defect_percent_4":   "F13",
            # "defect_percent_5":   "F14",            
        },
        "defects": {
            "start_row": 6,
            "count": 5,
            "columns": {
                "category": "K",
                "item": "L",
                "qty": "M",
                "percent": "N",
            },
            "target_map": {
                "category": "defect_catagory_",
                "item": "defect_item_",
                "qty": "defect_qty_",
                "percent": "defect_percent_",
            }
        }
    },
    
    "Final": {
        "cells": {
            # "Total_audit":        _count("Final", EXTRACT_SETTINGS.style_column, EXTRACT_SETTINGS.min_row),
            # "Item_name":          _unique("Final", EXTRACT_SETTINGS.item_column, EXTRACT_SETTINGS.min_row),

            "Shipping":           "T4",
            "Audit":              "U4",
            "Defect":             "W4",
            "Percent":            "X4",

            "defect_catagory_1":  "K6",
            "defect_catagory_2":  "K7",
            "defect_catagory_3":  "K8",
            "defect_catagory_4":  "K9",
            "defect_catagory_5":  "K10",

            "defect_item_1":      "L6",
            "defect_item_2":      "L7",
            "defect_item_3":      "L8",
            "defect_item_4":      "L9",
            "defect_item_5":      "L10",

            "defect_qty_1":       "M6",
            "defect_qty_2":       "M7",
            "defect_qty_3":       "M8",
            "defect_qty_4":       "M9",
            "defect_qty_5":       "M10",

            "defect_percent_1":   "N6",
            "defect_percent_2":   "N7",
            "defect_percent_3":   "N8",
            "defect_percent_4":   "N9",
            "defect_percent_5":   "N10",
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

            "defect_qty_1":       "E20",
            "defect_qty_2":       "E21",
            "defect_qty_3":       "E22",
            "defect_qty_4":       "E23",
            "defect_qty_5":       "E24",

            "defect_percent_1":   "F20",
            "defect_percent_2":   "F21",
            "defect_percent_3":   "F22",
            "defect_percent_4":   "F23",
            "defect_percent_5":   "F24",
            
        },
    },
    
    "Final-100%": {
        "cells": {
            # "Total_audit":        _count("Final-100%", EXTRACT_SETTINGS.style_column, EXTRACT_SETTINGS.min_row),
            # "Item_name":          _unique("Final-100%", EXTRACT_SETTINGS.item_column, EXTRACT_SETTINGS.min_row),
            
            "Shipping":           "T4",
            "Audit":              "U4",
            "Defect":             "W4",
            "Percent":            "X4",

            "defect_catagory_1":  "K6",
            "defect_catagory_2":  "K7",
            "defect_catagory_3":  "K8",
            "defect_catagory_4":  "K9",
            "defect_catagory_5":  "K10",

            "defect_item_1":      "L6",
            "defect_item_2":      "L7",
            "defect_item_3":      "L8",
            "defect_item_4":      "L9",
            "defect_item_5":      "L10",

            "defect_qty_1":       "M6",
            "defect_qty_2":       "M7",
            "defect_qty_3":       "M8",
            "defect_qty_4":       "M9",
            "defect_qty_5":       "M10",

            "defect_percent_1":   "N6",
            "defect_percent_2":   "N7",
            "defect_percent_3":   "N8",
            "defect_percent_4":   "N9",
            "defect_percent_5":   "N10",
        },
        "template_targets": {
            "Total_audit":        "C27",
            "Item_name":          "B28",
            "Shipping":           "E27",
            "Audit":              "H27",
            "Defect":             "K27",
            "Percent":            "M27",

            "defect_catagory_1":  "C30",
            "defect_catagory_2":  "C31",
            "defect_catagory_3":  "C32",
            "defect_catagory_4":  "C33",
            "defect_catagory_5":  "C34",

            "defect_item_1":      "D30",
            "defect_item_2":      "D31",
            "defect_item_3":      "D32",
            "defect_item_4":      "D33",
            "defect_item_5":      "D34",

            "defect_percent_1":   "E30",
            "defect_percent_2":   "E31",
            "defect_percent_3":   "E32",
            "defect_percent_4":   "E33",
            "defect_percent_5":   "E34",

            "defect_qty_1":       "F30",
            "defect_qty_2":       "F31",
            "defect_qty_3":       "F32",
            "defect_qty_4":       "F33",
            "defect_qty_5":       "F34",
        },
    },

    "Re-Final": {
        "cells": {
            # "Total_audit":        _count("Re-Final", EXTRACT_SETTINGS.style_column, EXTRACT_SETTINGS.min_row),
            # "Item_name":          _unique("Re-Final", EXTRACT_SETTINGS.item_column, EXTRACT_SETTINGS.min_row),

            "Shipping":           "T4",
            "Audit":              "U4",
            "Defect":             "W4",
            "Percent":            "X4",

            "defect_catagory_1":  "K6",
            "defect_catagory_2":  "K7",
            "defect_catagory_3":  "K8",
            "defect_catagory_4":  "K9",
            "defect_catagory_5":  "K10",

            "defect_item_1":      "L6",
            "defect_item_2":      "L7",
            "defect_item_3":      "L8",
            "defect_item_4":      "L9",
            "defect_item_5":      "L10",

            "defect_qty_1":       "M6",
            "defect_qty_2":       "M7",
            "defect_qty_3":       "M8",
            "defect_qty_4":       "M9",
            "defect_qty_5":       "M10",

            "defect_percent_1":   "N6",
            "defect_percent_2":   "N7",
            "defect_percent_3":   "N8",
            "defect_percent_4":   "N9",
            "defect_percent_5":   "N10",
        },
        "template_targets": {
            "Total_audit":        "C37",
            "Item_name":          "B38",
            "Shipping":           "E37",
            "Audit":              "H37",
            "Defect":             "K37",
            "Percent":            "M37",

            "defect_catagory_1":  "C40",
            "defect_catagory_2":  "C41",
            "defect_catagory_3":  "C42",
            "defect_catagory_4":  "C43",
            "defect_catagory_5":  "C44",

            "defect_item_1":      "D40",
            "defect_item_2":      "D41",
            "defect_item_3":      "D42",
            "defect_item_4":      "D43",
            "defect_item_5":      "D44",

            "defect_percent_1":   "E40",
            "defect_percent_2":   "E41",
            "defect_percent_3":   "E42",
            "defect_percent_4":   "E43",
            "defect_percent_5":   "E44",

            "defect_qty_1":       "F40",
            "defect_qty_2":       "F41",
            "defect_qty_3":       "F42",
            "defect_qty_4":       "F43",
            "defect_qty_5":       "F44",
        },
    },
}


# ── main extract ──────────────────────────────────────────────────────────────

# def extract_data(wb, sheet_name):
#     """
#     Extract all data from the source sheet.
#     Returns a dict ready to be written into the template.
#     """
#     ws     = wb[sheet_name]
#     cfg    = MAPPINGS[sheet_name]
#     data   = {}

#     # Static cells
#     for key, coord in cfg["cells"].items():
#         data[key] = ws[coord].value

#     # Dynamic column L data
#     col    = EXTRACT_SETTINGS["column_letter"]
#     start  = EXTRACT_SETTINGS["min_row"]
#     unique_items  = _unique(ws, col, start)
#     data["item_column"]   = ", ".join(str(i) for i in unique_items)
#     data["style_column"] = _count(ws, col, start)

#     return data
def extract_data(wb, sheet_name):
    ws = wb[sheet_name]
    cfg = MAPPINGS.get(sheet_name, {})
    settings = EXTRACT_SETTINGS
    data = {}

    # 1. static + computed cells
    for key, rule in cfg.get("cells", {}).items():
        data[key] = resolve_cell(ws, rule, settings)

    # 2. template mapping
    for key, coord in cfg.get("template_targets", {}).items():
        data[key] = ws[coord].value

    # 3. defects block
    if "defects" in cfg:
        data.update(resolve_defects(ws, cfg["defects"]))

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


def resolve_cell(ws, rule, settings):
    col = settings["item_column"]
    start = settings["min_row"]

    if isinstance(rule, str):
        return ws[rule].value

    if rule["type"] == "count":
        return _count(ws, col, start)

    if rule["type"] == "unique":
        return _unique(ws, col, start)

    return None

def resolve_defects(ws, rule):
    start = rule["start_row"]
    count = rule["count"]
    cols = rule["columns"]
    prefix = rule["target_map"]

    result = {}

    for i in range(count):
        row = start + i
        idx = i + 1

        result[f"{prefix['category']}{idx}"] = ws[f"{cols['category']}{row}"].value
        result[f"{prefix['item']}{idx}"] = ws[f"{cols['item']}{row}"].value
        result[f"{prefix['qty']}{idx}"] = ws[f"{cols['qty']}{row}"].value
        result[f"{prefix['percent']}{idx}"] = ws[f"{cols['percent']}{row}"].value

    return result