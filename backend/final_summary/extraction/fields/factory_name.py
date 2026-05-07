"""
-----------------------------------
Extracts the factory name from an audit report sheet.

To change label text   → edit SYNONYMS
To change search dir   → edit DIRECTION
To change parse logic  → edit extract()
Nothing else needs to change anywhere.
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
# Field configuration — edit here to add new label variants
# ---------------------------------------------------------------------------

SYNONYMS: list[str] = [
    "factory name",
    "factory",
    "factory name:",
    "factory:",
]

DIRECTION = DirectionRule.RIGHT


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

def extract(grid: CellGrid, path: Optional[Path] = None) -> str:
    """
    Find the factory name label and return the value to its right.

    Tries every synonym in SYNONYMS until a non-empty value is found.
    Also handles "Factory Name: ABC Ltd" packed into a single cell (inline).

    Parameters
    ----------
    grid : CellGrid for the sheet being processed
    path : unused — included for a uniform signature across all field files

    Returns
    -------
    Extracted factory name string, or "" if not found.
    """
    positions = grid.find_label_positions(SYNONYMS)

    for row, col, cell_text in positions:
        # Try inline first: "Factory Name: ABC Garments Ltd"
        for syn in SYNONYMS:
            value = find_inline_value(syn, cell_text)
            if value:
                return value

        # Proximity: value in adjacent cell
        value = resolve_value(grid, (row, col), DIRECTION)
        if value:
            return value

    return ""