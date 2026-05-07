"""
--------------------------------
Extracts the Report Number (e.g. EU26-02CIPL-001) from an audit report sheet.

Report numbers share the same label text as PO numbers in some formats.
This file uses the validated pattern match from proximity.resolve_po_or_report_number
to ensure only a genuine Report Number is returned.

Pattern: [A-Z]{2}\d{2}-\d{2}[A-Z0-9]+-\d+   e.g. JP26-02BABL-001

To change label text  → edit SYNONYMS
To change the pattern → edit is_valid_report_no() in extraction/core/proximity.py
"""

from pathlib import Path
from typing import Optional

from extraction.core import (
    CellGrid,
    DirectionRule,
    resolve_po_or_report_number,
)

# ---------------------------------------------------------------------------
# Field configuration
# ---------------------------------------------------------------------------

SYNONYMS: list[str] = [
    "report no",
    "report number",
    "inspection report no",
    "report no.",
]

# Direction is irrelevant here — resolve_po_or_report_number always scans right.
DIRECTION = DirectionRule.RIGHT


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

def extract(grid: CellGrid, path: Optional[Path] = None) -> str:
    """
    Find the Report No label and return a validated report number.

    Uses resolve_po_or_report_number with field_name="report_no" so only
    values matching the Report Number pattern are accepted.  This prevents
    a PO number (which uses the same label in some sheets) from being stored
    as a report number.

    Parameters
    ----------
    grid : CellGrid for the sheet being processed
    path : unused

    Returns
    -------
    Report number string (e.g. "EU26-02CIPL-001"), or "" if not found.
    """
    positions = grid.find_label_positions(SYNONYMS)

    for row, col, _ in positions:
        value = resolve_po_or_report_number(grid, (row, col), field_name="report_no")
        if value:
            return value

    return ""