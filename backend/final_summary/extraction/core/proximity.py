"""
-----------------------------
Functions that locate a field's VALUE relative to its LABEL cell.

Moved from helpers/extraction/proximity.py.
Import updated: CellGrid now comes from extraction.core.cell_grid.
No logic changes.

Core function : resolve_value()
  Given a label position and a direction rule, scans adjacent cells until
  a non-empty string is found.

Special handlers
  resolve_po_wh_value()         – date may span 3 cells (MM | DD | YYYY).
  resolve_po_or_report_number() – validates PO vs Report number patterns.
  find_inline_value()           – extracts "LABEL: value" from a single cell.
"""

import logging
import re
from typing import Any, List, Tuple

from .cell_grid import CellGrid


# ---------------------------------------------------------------------------
# Type-check helpers
# ---------------------------------------------------------------------------

def is_int(s: str) -> bool:
    """True if *s* can be parsed as an integer."""
    try:
        int(s)
        return True
    except (ValueError, TypeError):
        return False


def is_date_format(s: str) -> bool:
    """True if *s* looks like a complete date (e.g. 12/31/2024)."""
    if not s:
        return False
    return bool(re.match(r"^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$", s.strip()))


def is_valid_month_or_day(value: str) -> bool:
    """True if *value* is an integer in [1, 31] (valid MM or DD)."""
    try:
        return 1 <= int(value.strip()) <= 31
    except (ValueError, TypeError):
        return False


def is_valid_year(value: str) -> bool:
    """True if *value* is a plausible 4-digit year (1900–2100)."""
    try:
        return 1900 <= int(value.strip()) <= 2100
    except (ValueError, TypeError):
        return False


def is_valid_po_no(value: str) -> bool:
    """
    True if *value* matches the PO number pattern.
    Valid: P0726-482920-005  or  P0726-482920-005-1-2
    """
    if not value:
        return False
    return bool(re.match(r"^P\d{4}-\d{6}-\d{3}(?:-\d+)*$", value.strip()))


def is_valid_report_no(value: str) -> bool:
    """
    True if *value* matches the Report number pattern.
    Valid: EU26-02CIPL-001.
    Strips trailing punctuation before matching.
    """
    if not value:
        return False
    cleaned = value.strip().rstrip(".,;:")
    # Use the same flexible pattern as the search engine
    pat = r"[A-Z]{1,2}\s*\d{0,2}\s*[-\s]?\s*\d{2}\s*[-/]?\s*[A-Z0-9]{2,}\s*[-/]?\s*\d+"
    return bool(re.search(pat, cleaned, re.IGNORECASE))


# ---------------------------------------------------------------------------
# Inline-value extraction  (e.g. "LABEL: value" in a single cell)
# ---------------------------------------------------------------------------

def find_inline_value(label_text: str, cell_text: str) -> str:
    """
    If *cell_text* contains the label followed by a separator and a value,
    return the value part.  Returns "" otherwise.

    Example
    -------
    label_text = "factory"
    cell_text  = "Factory: ABC Garments Ltd"
    → returns "ABC Garments Ltd"
    """
    if not cell_text or not label_text:
        return ""

    lower_cell  = cell_text.lower().strip()
    lower_label = label_text.lower().strip()

    # Cell is exactly the label — no trailing value
    if lower_cell == lower_label or lower_cell == lower_label.rstrip(":- "):
        return ""

    label_core = lower_label.rstrip(":- ").strip()
    if label_core not in lower_cell:
        return ""

    # Split on the first recognised separator
    for sep in [":", "-", "\u2013", "\u2014"]:  # colon, hyphen, en-dash, em-dash
        if sep in cell_text:
            parts = cell_text.split(sep, 1)
            if len(parts) == 2:
                value = parts[1].strip()
                if value and len(value) >= 1:
                    return value

    # Newline-separated inline value
    if "\n" in cell_text or "\r" in cell_text:
        lines = [ln.strip() for ln in re.split(r"[\r\n]+", cell_text) if ln.strip()]
        if len(lines) >= 2 and label_core in lines[0].lower():
            candidate = lines[1].strip()
            if candidate and len(candidate) >= 1:
                return candidate

    # Simple "LABEL value" with whitespace separator
    m = re.match(
        rf"^{re.escape(label_core)}\s+(.+)$",
        lower_cell,
        flags=re.IGNORECASE,
    )
    if m:
        candidate = m.group(1).strip()
        if candidate and len(candidate) >= 1:
            return candidate

    return ""


# ---------------------------------------------------------------------------
# Main proximity resolver
# ---------------------------------------------------------------------------

def resolve_value(
    grid: CellGrid,
    label_pos: Tuple[int, int],
    direction_rule: Any = "right_then_down",
) -> str:
    """
    Scan cells adjacent to *label_pos* and return the first non-empty string.

    Parameters
    ----------
    grid          : CellGrid wrapping the sheet
    label_pos     : (row, col) of the label cell (0-based)
    direction_rule: DirectionRule value or list thereof.
                    Supported rules:
                      "right"           – scan right across the same row
                      "down"            – scan down the same column
                      "down_if_int"     – scan down but only accept integers
                      "right_then_down" (default)
                      "down_then_right"

    Returns
    -------
    First non-empty value found, or "" if nothing is found.
    """
    row, col = label_pos

    # Normalise to a list of rule strings
    if isinstance(direction_rule, list):
        rules: List[str] = [
            r.value if hasattr(r, "value") else str(r) for r in direction_rule
        ]
    elif direction_rule in ("right_then_down", "right then down"):
        rules = ["right", "down"]
    elif direction_rule in ("down_then_right", "down then right"):
        rules = ["down", "right"]
    else:
        rule_str = direction_rule.value if hasattr(direction_rule, "value") else str(direction_rule)
        rules = [rule_str]

    for rule in rules:

        if rule == "right":
            for c in range(col + 1, grid.ncols):
                raw = grid.get(row, c)
                value = str(raw).strip() if raw is not None else ""
                if value and value not in (":", "-", "|", "_"):
                    return raw

        elif rule == "down":
            for r in range(row + 1, grid.nrows):
                raw = grid.get(r, col)
                value = str(raw).strip() if raw is not None else ""
                if value and value not in (":", "-", "|", "_"):
                    return raw

        elif rule == "down_if_int":
            for r in range(row + 1, grid.nrows):
                value = grid.get(r, col)
                if value:
                    if is_int(value):
                        return value
                    break  # non-integer — stop looking

    return ""


# ---------------------------------------------------------------------------
# PO / Report number handler
# ---------------------------------------------------------------------------

def resolve_po_or_report_number(
    grid: CellGrid,
    label_pos: Tuple[int, int],
    field_name: str = "audit_report",
) -> str:
    """
    Extract and validate a PO or Report number from cells to the right of the label.

    field_name controls which pattern is accepted:
      "po_no"        → only PO pattern   (P0726-482920-005)
      "report_no"    → only Report pattern (EU26-02CIPL-001)
    """
    row, col = label_pos
    
    # Shared regex patterns for internal searching
    REPORT_PAT = r"[A-Z]{1,2}\s*\d{0,2}\s*[-\s]?\s*\d{2}\s*[-/]?\s*[A-Z0-9]{2,}\s*[-/]?\s*\d+"
    PO_PAT     = r"P\d{0,4}[-\s]?\d{6}-\d{3}(?:-\d+)*"
    
    # 1. Search Right (including the label cell itself for inline values)
    # 2. Search Down (BABL formats often put the value below the label)
    search_coords = []
    # Right: (row, col) to (row, col+9)
    for c in range(col, min(col + 10, grid.ncols)):
        search_coords.append((row, c))
    # Down: (row+1, col) to (row+5, col)
    for r in range(row + 1, min(row + 6, grid.nrows)):
        search_coords.append((r, col))

    for r_idx, c_idx in search_coords:
        raw_val = grid.get(r_idx, c_idx)
        if not raw_val:
            continue
        
        value = str(raw_val).strip()

        # Strictly check for the requested pattern. 
        # If po_no is looking at a Report No label, this will correctly fail and return ""
        if field_name == "report_no":
            match_r = re.search(REPORT_PAT, value, re.IGNORECASE)
            if match_r:
                found = match_r.group(0).rstrip(".,;:")
                logging.debug(f"PO_OR_REPORT: Found Report No '{found}' at ({r_idx}, {c_idx})")
                return found
        
        if field_name == "po_no":
            match_p = re.search(PO_PAT, value, re.IGNORECASE)
            if match_p:
                found = match_p.group(0)
                logging.debug(f"PO_OR_REPORT: Found PO No '{found}' at ({r_idx}, {c_idx})")
                return found

    logging.debug(f"PO_OR_REPORT: nothing found in proximity for '{field_name}'")
    return ""


# ---------------------------------------------------------------------------
# PO W/H special handler  (date may be split across 3 cells: MM | DD | YYYY)
# ---------------------------------------------------------------------------

def resolve_po_wh_value(grid: CellGrid, label_pos: Tuple[int, int]) -> str:
    """
    Extract a date value that may be split across up to 3 adjacent cells.

    Handles two formats:
      - Single cell:   "12/31/2024"
      - Split cells:   "12"  |  "31"  |  "2024"  → "12/31/2024"
    """
    row, col = label_pos

    # Find the first non-empty cell to the right
    first_col = None
    first_val = ""

    for c in range(col + 1, min(col + 10, grid.ncols)):
        val = grid.get(row, c)
        if val:
            first_col = c
            first_val = val.strip()
            break

    if not first_val:
        return ""

    # Format 1: full date already in one cell
    if is_date_format(first_val):
        return first_val

    # Format 2: date split across three cells (MM | DD | YYYY)
    if is_valid_month_or_day(first_val):
        mm = first_val

        second_col = None
        second_val = ""
        for c in range(first_col + 1, min(first_col + 5, grid.ncols)):
            val = grid.get(row, c)
            if val:
                second_col = c
                second_val = val.strip()
                break

        if not second_val or not is_valid_month_or_day(second_val):
            return mm

        dd = second_val

        third_val = ""
        for c in range(second_col + 1, min(second_col + 5, grid.ncols)):
            val = grid.get(row, c)
            if val:
                third_val = val.strip()
                break

        if not third_val or not is_valid_year(third_val):
            return f"{mm}/{dd}"

        return f"{mm}/{dd}/{third_val}"

    # Format 3: non-date value — return as-is
    return first_val