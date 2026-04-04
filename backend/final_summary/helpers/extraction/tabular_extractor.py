"""
tabular_extractor.py
--------------------
Extracts structured defect data from a rectangular Excel table range.

The caller supplies an Excel range string such as "B4:H38".  This module
converts that to row/column indices, identifies which column holds the
defect category names and which holds the "Major" counts, then reads every
row into a dict.

Column identification strategy (in order of priority)
------------------------------------------------------
1. Look for header cells containing the word "major" in the rows
   immediately above or at the top of the specified range.
2. If no header is found, pick the column with the most numeric values
   (heuristic – usually the major count column).
3. Fall back to the second column in the range.
"""

import logging
from typing import Dict, List, Tuple

from openpyxl.utils import range_boundaries

from ..core.cell_grid import CellGrid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_int(value: str) -> int:
    """Convert a string to int, returning 0 on failure."""
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0


def _is_numeric(value: str) -> bool:
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Column identification
# ---------------------------------------------------------------------------

def _find_major_column(
    grid: CellGrid,
    min_row: int,
    max_row: int,
    min_col: int,
    max_col: int,
) -> Tuple[int, int]:
    """
    Return (category_col, major_col) as 0-based column indices.

    Parameters use 1-based Excel coordinates (as returned by range_boundaries).
    """
    # Convert to 0-based for grid access
    min_col_0 = min_col - 1
    max_col_0 = max_col - 1
    min_row_0 = min_row - 1
    num_rows  = max_row - min_row + 1

    category_col = min_col_0   # first column → defect category names
    major_col: int | None = None

    # ── Strategy 1: scan header rows for a cell containing "major" ──────────
    # Check up to 3 rows above the table, plus the first row of the table.
    header_rows = list(range(max(1, min_row - 3), min_row + 1))
    header_rows_0 = [r - 1 for r in header_rows]   # convert to 0-based

    for hr in header_rows_0:
        for col in range(min_col_0, max_col_0 + 1):
            header_val = grid.get(hr, col)
            if header_val and "major" in header_val.strip().lower():
                major_col = col
                break
        if major_col is not None:
            break

    # ── Strategy 2: column with the most numeric values ──────────────────────
    if major_col is None:
        numeric_counts: Dict[int, int] = {}
        for col in range(min_col_0 + 1, max_col_0 + 1):
            count = sum(
                1 for row in range(min_row_0, min_row_0 + num_rows)
                if _is_numeric(grid.get(row, col))
            )
            numeric_counts[col] = count

        if numeric_counts:
            major_col = max(numeric_counts, key=numeric_counts.get)

    # ── Strategy 3: hard fallback ────────────────────────────────────────────
    if major_col is None:
        major_col = min_col_0 + 1

    return category_col, major_col


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_defect_table(
    grid: CellGrid,
    table_range: str,
) -> Dict[str, Dict[str, int]]:
    """
    Parse a rectangular defect table and return a nested dict.

    Return structure
    ----------------
    {
        "Incorrect Sewing": {"major": 3},
        "Wrong Label":      {"major": 1},
        ...
    }

    Parameters
    ----------
    grid        : CellGrid for the sheet containing the table
    table_range : Excel range string, e.g. "B4:H38"

    Returns an empty dict on any parse error.
    """
    if not table_range:
        logging.warning("extract_defect_table: no table_range provided")
        return {}

    # ── Parse range ──────────────────────────────────────────────────────────
    try:
        min_col, min_row, max_col, max_row = range_boundaries(table_range)
    except Exception as exc:
        logging.error(f"Invalid Excel range '{table_range}': {exc}")
        return {}

    if (max_col - min_col + 1) < 3:
        logging.error(
            f"Defect range '{table_range}' must be at least 3 columns wide "
            f"(category + major + minor)."
        )
        return {}

    # ── Identify columns ─────────────────────────────────────────────────────
    category_col, major_col = _find_major_column(
        grid, min_row, max_row, min_col, max_col
    )

    # ── Read data rows ───────────────────────────────────────────────────────
    defects: Dict[str, Dict[str, int]] = {}

    for row_1based in range(min_row, max_row + 1):
        row = row_1based - 1   # convert to 0-based

        category = grid.get(row, category_col)
        if not category or not category.strip():
            continue   # skip blank / header rows

        major_count = _to_int(grid.get(row, major_col))
        defects[category.strip()] = {"major": major_count}

    logging.info(
        f"extract_defect_table: extracted {len(defects)} defect categories "
        f"from range '{table_range}'"
    )
    return defects
