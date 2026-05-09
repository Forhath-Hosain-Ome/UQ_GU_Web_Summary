"""
-----------------------------------
Blocking validation — records that fail are NOT saved to the database.

They are instead surfaced in the error log / retry flow so the user can
fix the missing data and re-upload.

Blocking checks
---------------
1. Required fields must not be empty.
2. Defect sum integrity: if defect_qty is set AND defect_rows were extracted,
   the sum of major+minor across defect_rows must equal defect_qty.
   A mismatch means the defect table was not read correctly.

Adding a new required field
----------------------------
Add a (field_attr, "human-readable message") tuple to _REQUIRED_FIELDS.
"""

import logging
from typing import Any, List, Tuple


# ---------------------------------------------------------------------------
# Required fields (blocking)
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS: List[Tuple[str, str]] = [
    ("factory",         "Factory name is missing"),
    ("date_of_issue",   "Date of Issue is missing"),
    ("inspection_type", "Inspection Type is missing"),
    ("report_no",       "Report Number is missing"),
    ("ship_qty",        "Shipping Quantity is missing"),
    ("audit_qty",       "Audit Quantity is missing"),
]


# ---------------------------------------------------------------------------
# Single-record blocking
# ---------------------------------------------------------------------------

def validate_blocking(record: Any) -> Any:
    """
    Run blocking checks on *record*.

    Any failure appends to record.blocking_errors.
    Records with blocking_errors are skipped by the DB save step and
    included in the error log / retry JSON.

    Returns the mutated record.
    """
    errors: List[str] = []

    # Check 1: required fields
    for field_attr, msg in _REQUIRED_FIELDS:
        val = getattr(record, field_attr, None)
        if not val or not str(val).strip():
            errors.append(f"REQUIRED_FIELD | {field_attr} | {msg}")
            logging.warning(f"[{record.file_name}] BLOCKING: {msg}")

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
                    f"DEFECT_MISMATCH | header={header_qty} "
                    f"extracted_sum={extracted_sum}"
                )
                errors.append(msg)
                logging.warning(f"[{record.file_name}] BLOCKING: {msg}")
        except (ValueError, TypeError):
            pass   # can't compare — don't block on this

    record.blocking_errors.extend(errors)
    return record


# ---------------------------------------------------------------------------
# Batch blocking
# ---------------------------------------------------------------------------

def validate_blocking_all(records: List[Any]) -> List[Any]:
    """Apply validate_blocking to every record. Returns the same list."""
    for r in records:
        validate_blocking(r)
    blocked = sum(1 for r in records if r.blocking_errors)
    logging.info(
        f"Blocking validation: {blocked}/{len(records)} record(s) blocked"
    )
    return records