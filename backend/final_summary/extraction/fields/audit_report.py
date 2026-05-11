"""
------------------------------------
Extracts the Audit Report Number field.

Some sheet formats have both a PO-style number AND a Report-style number
under the same label.  This extractor accepts either pattern and falls back
to the raw cell value so nothing is lost.

To change label text  → edit SYNONYMS
To change the pattern → edit is_valid_report_no / is_valid_po_no in proximity.py
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
    "report number",
    "report no",
    "inspection report no",
    "audit report no",
    "report no.",
]

DIRECTION = DirectionRule.RIGHT


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

def extract(grid: CellGrid, path: Optional[Path] = None, format_type: str = "") -> str:
    """
    Find the Audit Report label and return the number found to its right.

    Accepts both Report Number (EU26-...) and PO Number (P0426-...) patterns.
    Falls back to the raw cell value if neither pattern matches, so the field
    is never silently dropped.

    Parameters
    ----------
    grid : CellGrid for the sheet being processed
    path : unused

    Returns
    -------
    Audit report number string, or "" if not found.
    """
    positions = grid.find_label_positions(SYNONYMS)

    for row, col, _ in positions:
        value = resolve_po_or_report_number(grid, (row, col), field_name="audit_report")
        if value:
            return value

    return ""