"""
do_table_extractor.py
---------------------
Finds and extracts the Delivery Order (D.O.) plan table from any sheet in
an Excel workbook, then stores the rows directly on AuditRecord.do_orders.

This module is fully config-driven: column headers are discovered by matching
normalised cell text against  DO_TABLE_LABELS  in label_config.py —
no column letters or positions are hardcoded.

Where to make changes
---------------------
- New header spelling       → enums/field_enums.py  (DOLabelSynonym)
                              extraction/label_config.py  (DO_TABLE_LABELS)
- New column                → enums/field_enums.py  (DOFieldName + DOLabelSynonym)
                              extraction/label_config.py  (DO_TABLE_LABELS)
                              _build_do_row() below  (read the new field)
- Fill-down (merged cells)  → extraction/label_config.py  (DO_FILL_DOWN_FIELDS)

Output stored on record
-----------------------
record.do_orders = [
    {
        "date":                 "22-Jan-26",
        "po_qty":               48000,
        "do_no":                "01",
        "do_qty":               48000,
        "ship_qty":             15132,
        "audit_qty":            378,
        "do_balance_and_extra": -32868,
        "po_balance":           -17688,
        "remarks":              "PO & DO BALANCE",
        "special_note":         null
    },
    ...
]
record.do_totals  = {"ship_qty": 30312, "audit_qty": 1636}
record.do_note    = "#OUR INSPECTION CARTON NUMBER: ..."
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from ..core.cell_grid import CellGrid, normalize_text
from ..core.sheet_reader import read_all_sheets
from .label_config import DO_TABLE_LABELS, DO_FILL_DOWN_FIELDS


# ---------------------------------------------------------------------------
# Row classification helpers
# ---------------------------------------------------------------------------

_TOTAL_KEYWORDS = {"total", "totals", "grand total"}


def _is_total_row(cells: List[str]) -> bool:
    return any(normalize_text(c) in _TOTAL_KEYWORDS for c in cells if c.strip())


def _is_note_row(cells: List[str]) -> bool:
    for c in cells:
        if c.strip():
            return c.strip()[0] in {"#", "*"}
    return False


def _is_special_note(value: str) -> bool:
    """Cells like 'RANDOM FINAL (15,180) PCS' or '1st TIME RE-FINAL AUDIT…'."""
    return bool(re.search(r"(random|re.?final|re.?audit|audit)", value, re.IGNORECASE))


# ---------------------------------------------------------------------------
# Numeric helper
# ---------------------------------------------------------------------------

def _to_int_or_none(value: str) -> Optional[int]:
    if not value or not value.strip():
        return None
    # Strip everything except digits, minus, dot
    cleaned = re.sub(r"[^\d\-\.]", "", value.replace(",", ""))
    try:
        return int(float(cleaned))
    except (ValueError, TypeError):
        return None


def _format_date(value: str) -> Optional[str]:
    """Convert '2026-01-22 00:00:00' or datetime objects to '22-Jan-26'."""
    if not value:
        return None
    s = str(value).strip()
    # Already a nice string like "22-Jan-26"
    if re.match(r"\d{1,2}-[A-Za-z]{3}-\d{2,4}", s):
        return s
    # Excel datetime string "2026-01-22 00:00:00"
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
# Header discovery  (driven by DO_TABLE_LABELS config)
# ---------------------------------------------------------------------------

def _find_header_row(
    grid: CellGrid,
    min_row_0: int,
    max_row_0: int,
    min_col_0: int,
    max_col_0: int,
) -> Tuple[Optional[int], Dict[str, int]]:
    """
    Scan rows looking for the header row of the D.O. table.
    Matches each cell against every synonym defined in DO_TABLE_LABELS.

    Returns (header_row_0, {field_name: col_index_0}) or (None, {}).
    """
    # Search the full sheet range - table can be anywhere (not just top 5 rows)
    for row in range(min_row_0, max_row_0 + 1):
        col_map: Dict[str, int] = {}

        for col in range(min_col_0, max_col_0 + 1):
            raw = grid.get(row, col)
            if not raw:
                continue
            normalised = normalize_text(raw)

            for field_name, synonyms in DO_TABLE_LABELS.items():
                if field_name in col_map:
                    continue
                for syn in synonyms:
                    syn_str = syn.value if hasattr(syn, "value") else str(syn)
                    if normalised == syn_str or normalised.startswith(syn_str):
                        col_map[field_name] = col
                        logging.debug(
                            f"  DO header: col {col} '{raw}' "
                            f"→ '{field_name}' via '{syn_str}'"
                        )
                        break

        # Valid header: must match at least 4 defined columns
        if len(col_map) >= 4:
            logging.info(
                f"DO table header at row {row}: {dict(col_map)}"
            )
            return row, col_map

    return None, {}


# ---------------------------------------------------------------------------
# Auto-detect which sheet and row range contains the D.O. table
# ---------------------------------------------------------------------------

def _find_do_table_in_sheets(
    all_sheets: List[CellGrid],
) -> Tuple[Optional[CellGrid], Optional[int], Dict[str, int]]:
    """
    Try every sheet until a D.O. header row is found.

    Returns (grid, header_row_0, col_map) or (None, None, {}).
    """
    for grid in all_sheets:
        header_row_0, col_map = _find_header_row(
            grid,
            min_row_0=0,
            max_row_0=grid.nrows - 1,
            min_col_0=0,
            max_col_0=grid.ncols - 1,
        )
        if header_row_0 is not None:
            return grid, header_row_0, col_map

    return None, None, {}


# ---------------------------------------------------------------------------
# Single data-row builder
# ---------------------------------------------------------------------------

def _build_do_row(
    grid: CellGrid,
    row: int,
    col_map: Dict[str, int],
    fill_down: Dict[str, str],
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Build one D.O. row dict from grid row *row*.

    fill_down is mutated in place to carry merged-cell values forward.
    Returns (row_dict, special_note_str_or_None).
    """
    def _cell(field: str) -> str:
        col = col_map.get(field)
        return grid.get(row, col).strip() if col is not None else ""

    # ── Update fill-down for merged-cell columns ──────────────────────────────
    for field in DO_FILL_DOWN_FIELDS:
        field_str = field.value if hasattr(field, "value") else str(field)
        raw = _cell(field_str)
        if raw:
            fill_down[field_str] = raw

    # ── Detect special audit note in D.O QTY cell (merged-cell special rows) ─
    do_qty_raw   = _cell("do_qty")
    do_no_raw    = _cell("do_no")
    special_note = None

    if _is_special_note(do_qty_raw):
        special_note = do_qty_raw
        do_qty_raw   = ""
    elif _is_special_note(do_no_raw):
        special_note = do_no_raw
        do_no_raw    = ""

    row_dict: Dict[str, Any] = {
        # Carry-forward (merged) fields
        "date":    _format_date(fill_down.get("date", "")) if fill_down.get("date") else None,
        "po_qty":  _to_int_or_none(fill_down.get("po_qty", "")),

        # Per-row fields
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
# Public API  –  called from main.py / process_file()
# ---------------------------------------------------------------------------

def extract_do_table_to_record(record: Any, path: Any) -> None:
    """
    Find the D.O. plan table anywhere in the workbook, extract all rows,
    and store them on record.do_orders / record.do_totals / record.do_note.

    Parameters
    ----------
    record : AuditRecord  (mutated in place)
    path   : pathlib.Path to the Excel file
    """
    from ..core.cell_grid import CellGrid
    from ..core.sheet_reader import read_all_sheets

    all_dfs   = read_all_sheets(path)
    all_grids = [CellGrid(df) for df in all_dfs]

    grid, header_row_0, col_map = _find_do_table_in_sheets(all_grids)

    if grid is None or header_row_0 is None:
        logging.warning(f"[{record.file_name}] DO table not found in any sheet")
        return

    # ── Walk data rows ────────────────────────────────────────────────────────
    do_orders: List[Dict[str, Any]] = []
    totals:    Dict[str, Any]       = {}
    note:      str                  = ""
    fill_down: Dict[str, str]       = {}

    for row in range(header_row_0 + 1, grid.nrows):
        row_cells = [grid.get(row, c) for c in range(grid.ncols)]
        non_empty = [c for c in row_cells if c.strip()]

        if not non_empty:
            continue

        if _is_note_row(row_cells):
            note = " ".join(non_empty).strip()
            logging.info(f"  DO note: '{note[:80]}...'")
            continue

        if _is_total_row(row_cells):
            def _cell_t(field: str) -> str:
                col = col_map.get(field)
                return grid.get(row, col).strip() if col is not None else ""
            totals = {
                "ship_qty":  _to_int_or_none(_cell_t("ship_qty")),
                "audit_qty": _to_int_or_none(_cell_t("audit_qty")),
            }
            logging.info(f"  DO totals: {totals}")
            continue

        do_row, _ = _build_do_row(grid, row, col_map, fill_down)

        # Skip rows that have absolutely no data
        values = [v for k, v in do_row.items()
                  if k not in ("date", "po_qty") and v is not None]
        if not values:
            continue

        do_orders.append(do_row)
        logging.debug(f"  DO row: {do_row}")

    # ── Store on record ───────────────────────────────────────────────────────
    record.do_orders = do_orders
    record.do_totals = totals if totals else {}
    record.do_note   = note or ""

    logging.info(
        f"[{record.file_name}] DO table: "
        f"{len(do_orders)} row(s), totals={totals}"
    )
