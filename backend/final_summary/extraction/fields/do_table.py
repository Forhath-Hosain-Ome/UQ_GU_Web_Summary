"""
------------------------------
Finds and extracts the Delivery Order (D.O.) plan table from any sheet in
the workbook, then returns structured rows ready to store on AuditReport.

This module is config-driven: column headers are discovered by matching
normalised cell text against DO_TABLE_LABELS — no column letters hardcoded.

To add a new column header spelling → add to DO_SYNONYMS below.
To add a new D.O. column           → add to DOFieldName in label_map.py,
                                      add synonym below, add to _build_do_row().
To change fill-down behaviour      → edit DO_FILL_DOWN_FIELDS in label_map.py.

Returns
-------
{
  "do_orders": [...],   # list of per-row dicts
  "do_totals": {...},   # {"ship_qty": N, "audit_qty": N}
  "do_note":   "...",   # any "#..." or "*..." note row
}
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from final_summary.extraction.core import (
    CellGrid,
    DOFieldName,
    DO_FILL_DOWN_FIELDS,
    normalize_text,
)
from final_summary.extraction.core.sheet_reader import read_all_sheets

# ---------------------------------------------------------------------------
# DO column synonym map
# Each DOFieldName key → list of normalised label synonyms
# ---------------------------------------------------------------------------

DO_SYNONYMS: Dict[str, List[str]] = {
    DOFieldName.DATE: [
        "date",
    ],
    DOFieldName.PO_QTY: [
        "po qty", "p o qty", "po quantity", "p o quantity",
    ],
    DOFieldName.DO_NO: [
        "do no", "d o no", "do number", "d o number", "delivery order no",
    ],
    DOFieldName.DO_QTY: [
        "do qty", "d o qty", "do quantity", "d o quantity",
    ],
    DOFieldName.SHIP_QTY: [
        "ship qty", "ship quantity", "shipment qty", "shipment quantity",
    ],
    DOFieldName.AUDIT_QTY: [
        "audit qty", "audit quantity", "audited qty",
    ],
    DOFieldName.DO_BALANCE: [
        "do balance", "d o balance", "do balance extra",
        "do balance and extra", "balance extra",
    ],
    DOFieldName.PO_EXTRA: [
        "po extra", "p o extra",
    ],
    DOFieldName.REMARKS: [
        "remarks", "balance qty plan", "balance qty plan date",
        "balance qty plan date remarks", "plan date remarks",
    ],
    DOFieldName.PO_BALANCE: [
        "po balance", "po bal",
    ],
}

_TOTAL_KEYWORDS = {"total", "totals", "grand total"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_total_row(cells: List[str]) -> bool:
    return any(
        normalize_text(c) in _TOTAL_KEYWORDS
        for c in cells if c.strip()
    )


def _is_note_row(cells: List[str]) -> bool:
    for c in cells:
        if c.strip():
            return c.strip()[0] in {"#", "*"}
    return False


def _is_special_note(value: str) -> bool:
    return bool(re.search(
        r"(random|re.?final|re.?audit|audit)",
        value, re.IGNORECASE,
    ))


def _to_int_or_none(value: str) -> Optional[int]:
    if not value or not value.strip():
        return None
    cleaned = re.sub(r"[^\d\-\.]", "", value.replace(",", ""))
    try:
        return int(float(cleaned))
    except (ValueError, TypeError):
        return None


def _format_date(value: str) -> Optional[str]:
    if not value:
        return None
    s = str(value).strip()
    if re.match(r"\d{1,2}-[A-Za-z]{3}-\d{2,4}", s):
        return s
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        from datetime import datetime
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return dt.strftime("%d-%b-%y")
        except ValueError:
            pass
    return s


# ---------------------------------------------------------------------------
# Header discovery
# ---------------------------------------------------------------------------

def _find_header_row(
    grid: CellGrid,
) -> Tuple[Optional[int], Dict[str, int]]:
    """
    Scan rows for the D.O. table header.

    Returns (header_row_0, {field_name: col_index_0}) or (None, {}).
    Requires at least 4 matched columns to be considered a valid header.
    """
    for row in range(grid.nrows):
        col_map: Dict[str, int] = {}

        for col in range(grid.ncols):
            raw = grid.get(row, col)
            if not raw:
                continue
            normalised = normalize_text(raw)

            for field_name, synonyms in DO_SYNONYMS.items():
                if field_name in col_map:
                    continue
                for syn in synonyms:
                    if normalised == syn or normalised.startswith(syn):
                        col_map[field_name] = col
                        break

        if len(col_map) >= 4:
            logging.info(f"DO table header at row {row}: {col_map}")
            return row, col_map

    return None, {}


# ---------------------------------------------------------------------------
# Single data-row builder
# ---------------------------------------------------------------------------

def _build_do_row(
    grid: CellGrid,
    row: int,
    col_map: Dict[str, int],
    fill_down: Dict[str, str],
) -> Tuple[Dict[str, Any], Optional[str]]:
    def _cell(field: str) -> str:
        col = col_map.get(field)
        return grid.get(row, col).strip() if col is not None else ""

    # Update fill-down for merged-cell columns
    for field in DO_FILL_DOWN_FIELDS:
        field_str = field.value if hasattr(field, "value") else str(field)
        raw = _cell(field_str)
        if raw:
            fill_down[field_str] = raw

    do_qty_raw = _cell("do_qty")
    do_no_raw  = _cell("do_no")
    special_note = None

    if _is_special_note(do_qty_raw):
        special_note = do_qty_raw
        do_qty_raw   = ""
    elif _is_special_note(do_no_raw):
        special_note = do_no_raw
        do_no_raw    = ""

    row_dict: Dict[str, Any] = {
        "date":                 _format_date(fill_down.get("date", "")) if fill_down.get("date") else None,
        "po_qty":               _to_int_or_none(fill_down.get("po_qty", "")),
        "do_no":                do_no_raw or None,
        "do_qty":               _to_int_or_none(do_qty_raw),
        "ship_qty":             _to_int_or_none(_cell("ship_qty")),
        "audit_qty":            _to_int_or_none(_cell("audit_qty")),
        "do_balance_and_extra": _to_int_or_none(_cell("do_balance")),
        "po_balance":           _to_int_or_none(_cell("po_balance")),
        "remarks":              _cell("remarks") or None,
        "special_note":         special_note,
    }
    return row_dict, special_note


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract(
    path: Path,
    sheet_name: Optional[str] = None,
    grid: Optional[CellGrid] = None,
) -> Dict[str, Any]:
    """
    Find the D.O. plan table anywhere in the workbook and extract all rows.

    Searches every sheet — the D.O. table is often on a different sheet
    from the main audit data.

    Parameters
    ----------
    path       : Path to the Excel file
    sheet_name : Hint — checked first but not required
    grid       : Unused (D.O. table may not be on the primary sheet)

    Returns
    -------
    dict with keys: do_orders, do_totals, do_note
    """
    all_dfs    = read_all_sheets(path)
    all_grids  = [CellGrid(df) for df in all_dfs]

    found_grid: Optional[CellGrid] = None
    header_row: Optional[int]      = None
    col_map:    Dict[str, int]      = {}

    for g in all_grids:
        h, cm = _find_header_row(g)
        if h is not None:
            found_grid = g
            header_row = h
            col_map    = cm
            break

    if found_grid is None or header_row is None:
        logging.warning(f"[{path.name}] DO table not found in any sheet.")
        return {"do_orders": [], "do_totals": {}, "do_note": ""}

    do_orders: List[Dict[str, Any]] = []
    totals:    Dict[str, Any]       = {}
    note:      str                  = ""
    fill_down: Dict[str, str]       = {}

    for row in range(header_row + 1, found_grid.nrows):
        row_cells = [found_grid.get(row, c) for c in range(found_grid.ncols)]
        non_empty = [c for c in row_cells if c.strip()]

        if not non_empty:
            continue

        if _is_note_row(row_cells):
            note = " ".join(non_empty).strip()
            continue

        if _is_total_row(row_cells):
            def _cell_t(field: str) -> str:
                col = col_map.get(field)
                return found_grid.get(row, col).strip() if col is not None else ""
            totals = {
                "ship_qty":  _to_int_or_none(_cell_t("ship_qty")),
                "audit_qty": _to_int_or_none(_cell_t("audit_qty")),
            }
            continue

        do_row, _ = _build_do_row(found_grid, row, col_map, fill_down)

        # Skip rows with no meaningful data
        values = [
            v for k, v in do_row.items()
            if k not in ("date", "po_qty") and v is not None
        ]
        if not values:
            continue

        do_orders.append(do_row)

    logging.info(
        f"[{path.name}] DO table: {len(do_orders)} row(s), totals={totals}"
    )
    return {
        "do_orders": do_orders,
        "do_totals": totals if totals else {},
        "do_note":   note,
    }