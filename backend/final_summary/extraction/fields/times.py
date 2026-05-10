"""
----------------------------
Extracts all time fields from an audit report sheet and derives duration totals.

Fields handled:
  - factory_in_time     (time factory staff arrived)
  - factory_out_time    (time factory staff left)
  - factory_total_hours (derived: factory_out − factory_in)
  - audit_start_time    (time audit began)
  - audit_end_time      (time audit ended)
  - audit_total_hours   (derived: audit_end − audit_start)

All raw values are normalised to "HH:MM" (24-hour) by to_hhmm().
Durations are computed by duration_hhmm() and also returned as "HH:MM".

To add a new label variant → add to the relevant SYNONYMS list.
To change time format      → edit to_hhmm() in extraction/core/normalise.py.
"""

from pathlib import Path
from typing import Optional

from final_summary.extraction.core import (
    CellGrid,
    DirectionRule,
    to_hhmm,
    duration_hhmm,
    resolve_value,
)

# ---------------------------------------------------------------------------
# Per-field synonym lists
# ---------------------------------------------------------------------------

FACTORY_IN_SYNONYMS: list[str] = [
    "factory in time",
    "factory in",
    "in time",
    "factory intime",
]

FACTORY_OUT_SYNONYMS: list[str] = [
    "factory out time",
    "factory out",
    "out time",
    "factory outtime",
]

AUDIT_START_SYNONYMS: list[str] = [
    "audit start time",
    "start time",
    "audit start",
    "inspection start",
    "inspection start time",
]

AUDIT_END_SYNONYMS: list[str] = [
    "audit end time",
    "end time",
    "audit end",
    "inspection end",
    "inspection end time",
]

_DIRECTION = DirectionRule.RIGHT


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _extract_time(grid: CellGrid, synonyms: list[str]) -> str:
    """
    Find a time label and return the normalised HH:MM value to its right.
    Returns "" if nothing found or if the raw value is not a valid time.
    """
    for row, col, _ in grid.find_label_positions(synonyms):
        raw = resolve_value(grid, (row, col), _DIRECTION)
        if raw:
            normalised = to_hhmm(raw)
            if normalised:
                return normalised
    return ""


# ---------------------------------------------------------------------------
# Unified extract() — returns all time fields + derived durations
# ---------------------------------------------------------------------------

def extract(
    grid: CellGrid,
    path: Optional[Path] = None,
) -> dict[str, str]:
    """
    Extract all 4 raw time fields and derive the 2 duration totals.

    Parameters
    ----------
    grid : CellGrid for the sheet being processed
    path : unused

    Returns
    -------
    dict with keys:
      factory_in_time, factory_out_time, factory_total_hours,
      audit_start_time, audit_end_time, audit_total_hours
    All values are "HH:MM" strings or "" if not found / not computable.
    """
    factory_in  = _extract_time(grid, FACTORY_IN_SYNONYMS)
    factory_out = _extract_time(grid, FACTORY_OUT_SYNONYMS)
    audit_start = _extract_time(grid, AUDIT_START_SYNONYMS)
    audit_end   = _extract_time(grid, AUDIT_END_SYNONYMS)

    return {
        "factory_in_time":     factory_in,
        "factory_out_time":    factory_out,
        "factory_total_hours": duration_hhmm(factory_in, factory_out),
        "audit_start_time":    audit_start,
        "audit_end_time":      audit_end,
        "audit_total_hours":   duration_hhmm(audit_start, audit_end),
    }