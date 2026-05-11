"""
extraction/fields/quantities.py
---------------------------------
Extracts all quantity fields from an audit report sheet.

Fields handled
--------------
  po_qty, po_qty_pcs, po_qty_pack, po_qty_set
  do_qty, ship_qty, audit_qty
  defect_qty, defect_percentage, acceptable_defect_qty

Three-stage extraction per field
---------------------------------
1. LABEL SEARCH   — scan for known label synonyms + configured direction
2. PATTERN SEARCH — scan grid for cells matching a numeric pattern
3. FIXED CELL     — format-specific known cell position as last resort

PQC format specifics (WOVEN_78)
---------------------------------
  ship_qty  : label "出荷予定数(EXF QTY)：" R43C21 → value R44C21 (DOWN, not RIGHT)
  audit_qty : label "検査数\\nInspection quantity" R48C21 → value R48C23 (RIGHT ✓)
  defect_qty: label "重不良\\nMajor" R50C21 → value R50C23 (RIGHT ✓)

Fixed cell fallback positions (0-based) by format_type
-------------------------------------------------------
  WOVEN_78:
    ship_qty   → R43 C20  (row 44, col 21 in 1-based)
    audit_qty  → R47 C22  (row 48, col 23)
    defect_qty → R49 C22  (row 50, col 23)

To add new synonyms  → edit the relevant *_SYNONYMS list
To add a fixed cell  → add to FORMAT_FIXED_CELLS
To change direction  → edit the direction constant for that field
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
    "po qty", "p o qty", "po quantity", "p o quantity", "po qty.",
]

DO_QTY_SYNONYMS: list[str] = [
    "do qty", "d o qty", "do quantity", "delivery order qty", "d o quantity",
]

SHIP_QTY_SYNONYMS: list[str] = [
    "ship qty", "shipment qty", "shipping quantity", "shipping qty",
    "audit for shipping qty",
    "exf qty",                   # "出荷予定数(EXF QTY)：" → "exf qty" ✓
    "shipment quantity",
    "fqc inspection pass qty total",  # PQC row 73
    "total ship qty",
]

AUDIT_QTY_SYNONYMS: list[str] = [
    "audit qty", "audited quantity", "qty inspected", "audited qty",
    "inspection qty",
    "inspection quantity",       # "検査数\nInspection quantity" → "inspection quantity" ✓
    "total audit qty",           # PQC row 73
    "1st audit quantity",
]

DEFECT_QTY_SYNONYMS: list[str] = [
    "major defects", "major defect", "total major",
    "major",                     # "重不良\nMajor" → "major" ✓
    "total no of defect",        # PQC row 41
]

ACCEPTABLE_DEFECT_SYNONYMS: list[str] = [
    "acceptable defect qty", "acceptable defect", "aql defect",
    "acceptable qty", "acceptable no",
    "acceptable defect qty",
]

# Directions per field
_PO_DIR       = [DirectionRule.DOWN_IF_INT, DirectionRule.RIGHT]
_DO_DIR       = [DirectionRule.DOWN_IF_INT, DirectionRule.RIGHT]
_SHIP_DIR     = [DirectionRule.DOWN_IF_INT, DirectionRule.RIGHT]  # DOWN first for PQC
_DEFAULT_DIR  = DirectionRule.RIGHT

# PO unit routing
_PO_UNIT_MAP: dict[str, str] = {
    "pcs":  "po_qty_pcs",
    "pack": "po_qty_pack",
    "set":  "po_qty_set",
}

# ---------------------------------------------------------------------------
# Fixed cell fallbacks — {format_type: {field: (row_0based, col_0based)}}
# ---------------------------------------------------------------------------

FORMAT_FIXED_CELLS: dict[str, dict[str, tuple[int, int]]] = {
    "WOVEN_78": {
        "ship_qty":   (43, 20),   # R44 C21
        "audit_qty":  (47, 22),   # R48 C23
        "defect_qty": (49, 22),   # R50 C23
    },
}


# ---------------------------------------------------------------------------
# PO qty parser
# ---------------------------------------------------------------------------

def _parse_po_qty(raw: str) -> dict[str, int]:
    result = {"po_qty_pcs": 0, "po_qty_pack": 0, "po_qty_set": 0}
    if not raw:
        return result
    numeric_str = extract_first_number(raw)
    if not numeric_str:
        return result
    numeric     = int(float(numeric_str))
    raw_lower   = raw.strip().lower()
    target      = "po_qty_pcs"
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
    Find the second cell containing the word 'major' and return the
    integer value to its right (the sub-total row, not the column header).
    """
    major_positions = []
    for row in range(grid.nrows):
        for col in range(grid.ncols):
            cell = grid.get(row, col)
            if cell and "major" in cell.lower().strip():
                major_positions.append((row, col))
    major_positions.sort(key=lambda x: x[0])

    if len(major_positions) < 2:
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
# Internal extract helper
# ---------------------------------------------------------------------------

def _extract_qty(
    grid: CellGrid,
    synonyms: list[str],
    direction,
    field_name: str,
    format_type: str,
) -> str:
    """
    Three-stage extraction for a single quantity field.
    Returns the raw string value or "".
    """
    # Stage 1: label search
    for row, col, _ in grid.find_label_positions(synonyms):
        raw = resolve_value(grid, (row, col), direction)
        if raw:
            return extract_first_number(raw) or raw

    # Stage 2: fixed cell fallback
    if format_type in FORMAT_FIXED_CELLS:
        cell_map = FORMAT_FIXED_CELLS[format_type]
        if field_name in cell_map:
            r, c = cell_map[field_name]
            raw = grid.get(r, c)
            if raw and raw.strip():
                return extract_first_number(raw) or raw.strip()

    return ""


# ---------------------------------------------------------------------------
# Unified extract()
# ---------------------------------------------------------------------------

def extract(
    grid: CellGrid,
    path: Optional[Path] = None,
    format_type: str = "",
) -> dict[str, str | int]:
    """
    Extract all quantity fields in one pass.

    Parameters
    ----------
    grid        : CellGrid for the sheet being processed
    path        : unused
    format_type : BuyerFactoryPair.report_type — used for fixed-cell fallback

    Returns
    -------
    dict with keys:
      po_qty, po_qty_pcs, po_qty_pack, po_qty_set,
      do_qty, ship_qty, audit_qty,
      defect_qty, acceptable_defect_qty, defect_percentage
    """
    result: dict = {}

    # ── PO Qty ────────────────────────────────────────────────────────────
    po_qty_raw = _extract_qty(grid, PO_QTY_SYNONYMS, _PO_DIR, "po_qty", format_type)
    result["po_qty"] = po_qty_raw
    result.update(_parse_po_qty(po_qty_raw))

    # ── DO Qty ────────────────────────────────────────────────────────────
    result["do_qty"] = _extract_qty(grid, DO_QTY_SYNONYMS, _DO_DIR, "do_qty", format_type)

    # ── Ship Qty ──────────────────────────────────────────────────────────
    ship_qty = _extract_qty(grid, SHIP_QTY_SYNONYMS, _SHIP_DIR, "ship_qty", format_type)
    result["ship_qty"] = ship_qty

    # ── Audit Qty ─────────────────────────────────────────────────────────
    audit_qty = _extract_qty(grid, AUDIT_QTY_SYNONYMS, _DEFAULT_DIR, "audit_qty", format_type)
    result["audit_qty"] = audit_qty

    # ── Defect Qty ────────────────────────────────────────────────────────
    defect_qty = _extract_qty(grid, DEFECT_QTY_SYNONYMS, _DEFAULT_DIR, "defect_qty", format_type)
    if not defect_qty:
        defect_qty = _defect_qty_fallback(grid)
    result["defect_qty"] = defect_qty

    # ── Acceptable Defect ─────────────────────────────────────────────────
    acceptable = ""
    for row, col, _ in grid.find_label_positions(ACCEPTABLE_DEFECT_SYNONYMS):
        raw = resolve_value(grid, (row, col), _DEFAULT_DIR)
        if raw:
            acceptable = raw
            break
    result["acceptable_defect_qty"] = acceptable

    # ── Derived: Defect % ─────────────────────────────────────────────────
    result["defect_percentage"] = calc_defect_percentage(defect_qty, audit_qty)

    return result