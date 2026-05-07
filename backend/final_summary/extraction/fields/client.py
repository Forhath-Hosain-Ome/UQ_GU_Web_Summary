"""
-----------------------------
Extracts the client / buyer name from an audit report sheet.

To change label text   → edit SYNONYMS
To change search dir   → edit DIRECTION
To change parse logic  → edit extract()
"""

from pathlib import Path
from typing import Optional

from extraction.core import (
    CellGrid,
    DirectionRule,
    resolve_value,
    find_inline_value,
)

# ---------------------------------------------------------------------------
# Field configuration
# ---------------------------------------------------------------------------

SYNONYMS: list[str] = [
    "client",
    "client name",
    "buyer",
    "buyer name",
    "client:",
    "buyer:",
]

DIRECTION = DirectionRule.RIGHT


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

def extract(grid: CellGrid, path: Optional[Path] = None) -> str:
    """
    Find the client / buyer label and return the value to its right.

    Parameters
    ----------
    grid : CellGrid for the sheet being processed
    path : unused

    Returns
    -------
    Extracted client name string, or "" if not found.
    """
    positions = grid.find_label_positions(SYNONYMS)

    for row, col, cell_text in positions:
        # Try inline: "Client: UNIQLO"
        for syn in SYNONYMS:
            value = find_inline_value(syn, cell_text)
            if value:
                return value

        value = resolve_value(grid, (row, col), DIRECTION)
        if value:
            return value

    return ""