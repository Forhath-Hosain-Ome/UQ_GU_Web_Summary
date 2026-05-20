"""
-------------------------------
Extracts the style number from an audit report sheet.

Also derives the destination country from the first 2 characters of the
style number using STYLE_COUNTRY_MAP.  The country is returned as a second
value via extract_with_country() for callers that need both.

To change label text    → edit SYNONYMS
To change country codes → edit STYLE_COUNTRY_MAP in extraction/core/label_map.py
"""

from pathlib import Path
from typing import Optional, Tuple

from final_summary.extraction.core import (
    CellGrid,
    DirectionRule,
    STYLE_COUNTRY_MAP,
    resolve_value,
    find_inline_value,
)

# ---------------------------------------------------------------------------
# Field configuration
# ---------------------------------------------------------------------------

SYNONYMS: list[str] = [
    "style no",
    "style number",
    "item code",
    "style",
    "local sample code",
    "style no.",
    "style#",
]

DIRECTION = DirectionRule.DOWN


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

def extract(grid: CellGrid, path: Optional[Path] = None, format_type: str = "") -> str:
    """
    Find the style number label and return the value to its right.

    Parameters
    ----------
    grid : CellGrid for the sheet being processed
    path : unused

    Returns
    -------
    Style number string, or "" if not found.
    """
    positions = grid.find_label_positions(SYNONYMS)

    for row, col, cell_text in positions:
        for syn in SYNONYMS:
            value = find_inline_value(syn, cell_text)
            if value:
                return value

        value = resolve_value(grid, (row, col), DIRECTION)
        if value:
            return value

    return ""


def extract_with_country(
    grid: CellGrid,
    path: Optional[Path] = None,
    format_type: str = "",
) -> Tuple[str, str]:
    """
    Return (style_no, country) derived from the style number.

    Country is looked up from STYLE_COUNTRY_MAP using the first 2 characters
    of the style number.  Returns "UNKNOWN" for country if the prefix is not
    in the map or the style number is too short.

    Parameters
    ----------
    grid : CellGrid for the sheet being processed
    path : unused

    Returns
    -------
    (style_no, country) — both strings, never None.
    """
    style = extract(grid, path, format_type)
    if not style or len(style) < 2:
        return style, "UNKNOWN"
    country = STYLE_COUNTRY_MAP.get(style[:2].upper(), "UNKNOWN")
    return style, country