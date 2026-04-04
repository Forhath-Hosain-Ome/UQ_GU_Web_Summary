"""
proximity.py
------------
Functions that locate a field's VALUE relative to its LABEL cell.

Core function : resolve_value()
  Given a label position and a direction rule, scans adjacent cells until
  a non-empty string is found.

Special handlers
  resolve_po_wh_value()       – PO W/H date may span 3 cells (MM | DD | YYYY).
  resolve_po_or_report_number() – validates PO vs Report number patterns.
"""

import logging
import re
from typing import Any, List, Tuple

from ..core.cell_grid import CellGrid


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
    Valid: EU26-02CIPL-001 or EU26-02CIPL-001.
    Strips trailing punctuation before matching.
    """
    if not value:
        return False
    # Strip trailing punctuation (period, comma, etc.)
    cleaned = value.strip().rstrip('.,;:')
    return bool(re.match(r"^[A-Z]{2}\d{2}-\d{2}[A-Z0-9]+-\d+$", cleaned))


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
                if value and len(value) > 2:
                    return value

    # Newline-separated inline value
    if "\n" in cell_text or "\r" in cell_text:
        lines = [ln.strip() for ln in re.split(r"[\r\n]+", cell_text) if ln.strip()]
        if len(lines) >= 2 and label_core in lines[0].lower():
            candidate = lines[1].strip()
            if candidate and len(candidate) > 2:
                return candidate

    # Simple "LABEL value" with whitespace separator
    m = re.match(rf"^{re.escape(label_core)}\s+(.+)$", lower_cell, flags=re.IGNORECASE)
    if m:
        candidate = m.group(1).strip()
        if candidate and len(candidate) > 2:
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
                value = grid.get(row, c)
                if value:
                    return value

        elif rule == "down":
            for r in range(row + 1, grid.nrows):
                value = grid.get(r, col)
                if value:
                    return value

        elif rule == "down_if_int":
            for r in range(row + 1, grid.nrows):
                value = grid.get(r, col)
                if value:
                    if is_int(value):
                        return value
                    break  # non-integer → stop looking

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
      "po_no"       → only PO pattern   (P0726-482920-005)
      "report_no"   → only Report pattern (EU26-02CIPL-001)
      "audit_report"→ accept either; fall back to raw value if no pattern matches
    """
    row, col = label_pos
    logging.debug(f"PO_OR_REPORT: resolving '{field_name}' from ({row}, {col})")

    for c in range(col + 1, min(col + 10, grid.ncols)):
        value = grid.get(row, c)
        if not value:
            continue

        value = value.strip()

        if field_name == "po_no":
            if is_valid_po_no(value):
                logging.debug(f"PO_OR_REPORT: PO match → {value}")
                return value

        elif field_name == "report_no":
            # Strip trailing punctuation for validation and return
            cleaned = value.rstrip('.,;:')
            if is_valid_report_no(value):
                logging.debug(f"PO_OR_REPORT: Report match → {cleaned}")
                return cleaned

        elif field_name == "audit_report":
            if is_valid_po_no(value) or is_valid_report_no(value):
                # For report_no matches, strip trailing punctuation
                if is_valid_report_no(value):
                    cleaned = value.rstrip('.,;:')
                    logging.debug(f"PO_OR_REPORT: pattern match → {cleaned}")
                    return cleaned
                logging.debug(f"PO_OR_REPORT: pattern match → {value}")
                return value
            # Fallback: return raw value for audit_report even without a pattern match
            logging.debug(f"PO_OR_REPORT: no pattern, returning raw → {value}")
            return value

    logging.debug(f"PO_OR_REPORT: nothing found to the right for '{field_name}'")
    return ""


# ---------------------------------------------------------------------------
# PO W/H special handler  (date may be split across 3 cells: MM | DD | YYYY)
# ---------------------------------------------------------------------------

def resolve_po_wh_value(grid: CellGrid, label_pos: Tuple[int, int]) -> str:
    """
    Extract the PO W/H (warehouse / ship date) value.

    Handles two formats:
      - Single cell:   "12/31/2024"
      - Split cells:   "12"  |  "31"  |  "2024"  → "12/31/2024"
    """
    row, col = label_pos
    logging.debug(f"PO_WH: resolving from label at ({row}, {col})")

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
        logging.debug("PO_WH: no value found to the right")
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

        result = f"{mm}/{dd}/{third_val}"
        logging.debug(f"PO_WH: reconstructed split date → {result}")
        return result

    # Format 3: non-date value — return as-is
    return first_val
