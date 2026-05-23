"""
------------------------------------
Validates and re-formats date and time fields on an AuditRecord.

Applied after extraction, before blocking validation.
All functions are pure — they mutate the record in place and return it.

Date fields  → normalised to MM/DD/YYYY
Time fields  → normalised to HH:MM AM/PM (12-hour display format)

00:00 times (placeholder / missing) → set to ""
Datetime strings in time fields     → set to ""
"""

import logging
import re
from datetime import datetime
from typing import Any

from final_summary.extraction.core import to_display_date, to_hhmm

# Fields that hold a date (normalised to MM/DD/YYYY)
_DATE_FIELDS = (
    "date_of_issue",
    "exf",
    "po_edt",
    "po_wh",
    "plan_edt",
    "plan_wh",
)

# Fields that hold a time (normalised to HH:MM AM/PM)
_TIME_FIELDS = (
    "factory_in_time",
    "factory_out_time",
    "audit_start_time",
    "audit_end_time",
)


def _to_display_time(value: str) -> str:
    """
    Convert "HH:MM" (24-hour) to "HH:MM AM/PM" (12-hour display format).
    Returns "" for 00:00 placeholder or unparseable values.
    """
    hhmm = to_hhmm(value)
    if not hhmm:
        return ""

    # Treat 00:00 as a missing placeholder (e.g. PQC "OUT TIME :00.00 PM")
    if hhmm == "00:00":
        logging.debug(f"date_time: 00:00 placeholder → set to ''")
        return ""

    try:
        return datetime.strptime(hhmm, "%H:%M").strftime("%I:%M %p")
    except ValueError:
        return ""


def apply_date_time_refinement(record: Any) -> Any:
    """
    Normalise all date and time fields on *record* in place.

    Date fields  → MM/DD/YYYY
    Time fields  → HH:MM AM/PM  (or "" for invalid / placeholder)

    Returns the mutated record.
    """
    for field_name in _DATE_FIELDS:
        raw = getattr(record, field_name, None)
        if not raw:
            continue
        refined = to_display_date(raw)
        if refined != raw:
            logging.info(f"  date refined [{field_name}]: '{raw}' → '{refined}'")
        setattr(record, field_name, refined)

    for field_name in _TIME_FIELDS:
        raw = getattr(record, field_name, None)
        if not raw:
            continue
        refined = _to_display_time(raw)
        if refined != raw:
            logging.info(f"  time refined [{field_name}]: '{raw}' → '{refined}'")
        setattr(record, field_name, refined)

    return record