"""
---------------------------------
Extracts all quantity fields from an audit report sheet.

Fields handled:
  - po_qty        (raw PO quantity string, e.g. "1200 PCS")
  - po_qty_pcs    (derived integer — PCS component)
  - po_qty_pack   (derived integer — PACK component)
  - po_qty_set    (derived integer — SET component)
  - do_qty        (Delivery Order quantity)
  - ship_qty      (Shipment quantity)
  - audit_qty     (Audited quantity)
  - defect_qty    (Major defect count from summary row)
  - defect_percentage (derived: defect_qty / audit_qty * 100)
  - acceptable_defect_qty (AQL acceptable defect level)

PO Qty routing
--------------
"1200 PCS"  → po_qty_pcs  = 1200
"300 SET"   → po_qty_set  = 300
"500 PACK"  → po_qty_pack = 500
bare "1200" → po_qty_pcs  = 1200  (default unit)

Defect qty fallback
-------------------
If the "Major Defects" label extraction returns nothing, a secondary scan
looks for the second occurrence of any "major" cell and reads the integer
to its right (the sub-total row rather than the column header row).

To add a new label → add to the relevant SYNONYMS list.
To change PO unit routing → edit _PO_UNIT_MAP below.
"""

import logging
import re
from pathlib import Path
from typing import Optional

from final_summary.extraction.core import (
    CellGrid,
    DirectionRule,
    to_int,
    calc_defect_percentage,
    extract_first_number,
    resolve_value,
)

# ---------------------------------------------------------------------------
# Per-field synonym lists
# ---------------------------------------------------------------------------

PO_QTY_SYNONYMS: list[str] = [
    "po qty",
    "p.o qty",
    "p.o. qty",
    "p o qty",
    "po quantity",
    "p o quantity",
    "po qty.",
]

DO_QTY_SYNONYMS: list[str] = [
    "do qty",
    "d o qty",
    "do quantity",
    "delivery order qty",
    "d o quantity",
]

SHIP_QTY_SYNONYMS: list[str] = [
    "ship qty",
    "shipment qty",
    "shipping quantity",
    "shipping qty",
    "audit for shipping qty",
    "exf qty",
    "shipment quantity",
]

AUDIT_QTY_SYNONYMS: list[str] = [
    "audit qty",
    "audited quantity",
    "qty inspected",
    "audited qty",
    "inspection qty",
]

DEFECT_QTY_SYNONYMS: list[str] = [
    "major defects",
    "major defect",
    "total major",
]

ACCEPTABLE_DEFECT_SYNONYMS: list[str] = [
    "acceptable defect qty",
    "acceptable defect",
    "aql defect",
    "acceptable qty",
    "acceptable no",
]

# PO Qty: try the cell below (merged header pattern) before scanning right
_PO_DIRECTION = [DirectionRule.DOWN_IF_INT, DirectionRule.RIGHT]
_DO_DIRECTION = [DirectionRule.DOWN_IF_INT, DirectionRule.RIGHT]
_DEFAULT_DIRECTION = DirectionRule.RIGHT

# Unit → field name for PO qty routing
_PO_UNIT_MAP: dict[str, str] = {
    "pcs":  "po_qty_pcs",
    "pack": "po_qty_pack",
    "set":  "po_qty_set",
}


# ---------------------------------------------------------------------------
# PO qty parser
# ---------------------------------------------------------------------------

def _parse_po_qty(raw: str) -> dict[str, int]:
    """
    Parse a raw PO qty string and return typed qty fields.

    "1200 PCS"  → {"po_qty_pcs": 1200, "po_qty_pack": 0, "po_qty_set": 0}
    "300 SET"   → {"po_qty_pcs": 0, "po_qty_pack": 0, "po_qty_set": 300}
    bare "1200" → {"po_qty_pcs": 1200, "po_qty_pack": 0, "po_qty_set": 0}
    """
    result = {"po_qty_pcs": 0, "po_qty_pack": 0, "po_qty_set": 0}
    if not raw:
        return result

    numeric_str = extract_first_number(raw)
    if not numeric_str:
        return result

    numeric = int(float(numeric_str))
    raw_lower = raw.strip().lower()

    target = "po_qty_pcs"  # default
    for keyword, field_name in _PO_UNIT_MAP.items():
        if keyword in raw_lower:
            target = field_name
            break

    result[target] = numeric
    return result


# ---------------------------------------------------------------------------
# Defect qty fallback (second "major" label scan)
# ---------------------------------------------------------------------------

def _defect_qty_fallback(grid: CellGrid) -> str:
    """
    Secondary scan: find the second cell containing the word "major" and
    return the integer value to its right.

    The first "major" occurrence is usually the column header in the defect
    table; the second is the sub-total row — which is what we want.
    """
    major_positions = []

    for row in range(grid.nrows):
        for col in range(grid.ncols):
            cell = grid.get(row, col)
            if cell and "major" in cell.lower().strip():
                major_positions.append((row, col))

    major_positions.sort(key=lambda x: x[0])

    if len(major_positions) < 2:
        logging.debug("defect_qty fallback: fewer than 2 'major' labels found")
        return ""

    r, c = major_positions[1]
    for col in range(c + 1, min(c + 6, grid.ncols)):
        raw = grid.get(r, col).strip()
        if not raw:
            continue
        try:
            int(float(raw))
            return raw
        except (ValueError, TypeError):
            continue

    return ""


# ---------------------------------------------------------------------------
# Unified extract() — returns all quantity fields as a dict
# ---------------------------------------------------------------------------

def extract(
    grid: CellGrid,
    path: Optional[Path] = None,
) -> dict[str, str | int]:
    """
    Extract all quantity fields in one pass and derive calculated fields.

    Parameters
    ----------
    grid : CellGrid for the sheet being processed
    path : unused

    Returns
    -------
    dict with keys:
      po_qty, po_qty_pcs, po_qty_pack, po_qty_set,
      do_qty, ship_qty, audit_qty,
      defect_qty, acceptable_defect_qty, defect_percentage
    """
    result: dict = {}

    # ── PO Qty (raw + parsed) ──────────────────────────────────────────────
    po_qty_raw = ""
    for row, col, _ in grid.find_label_positions(PO_QTY_SYNONYMS):
        raw = resolve_value(grid, (row, col), _PO_DIRECTION)
        if raw:
            po_qty_raw = raw
            break

    result["po_qty"] = po_qty_raw
    result.update(_parse_po_qty(po_qty_raw))

    # ── DO Qty ────────────────────────────────────────────────────────────
    do_qty = ""
    for row, col, _ in grid.find_label_positions(DO_QTY_SYNONYMS):
        raw = resolve_value(grid, (row, col), _DO_DIRECTION)
        if raw:
            do_qty = extract_first_number(raw)
            break
    result["do_qty"] = do_qty

    # ── Ship Qty ──────────────────────────────────────────────────────────
    ship_qty = ""
    for row, col, _ in grid.find_label_positions(SHIP_QTY_SYNONYMS):
        raw = resolve_value(grid, (row, col), _DEFAULT_DIRECTION)
        if raw:
            ship_qty = extract_first_number(raw)
            break
    result["ship_qty"] = ship_qty

    # ── Audit Qty ─────────────────────────────────────────────────────────
    audit_qty = ""
    for row, col, _ in grid.find_label_positions(AUDIT_QTY_SYNONYMS):
        raw = resolve_value(grid, (row, col), _DEFAULT_DIRECTION)
        if raw:
            audit_qty = extract_first_number(raw)
            break
    result["audit_qty"] = audit_qty

    # ── Defect Qty (primary label, then fallback) ─────────────────────────
    defect_qty = ""
    for row, col, _ in grid.find_label_positions(DEFECT_QTY_SYNONYMS):
        raw = resolve_value(grid, (row, col), _DEFAULT_DIRECTION)
        if raw:
            defect_qty = extract_first_number(raw)
            break

    if not defect_qty:
        defect_qty = _defect_qty_fallback(grid)

    result["defect_qty"] = defect_qty

    # ── Acceptable Defect Qty ─────────────────────────────────────────────
    acceptable = ""
    for row, col, _ in grid.find_label_positions(ACCEPTABLE_DEFECT_SYNONYMS):
        raw = resolve_value(grid, (row, col), _DEFAULT_DIRECTION)
        if raw:
            acceptable = raw
            break
    result["acceptable_defect_qty"] = acceptable

    # ── Derived: Defect Percentage ─────────────────────────────────────────
    result["defect_percentage"] = calc_defect_percentage(defect_qty, audit_qty)

    return result