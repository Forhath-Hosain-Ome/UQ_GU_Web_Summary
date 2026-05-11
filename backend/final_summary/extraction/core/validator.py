"""
validator.py
------------
Multi-layer validation and refinement of AuditRecord objects.

Layers (applied in order)
--------------------------
Layer 1 – DATE STRIPPING
    Date fields must contain a date only.  If the raw value carries a time
    component (e.g. "2026-01-01 10:00:00") the time part is silently stripped
    and only the date is kept.

Layer 2 – DATE FORMATTING
    Accepted dates are normalised to MM/DD/YYYY.

Layer 3 – TIME VALIDATION
    Time fields (factory in/out, audit start/end) must be parseable as
    HH:MM.  Unparseable values → set to "" (null) rather than storing garbage.

Layer 4 – PATTERN VALIDATION
    Report numbers and PO numbers share the same Excel label in some sheets.
    Each field is validated against its expected regex:
      Report No : e.g.  JP26-02BABL-001   ->  [A-Z]{2}\d{2}-\d{2}[A-Z0-9]+-\d+
      PO No     : e.g.  P0426-482649-004  →  P\d{4}-\d{6}-\d{3}(-\d+)*

Layer 5 – BUSINESS RULES
    Mandatory field checks, numeric range validation, etc.

Adding a new validation rule
-----------------------------
1. Write a bool function  f(value) -> bool  (True = valid).
2. Add a tuple  (f, "human-readable error message")  to VALIDATION_RULES[FieldName.XXX].
"""

import logging
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Tuple

from final_summary.models import AuditRecord
from final_summary.models import FieldName

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Layer 1 + 2 : Date stripping and formatting
# ---------------------------------------------------------------------------

_DATE_FORMATS = [
    "%m/%d/%Y",  # target format – skip re-formatting if already correct
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%Y-%m-%d",
    "%m-%d-%Y",
    "%d-%m-%Y",
    "%m.%d.%Y",
    "%d.%m.%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%Y/%d/%m",
    "%Y-%d-%m",
    "%d-%Y-%m",
    "%m/%Y/%d",
    "%d/%Y/%m",
]

# Regex that detects a datetime string with both a date and a time component.
# E.g. "2026-01-01 10:00:00" or "2026-01-01T10:00"
_DATETIME_RE = re.compile(
    r"^(\d{4}[-/]\d{1,2}[-/]\d{1,2}|"   # YYYY-MM-DD …
    r"\d{1,2}[-/]\d{1,2}[-/]\d{4})"       # DD/MM/YYYY …
    r"[\sT]"                               # separator
    r"\d{1,2}[:.]\d{2}"                   # time component
)


def _strip_time_from_date(value: str) -> str:
    """
    If *value* contains both a date and a time component, strip the time.

    "2026-01-01 10:00:00" → "2026-01-01"
    "01/15/2026 09:30"    → "01/15/2026"
    "2026-01-15"          → "2026-01-15"   (unchanged)
    """
    if not value:
        return value
    s = value.strip()
    if _DATETIME_RE.match(s):
        # Keep everything before the first space or T
        stripped = re.split(r"[\sT]", s, maxsplit=1)[0]
        logger.info(f"  date stripped of time component: '{s}' → '{stripped}'")
        return stripped
    return s


def _format_date(date_string: str) -> str:
    """
    Strip any time component, then normalise to MM/DD/YYYY.
    Returns the original string unchanged if no format matches.
    """
    if not isinstance(date_string, str) or not date_string.strip():
        return date_string or ""

    # Layer 1: strip time component
    date_string = _strip_time_from_date(date_string.strip())

    # Layer 2: normalise to MM/DD/YYYY
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(date_string, fmt).strftime("%m/%d/%Y")
        except ValueError:
            continue

    logger.warning(f"Date format not recognised: '{date_string}'")
    return date_string


# ---------------------------------------------------------------------------
# Layer 3 : Time validation
# ---------------------------------------------------------------------------

def _format_time(time_string: str) -> str:
    """
    Convert a loose time string to "HH:MM AM/PM" (12-hour with suffix).
    Returns "" (empty / null) if the value is not a valid time — this
    prevents storing garbage in the time fields.

    Examples
    --------
    "9:30"          → "09:30 AM"
    "14:00"         → "02:00 PM"
    "9.30AM"        → "09:30 AM"
    "2026-01-01..." → ""   (datetime strings are invalid as times)
    """
    if not isinstance(time_string, str) or not time_string.strip():
        return ""

    s = time_string.strip()

    # If the time string contains a date (common in Excel), strip it and take the time part
    if " " in s and re.match(r"\d{4}[-/]\d{2}[-/]\d{2}", s):
        s = s.split(" ", 1)[1]
    elif "T" in s and re.match(r"\d{4}[-/]\d{2}[-/]\d{2}", s):
        s = s.split("T", 1)[1]
    elif re.match(r"^\d{4}[-/]\d{2}[-/]\d{2}$", s):
        # It's ONLY a date with no time component
        return ""

    match = re.search(r"(\d{1,2})[:.]?(\d{2})?\s*([APap][Mm])?", s)
    if not match:
        logger.info(f"  time field '{s}' not parseable → set to null")
        return ""

    hour_str, minute_str, am_pm = match.groups()
    hour   = int(hour_str)
    minute = int(minute_str) if minute_str else 0

    if not (0 <= hour <= 23 and 0 <= minute <= 59): # type: ignore
        logger.info(
            f"  time field '{s}' out of range → set to null"
        )
        return ""

    if am_pm:
        am_pm_lower = am_pm.lower()
        if am_pm_lower.startswith("p") and hour != 12:
            hour += 12
        elif am_pm_lower.startswith("a") and hour == 12:
            hour = 0

    try:
        return datetime.strptime(f"{hour}:{minute}", "%H:%M").strftime("%I:%M %p")
    except ValueError:
        logger.info(f"  time field '{s}' failed strptime → set to null")
        return ""


# ---------------------------------------------------------------------------
# Layer 4 : Pattern validation helpers
# ---------------------------------------------------------------------------

_REPORT_NO_RE = re.compile(r"^[A-Z]{2}\d{2}-\d{2}[A-Z0-9]+-\d+$")
_PO_NO_RE     = re.compile(r"^P\d{4}-\d{6}-\d{3}(-\d+)*$")


def is_valid_report_no(value: str) -> bool:
    """True if value matches the Report Number pattern (e.g. JP26-02BABL-001)."""
    if not value:
        return False
    return bool(_REPORT_NO_RE.match(value.strip().rstrip(".,;:")))


def is_valid_po_no(value: str) -> bool:
    """True if value matches the PO Number pattern (e.g. P0426-482649-004)."""
    if not value:
        return False
    return bool(_PO_NO_RE.match(value.strip()))


# ---------------------------------------------------------------------------
# Layer 5 : Business rule validators
# ---------------------------------------------------------------------------

def is_not_empty(value: Any) -> bool:
    return bool(str(value).strip())


def is_numeric(value: Any) -> bool:
    if isinstance(value, (int, float)):
        return True
    return str(value).strip().replace(".", "", 1).isdigit()


def is_date_mmddyyyy(value: str) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.strptime(value.strip(), "%m/%d/%Y")
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Validation rules per field
# ---------------------------------------------------------------------------

ValidationRule = Callable[[Any], bool]
RuleList       = List[Tuple[ValidationRule, str]]

VALIDATION_RULES: Dict[str, RuleList] = {
    FieldName.FACTORY: [
        (is_not_empty, "Factory name should not be empty."),
    ],
    FieldName.DATE_OF_ISSUE: [
        (is_not_empty,    "Date of Issue should not be empty."),
        (is_date_mmddyyyy, "Date of Issue must be in MM/DD/YYYY format."),
    ],
    FieldName.EXF: [
        (is_date_mmddyyyy, "EXF date must be in MM/DD/YYYY format."),
    ],
    FieldName.PO_EDT: [
        (is_date_mmddyyyy, "PO EDT must be in MM/DD/YYYY format."),
    ],
    FieldName.PO_WH: [
        (is_date_mmddyyyy, "PO WH date must be in MM/DD/YYYY format."),
    ],
    FieldName.PLAN_EDT: [
        (is_date_mmddyyyy, "Plan EDT must be in MM/DD/YYYY format."),
    ],
    FieldName.PLAN_WH: [
        (is_date_mmddyyyy, "Plan WH must be in MM/DD/YYYY format."),
    ],
    FieldName.SHIP_QTY: [
        (is_numeric, "Ship Quantity should be a number."),
    ],
    FieldName.AUDIT_QTY: [
        (is_numeric, "Audit Quantity should be a number."),
    ],
    FieldName.REPORT_NO: [
        (
            lambda v: not v or is_valid_report_no(v),
            "Report No does not match expected pattern (e.g. JP26-02BABL-001).",
        ),
    ],
    FieldName.PO_NO: [
        (
            lambda v: not v or is_valid_po_no(v),
            "PO No does not match expected pattern (e.g. P0426-482649-004).",
        ),
    ],
}


# ---------------------------------------------------------------------------
# Refinement map  (field → formatter)
# ---------------------------------------------------------------------------

_REFINEMENT_RULES: Dict[str, Callable[[str], str]] = {
    # Time fields → "HH:MM AM/PM" or "" on failure
    "factory_in_time":  _format_time,
    "factory_out_time": _format_time,
    "audit_start_time": _format_time,
    "audit_end_time":   _format_time,
    # Date fields → "MM/DD/YYYY" (time component stripped first)
    "date_of_issue":    _format_date,
    "exf":              _format_date,
    "po_wh":            _format_date,
    "po_edt":           _format_date,
    "plan_edt":         _format_date,
    "plan_wh":          _format_date,
}


def apply_refinement_rules(record: AuditRecord) -> AuditRecord:
    """Apply date/time formatting to all relevant fields in *record*."""
    for field_name, formatter in _REFINEMENT_RULES.items():
        raw = getattr(record, field_name, None)
        if not raw:
            continue
        refined = formatter(raw)
        if refined != raw: # type: ignore
            logger.info(f"  refined [{field_name}]: '{raw}' → '{refined}'")
        setattr(record, field_name, refined)
    return record


# ---------------------------------------------------------------------------
# Blocking validation  (records that FAIL these are never inserted into DB)
# ---------------------------------------------------------------------------

# Fields that MUST be present for a record to be usable.
# If any of these are missing the record goes to the error JSON instead.
_BLOCKING_REQUIRED_FIELDS: List[Tuple[str, str]] = [
    ("factory",         "Factory name is missing"),
    ("date_of_issue",   "Date of Issue is missing"),
    ("inspection_type", "Inspection Type is missing"),
    ("report_no",       "Report Number is missing"),
    ("ship_qty",        "Shipping Quantity is missing"),
    ("audit_qty",       "Audit Quantity is missing"),
]


def validate_blocking(record: AuditRecord) -> AuditRecord:
    """
    Run blocking validations.  Any failure appends to record.blocking_errors
    and the record will be written to the error JSON and skipped by the DB.

    Checks:
      1. Required fields must not be empty.
      2. Sum of extracted defect major counts must equal record.defect_qty.
         A mismatch means the defect table was not read correctly.
    """
    errors: List[str] = []

    # Check 1: required fields
    for field_key, msg in _BLOCKING_REQUIRED_FIELDS:
        val = getattr(record, field_key, None)
        if not val or not str(val).strip():
            errors.append(f"REQUIRED_FIELD | {field_key} | {msg}")
            logger.warning(f"[{record.file_name}] BLOCKING: {msg}")

    # Check 2: defect count integrity
    if record.defect_qty and record.defect_rows:
        try:
            header_qty = int(str(record.defect_qty).strip())
            extracted_sum = sum(
                int(d.get("major", 0) or 0) + int(d.get("minor", 0) or 0)
                for d in record.defect_rows
                if isinstance(d, dict)
            )
            if header_qty != extracted_sum:
                msg = (
                    f"DEFECT_MISMATCH | "
                    f"header says {header_qty} total defects but "
                    f"extracted defect rows sum to {extracted_sum}"
                )
                errors.append(msg)
                logger.warning(f"[{record.file_name}] BLOCKING: {msg}")
        except (ValueError, TypeError):
            pass   # can't compare — don't block on this

    record.blocking_errors.extend(errors)
    return record


def validate_blocking_all(records: List[AuditRecord]) -> List[AuditRecord]:
    """Apply validate_blocking to every record and return the list."""
    for r in records:
        validate_blocking(r)
    blocked = sum(1 for r in records if r.blocking_errors)
    logger.info(f"Blocking validation: {blocked}/{len(records)} records blocked")
    return records


# ---------------------------------------------------------------------------
# Per-record validation
# ---------------------------------------------------------------------------

def validate_record(record: AuditRecord) -> AuditRecord:
    """
    1. Apply refinement rules (date stripping, date/time formatting).
    2. Run all VALIDATION_RULES and collect error messages.
    Returns the mutated record.
    """
    record = apply_refinement_rules(record)

    errors: List[str] = []

    for field_name, rules in VALIDATION_RULES.items():
        value = getattr(record, field_name, None)
        if not value:
            continue  # only validate fields that were actually extracted
        for rule_fn, error_msg in rules:
            if not rule_fn(value):
                full_msg = f"'{field_name}': {error_msg}"
                errors.append(full_msg)
                logger.warning(
                    f"Validation [{record.file_name}] – {full_msg}"
                )

    record.validation_errors.extend(errors)

    if errors:
        logger.warning(
            f"[{record.file_name}] {len(errors)} validation error(s)"
        )
    else:
        logger.info(f"[{record.file_name}] passed all validations")

    return record


# ---------------------------------------------------------------------------
# Batch validation
# ---------------------------------------------------------------------------

def validate_all_records(records: List[AuditRecord]) -> List[AuditRecord]:
    """
    Validate every record and log a summary.
    Returns the same list with validation_errors populated.
    """
    logger.info("=" * 60)
    logger.info("VALIDATION PHASE")
    logger.info("=" * 60)

    validated = [validate_record(r) for r in records]

    files_with_errors = sum(1 for r in validated if r.validation_errors)
    total_errors      = sum(len(r.validation_errors) for r in validated)

    logger.info(f"Total validated  : {len(records)}")
    logger.info(f"Files with errors: {files_with_errors}")
    logger.info(f"Total errors     : {total_errors}")
    logger.info("=" * 60)

    return validated
