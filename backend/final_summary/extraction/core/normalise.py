"""
extraction/core/normalise.py
-----------------------------
Single source of truth for all value normalisation in the extraction pipeline.

Consolidates logic previously scattered across:
  - helpers/extraction/post_processor.py  (_parse_hhmm, _calc_defect_percentage)
  - helpers/validator.py                  (_format_date, _strip_time_from_date, _format_time)
  - db/db_manager.py                      (_to_iso_date)

Rules
-----
- All date normalisation targets MM/DD/YYYY for display/validation.
- All date storage targets YYYY-MM-DD (ISO) for DB range queries.
- All time normalisation targets HH:MM (24-hour) internally.
- All public functions are pure (no side-effects) and return "" on failure —
  never raise, never return None, never block a record.

Adding a new normalisation
--------------------------
1. Write a pure function here.
2. Import it in the field file that needs it (e.g. extraction/fields/dates.py).
3. Never duplicate normalisation logic in a field file — always call here.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Any


# =============================================================================
# DATE NORMALISATION
# =============================================================================

# All formats the extraction pipeline may encounter.
# Order matters: more specific / more common formats first.
_DATE_FORMATS = [
    "%m/%d/%Y",   # 01/05/2026  ← validator output / display standard
    "%Y-%m-%d",   # 2026-01-05  ← ISO / DB storage
    "%Y/%m/%d",   # 2026/01/05
    "%d-%b-%y",   # 05-Jan-26
    "%d-%b-%Y",   # 05-Jan-2026
    "%m-%d-%Y",   # 01-05-2026
    "%d/%m/%Y",   # 05/01/2026  ← last (ambiguous with MM/DD; only tried if others fail)
    "%B %d, %Y",  # January 5, 2026
    "%b %d, %Y",  # Jan 5, 2026
    "%Y/%d/%m",
    "%Y-%d-%m",
    "%d-%Y-%m",
    "%m/%Y/%d",
    "%d/%Y/%m",
]

# Regex: detects strings that contain both a date AND a time component.
_DATETIME_RE = re.compile(
    r"^(\d{4}[-/]\d{1,2}[-/]\d{1,2}|"   # YYYY-MM-DD ...
    r"\d{1,2}[-/]\d{1,2}[-/]\d{4})"      # DD/MM/YYYY ...
    r"[\sT]"                              # separator (space or T)
    r"\d{1,2}[:.]\d{2}"                  # time component
)


def strip_time_from_date(value: str) -> str:
    """
    If *value* contains both a date and a time component, strip the time part.

    "2026-01-01 10:00:00" → "2026-01-01"
    "01/15/2026 09:30"    → "01/15/2026"
    "2026-01-15"          → "2026-01-15"  (unchanged)
    """
    if not value:
        return value
    s = value.strip()
    # Strip time portion if detected
    if len(s) > 10 and (s[10] in (" ", "T")):
        return s[:10]
    if _DATETIME_RE.match(s):
        stripped = re.split(r"[\sT]", s, maxsplit=1)[0]
        logging.debug(f"normalise: stripped time from date: '{s}' → '{stripped}'")
        return stripped
    return s


def to_display_date(value: str) -> str:
    """
    Normalise *value* to MM/DD/YYYY for display and validation output.
    Strips any time component first.
    Returns the original string unchanged if no format matches.

    Examples
    --------
    "2026-01-05"            → "01/05/2026"
    "05-Jan-26"             → "01/05/2026"
    "2026-01-05 00:00:00"   → "01/05/2026"
    "01/05/2026"            → "01/05/2026"  (already correct)
    """
    if not isinstance(value, str) or not value.strip():
        return value or ""

    s = strip_time_from_date(value.strip())

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%m/%d/%Y")
        except ValueError:
            continue

    logging.warning(f"normalise.to_display_date: unrecognised format '{value}'")
    return value


def to_iso_date(value: str) -> Optional[str]:
    """
    Normalise *value* to YYYY-MM-DD for database storage.
    Strips any time component first.
    Returns None if blank or completely unparseable.

    Examples
    --------
    "01/05/2026"  → "2026-01-05"
    "05-Jan-26"   → "2026-01-05"
    ""            → None
    """
    if not value or not str(value).strip():
        return None

    s = strip_time_from_date(str(value).strip())

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Store as-is if nothing matches — never block a DB insert on a date
    logging.warning(f"normalise.to_iso_date: unrecognised format '{value}', storing as-is")
    return s


def is_valid_display_date(value: str) -> bool:
    """True if *value* is already in MM/DD/YYYY format."""
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.strptime(value.strip(), "%m/%d/%Y")
        return True
    except ValueError:
        return False


# =============================================================================
# TIME NORMALISATION
# =============================================================================

def to_hhmm(value: str) -> str:
    """
    Convert a loose time string to "HH:MM" (24-hour, no AM/PM suffix).
    This is the internal pipeline format used in AuditRecord time fields.

    Returns "" if the value is not a valid or parseable time — never stores
    garbage in time fields.

    Examples
    --------
    "9:30"          → "09:30"
    "09:30 AM"      → "09:30"
    "14:00"         → "14:00"
    "9.30AM"        → "09:30"
    "930"           → "09:30"
    "2026-01-01..." → ""   (date strings are rejected)
    """
    if not isinstance(value, str) or not value.strip():
        return ""

    s = value.strip()

    # Reject strings that look like full dates or datetimes
    if re.match(r"\d{4}[-/]\d{2}[-/]\d{2}", s):
        logging.debug(f"normalise.to_hhmm: rejected datetime string '{s}'")
        return ""

    match = re.search(r"(\d{1,2})[:.]?(\d{2})?\s*([APap][Mm])?", s)
    if not match:
        logging.debug(f"normalise.to_hhmm: not parseable '{s}'")
        return ""

    hour_str, minute_str, am_pm = match.groups()
    hour   = int(hour_str)
    minute = int(minute_str) if minute_str else 0

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        logging.debug(f"normalise.to_hhmm: out of range '{s}'")
        return ""

    if am_pm:
        am_pm_lower = am_pm.lower()
        if am_pm_lower.startswith("p") and hour != 12:
            hour += 12
        elif am_pm_lower.startswith("a") and hour == 12:
            hour = 0

    try:
        return datetime.strptime(f"{hour}:{minute}", "%H:%M").strftime("%H:%M")
    except ValueError:
        return ""


def to_display_time(value: str) -> str:
    """
    Convert a loose time string to "HH:MM AM/PM" (12-hour with suffix).
    Used for display / export output.

    Returns "" on failure — same policy as to_hhmm().

    Examples
    --------
    "09:30"   → "09:30 AM"
    "14:00"   → "02:00 PM"
    "9.30AM"  → "09:30 AM"
    """
    hhmm = to_hhmm(value)
    if not hhmm:
        return ""
    try:
        return datetime.strptime(hhmm, "%H:%M").strftime("%I:%M %p")
    except ValueError:
        return ""


def duration_hhmm(start: str, end: str) -> str:
    """
    Return the elapsed duration between two "HH:MM" strings as "HH:MM".
    Handles overnight spans (end < start) by adding 24 hours.
    Returns "" on any parse error.

    Examples
    --------
    ("08:00", "17:30") → "09:30"
    ("22:00", "06:00") → "08:00"  (overnight)
    """
    if not start or not end:
        return ""
    try:
        t0 = datetime.strptime(start, "%H:%M")
        t1 = datetime.strptime(end, "%H:%M")
        delta = t1 - t0
        if delta.total_seconds() < 0:
            delta += timedelta(days=1)
        total_minutes = int(delta.total_seconds() // 60)
        hours   = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours:02d}:{minutes:02d}"
    except ValueError as exc:
        logging.debug(f"normalise.duration_hhmm: failed ('{start}' → '{end}'): {exc}")
        return ""


# =============================================================================
# NUMERIC NORMALISATION
# =============================================================================

def to_int(value: Any) -> Optional[int]:
    """
    Convert *value* to int.  Returns None on failure (never raises).

    Handles: "1,200", "1200.0", 1200, "1200 PCS" (takes first number found).
    """
    if value is None or value == "":
        return None
    s = str(value).strip()
    if not s or s in ("-", "N/A", "n/a"):
        return None
    # Strip commas and take everything up to non-numeric
    cleaned = re.sub(r"[^\d\-\.]", "", s.replace(",", ""))
    try:
        return int(float(cleaned))
    except (ValueError, TypeError):
        return None


def to_float(value: Any) -> Optional[float]:
    """
    Convert *value* to float.  Returns None on failure (never raises).
    """
    if value is None or value == "":
        return None
    s = str(value).strip().replace(",", "")
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def to_percentage(value: str) -> str:
    """
    Clean a percentage string: "3.71%" → "3.71%", "3.714" → "3.714%".
    Returns "" on failure.
    """
    if not value:
        return ""
    s = str(value).strip()
    # Strip existing % and reformat to 2dp
    numeric = s.rstrip("%").strip()
    try:
        pct = round(float(numeric), 2)
        return f"{pct}%"
    except (ValueError, TypeError):
        return ""


def extract_first_number(value: str) -> str:
    """
    Extract only the FIRST number from *value* and return it as a plain string.
    Commas are removed.

    "1,200 PCS" → "1200"
    "PO: 3500"  → "3500"
    ""           → ""
    """
    if not value:
        return ""
    match = re.search(r"[\d,]+\.?\d*", value.strip())
    if not match:
        return ""
    return match.group().replace(",", "")


def calc_defect_percentage(defect_qty: str, audit_qty: str) -> str:
    """
    Calculate defect percentage as "N.NN%" from raw string quantities.
    Returns "" if either quantity is missing or invalid.

    Examples
    --------
    ("9", "1636") → "0.55%"
    ("",  "1636") → ""
    """
    try:
        if not defect_qty or not audit_qty:
            return ""
        d = int(str(defect_qty).strip())
        a = int(str(audit_qty).strip())
        if a == 0:
            return ""
        return f"{round(d / a * 100, 2)}%"
    except (ValueError, TypeError):
        return ""


# ---------------------------------------------------------------------------
# Type alias for Any — avoids importing from typing in every caller
# ---------------------------------------------------------------------------
from typing import Any  # noqa: E402  (kept at bottom to avoid cluttering top)