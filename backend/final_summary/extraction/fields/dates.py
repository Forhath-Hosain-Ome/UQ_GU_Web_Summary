"""
----------------------------
Extracts all date fields from an audit report sheet.

Fields handled:
  - date_of_issue  (NOT extracted from sheet — injected from batch.inspection_date)
  - exf            (Ex-Factory date)
  - po_edt         (PO Estimated Delivery)
  - po_wh          (PO Warehouse / ship date — may be split across 3 cells)
  - plan_edt       (Plan Estimated Delivery)
  - plan_wh        (Plan Warehouse date)

Important: date_of_issue is always set by the upload batch (user-selected
inspection date) and is never extracted from the sheet.  This file provides
extract() as a stub that always returns "" for it, but provides individual
extract functions for the 5 shipment dates.

All extracted values are normalised to MM/DD/YYYY by to_display_date().

To add a new date label → add to the relevant SYNONYMS list below.
To change normalisation → edit to_display_date() in extraction/core/normalise.py.
"""

from pathlib import Path
from typing import Optional

from final_summary.extraction.core import (
    CellGrid,
    DirectionRule,
    to_display_date,
    resolve_po_wh_value,
    resolve_value,
)

# ---------------------------------------------------------------------------
# Per-field synonym lists
# ---------------------------------------------------------------------------

EXF_SYNONYMS: list[str] = [
    "exf",
    "ex factory",
    "ex-factory",
    "ex factory date",
]

PO_EDT_SYNONYMS: list[str] = [
    "po edt",
    "p o edt",
    "po e d t",
    "po estimated delivery",
    "po delivery date",
]

PO_WH_SYNONYMS: list[str] = [
    "po w h",
    "po wh",
    "po w/h",
    "warehouse",
    "po warehouse",
    "po ship date",
]

PLAN_EDT_SYNONYMS: list[str] = [
    "plan etd",
    "plan e t d",
    "plan edt",
    "planned delivery",
    "plan estimated delivery",
]

PLAN_WH_SYNONYMS: list[str] = [
    "plan w h",
    "plan wh",
    "plan w/h",
    "plan warehouse",
]

# All dates scan right (value is in the next cell / cells)
_DIRECTION = DirectionRule.RIGHT


# ---------------------------------------------------------------------------
# Individual extractors — one per date field
# ---------------------------------------------------------------------------

def extract_exf(grid: CellGrid) -> str:
    """Extract EX-Factory date, normalised to MM/DD/YYYY."""
    for row, col, _ in grid.find_label_positions(EXF_SYNONYMS):
        raw = resolve_po_wh_value(grid, (row, col))
        if raw:
            return to_display_date(raw)
    return ""


def extract_po_edt(grid: CellGrid) -> str:
    """Extract PO EDT date, normalised to MM/DD/YYYY."""
    for row, col, _ in grid.find_label_positions(PO_EDT_SYNONYMS):
        raw = resolve_po_wh_value(grid, (row, col))
        if raw:
            return to_display_date(raw)
    return ""


def extract_po_wh(grid: CellGrid) -> str:
    """
    Extract PO W/H date.

    Uses resolve_po_wh_value which handles both single-cell dates and
    dates split across 3 cells (MM | DD | YYYY).
    Normalised to MM/DD/YYYY.
    """
    for row, col, _ in grid.find_label_positions(PO_WH_SYNONYMS):
        raw = resolve_po_wh_value(grid, (row, col))
        if raw:
            return to_display_date(raw)
    return ""


def extract_plan_edt(grid: CellGrid) -> str:
    """Extract Plan EDT date, normalised to MM/DD/YYYY."""
    for row, col, _ in grid.find_label_positions(PLAN_EDT_SYNONYMS):
        raw = resolve_po_wh_value(grid, (row, col))
        if raw:
            return to_display_date(raw)
    return ""


def extract_plan_wh(grid: CellGrid) -> str:
    """Extract Plan W/H date, normalised to MM/DD/YYYY."""
    for row, col, _ in grid.find_label_positions(PLAN_WH_SYNONYMS):
        raw = resolve_po_wh_value(grid, (row, col))
        if raw:
            return to_display_date(raw)
    return ""


# ---------------------------------------------------------------------------
# Unified extract() — returns all 5 date fields as a dict
# ---------------------------------------------------------------------------

def extract(
    grid: CellGrid,
    path: Optional[Path] = None,
) -> dict[str, str]:
    """
    Extract all 5 shipment date fields in one pass.

    date_of_issue is NOT extracted here — it is always injected from
    batch.inspection_date in the task layer.

    Parameters
    ----------
    grid : CellGrid for the sheet being processed
    path : unused

    Returns
    -------
    dict with keys: exf, po_edt, po_wh, plan_edt, plan_wh
    All values are MM/DD/YYYY strings or "" if not found.
    """
    return {
        "exf":      extract_exf(grid),
        "po_edt":   extract_po_edt(grid),
        "po_wh":    extract_po_wh(grid),
        "plan_edt": extract_plan_edt(grid),
        "plan_wh":  extract_plan_wh(grid),
    }