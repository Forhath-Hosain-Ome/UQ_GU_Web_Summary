"""
extraction/validation/rules.py
--------------------------------
Non-blocking field-level validation rules.

These run after date_time refinement. Failures are appended to
record.validation_errors — they are WARNINGS, not blocks.
The record is still saved to the database.

Adding a new rule
-----------------
1. Write a bool function f(value) -> bool  (True = valid).
2. Add a tuple (field_name, f, "human-readable message") to RULES.

Blocking rules (required fields, defect sum check) live in blocking.py.
"""

import logging
import re
from datetime import datetime
from typing import Any, Callable, List, Tuple


# ---------------------------------------------------------------------------
# Validator functions
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


_REPORT_NO_RE = re.compile(r"^[A-Z]{2}\d{2}-\d{2}[A-Z0-9]+-\d+$")
_PO_NO_RE     = re.compile(r"^P\d{4}-\d{6}-\d{3}(-\d+)*$")


def is_valid_report_no(value: str) -> bool:
    if not value:
        return False
    return bool(_REPORT_NO_RE.match(value.strip().rstrip(".,;:")))


def is_valid_po_no(value: str) -> bool:
    if not value:
        return False
    return bool(_PO_NO_RE.match(value.strip()))


# ---------------------------------------------------------------------------
# Rule table
# (field_name, validator_fn, error_message)
# ---------------------------------------------------------------------------

Rule = Tuple[str, Callable[[Any], bool], str]

RULES: List[Rule] = [
    (
        "date_of_issue",
        is_date_mmddyyyy,
        "Date of Issue must be in MM/DD/YYYY format.",
    ),
    (
        "exf",
        lambda v: not v or is_date_mmddyyyy(v),
        "EXF date must be in MM/DD/YYYY format.",
    ),
    (
        "po_edt",
        lambda v: not v or is_date_mmddyyyy(v),
        "PO EDT must be in MM/DD/YYYY format.",
    ),
    (
        "po_wh",
        lambda v: not v or is_date_mmddyyyy(v),
        "PO WH date must be in MM/DD/YYYY format.",
    ),
    (
        "plan_edt",
        lambda v: not v or is_date_mmddyyyy(v),
        "Plan EDT must be in MM/DD/YYYY format.",
    ),
    (
        "plan_wh",
        lambda v: not v or is_date_mmddyyyy(v),
        "Plan WH must be in MM/DD/YYYY format.",
    ),
    (
        "ship_qty",
        lambda v: not v or is_numeric(v),
        "Ship Quantity should be a number.",
    ),
    (
        "audit_qty",
        lambda v: not v or is_numeric(v),
        "Audit Quantity should be a number.",
    ),
    (
        "po_no",
        lambda v: not v or is_valid_po_no(v),
        "PO No does not match expected pattern (e.g. P0426-482649-004).",
    ),
    # report_no: soft warning only — formats like PQC use sequential "01"
    (
        "report_no",
        lambda v: True,  # always passes — mismatch logged separately
        "Report No pattern note (non-blocking).",
    ),
]


# ---------------------------------------------------------------------------
# Apply rules
# ---------------------------------------------------------------------------

def validate_record(record: Any) -> Any:
    """
    Run all non-blocking validation rules on *record*.
    Appends human-readable messages to record.validation_errors.
    Returns the mutated record.
    """
    errors: List[str] = []

    # Soft log for report_no pattern if value present but doesn't match standard
    rno = getattr(record, "report_no", None)
    if rno and not is_valid_report_no(rno):
        msg = (
            f"'report_no': value '{rno}' does not match the standard pattern "
            f"(e.g. JP26-02BABL-001). This may be correct for this format."
        )
        errors.append(msg)
        logging.info(f"Soft validation [{record.file_name}]: {msg}")

    for field_name, rule_fn, error_msg in RULES:
        if field_name == "report_no":
            continue  # handled above
        value = getattr(record, field_name, None)
        if not value:
            continue  # only validate fields that were extracted
        if not rule_fn(value):
            full_msg = f"'{field_name}': {error_msg}"
            errors.append(full_msg)
            logging.warning(f"Validation [{record.file_name}]: {full_msg}")

    record.validation_errors.extend(errors)

    if errors:
        logging.warning(f"[{record.file_name}] {len(errors)} validation warning(s)")
    else:
        logging.info(f"[{record.file_name}] passed all field validations")

    return record


def validate_all(records: List[Any]) -> List[Any]:
    """Apply validate_record to every record. Returns the same list."""
    logging.info("=" * 60)
    logging.info("FIELD VALIDATION")
    logging.info("=" * 60)
    validated = [validate_record(r) for r in records]
    files_with_errors = sum(1 for r in validated if r.validation_errors)
    total_errors      = sum(len(r.validation_errors) for r in validated)
    logging.info(f"Records:           {len(records)}")
    logging.info(f"With warnings:     {files_with_errors}")
    logging.info(f"Total warnings:    {total_errors}")
    logging.info("=" * 60)
    return validated