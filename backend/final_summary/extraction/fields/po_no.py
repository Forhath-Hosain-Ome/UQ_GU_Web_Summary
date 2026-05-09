"""
----------------------------
Extracts the PO Number (e.g. P0426-485655-006) from an audit report sheet.

Uses pattern validation to distinguish PO numbers from Report numbers that
share the same label in some formats.

Pattern: P\d{4}-\d{6}-\d{3}(-\d+)*   e.g. P0726-482920-005-1-2

To change label text  → edit SYNONYMS
To change the pattern → edit is_valid_po_no() in extraction/core/proximity.py
"""

from pathlib import Path
from typing import Optional

from final_summary.extraction.core import (
    CellGrid,
    DirectionRule,
    resolve_po_or_report_number,
)

# ---------------------------------------------------------------------------
# Field configuration
# ---------------------------------------------------------------------------

SYNONYMS: list[str] = [
    "po no",
    "p o no",
    "po number",
    "purchase order no",
    "po no.",
    "p.o. no",
    "p.o no",
]

DIRECTION = DirectionRule.RIGHT


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

def extract(grid: CellGrid, path: Optional[Path] = None) -> str:
    """
    Find the PO number label and return a validated PO number.

    Uses resolve_po_or_report_number with field_name="po_no" so only values
    matching the PO number pattern (P0426-...) are accepted.

    Parameters
    ----------
    grid : CellGrid for the sheet being processed
    path : unused

    Returns
    -------
    PO number string (e.g. "P0426-485655-006"), or "" if not found.
    """
    positions = grid.find_label_positions(SYNONYMS)

    for row, col, _ in positions:
        value = resolve_po_or_report_number(grid, (row, col), field_name="po_no")
        if value:
            return value

    return ""