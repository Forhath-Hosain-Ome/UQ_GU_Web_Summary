"""
Excel report builder service.
Mirrors build_tables() + Excel writing from the original script.
"""
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def build_detail_df(records: list[dict]) -> pd.DataFrame:
    rows = []
    for r in records:
        row = {
            "Sample Size": r["sample_size"],
            "Description": r["description"],
            "Inspection Date": r["inspection_date"],
            "Style": r["style"],
        }
        for i, po in enumerate(r["po_numbers"], start=1):
            row[f"PO_{i}"] = po
        rows.append(row)
    return pd.DataFrame(rows)


def build_summary_df(records: list[dict]) -> pd.DataFrame:
    rows = []
    for r in records:
        style_po = f"{r['style']}({','.join(r['po_numbers'])})"
        rows.append({
            "Style No with PO": style_po,
            "PO Qty": r["po_qty"],
            "Actual Qty": r["actual_qty"],
            "Inspected Qty": r["inspected_qty"],
            "Major Defect": r["major_defect"],
            "Minor Defect": r["minor_defect"],
        })
    return pd.DataFrame(rows)


def write_excel(records: list[dict], output_path: Path) -> Path:
    """
    Write AQL Detail + Summary sheets to an Excel file.
    Returns the final output path.
    """
    detail_df = build_detail_df(records)
    summary_df = build_summary_df(records)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        detail_df.to_excel(writer, sheet_name="Detail", index=False)
        summary_df.to_excel(writer, sheet_name="AQL Summary", index=False)

    logger.info("Excel written → %s", output_path)
    return output_path