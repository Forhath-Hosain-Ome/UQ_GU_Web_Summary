"""
extraction/validation/__init__.py
----------------------------------
Public API for the validation pipeline.

Usage in the task layer:
    from extraction.validation import run_validation

    records = run_validation(records)
    # Each record now has validation_errors and blocking_errors populated.

Pipeline order (always applied in this sequence):
  1. date_time.apply_date_time_refinement  — format dates + times
  2. rules.validate_record                 — non-blocking field checks
  3. blocking.validate_blocking            — blocking required-field checks
"""

import logging
from typing import Any, List

from .date_time import apply_date_time_refinement
from .rules     import validate_record, validate_all
from .blocking  import validate_blocking, validate_blocking_all


def run_validation(records: List[Any]) -> List[Any]:
    """
    Run the complete validation pipeline on a list of AuditRecord objects.

    Stages
    ------
    1. Date/time refinement  (all records)
    2. Field-level rules     (all records, non-blocking warnings)
    3. Blocking checks       (all records, may block save)

    Returns the same list with all error lists populated.
    """
    logging.info("=" * 60)
    logging.info("VALIDATION PIPELINE — %d record(s)", len(records))
    logging.info("=" * 60)

    # Stage 1: date/time
    records = [apply_date_time_refinement(r) for r in records]

    # Stage 2: field-level rules (non-blocking)
    records = validate_all(records)

    # Stage 3: blocking checks
    records = validate_blocking_all(records)

    blocked   = sum(1 for r in records if r.blocking_errors)
    warned    = sum(1 for r in records if r.validation_errors)
    clean     = len(records) - blocked

    logging.info(
        "Validation complete: %d clean | %d warned | %d blocked",
        clean, warned, blocked,
    )
    return records


__all__ = [
    # Pipeline
    "run_validation",
    # Individual stages (for testing or custom pipelines)
    "apply_date_time_refinement",
    "validate_record",
    "validate_all",
    "validate_blocking",
    "validate_blocking_all",
]