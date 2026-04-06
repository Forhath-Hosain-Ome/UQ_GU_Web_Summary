"""
post_processor.py
-----------------
Derives, cleans, and enriches an AuditRecord *after* raw extraction.

Processing stages (run in order by post_process_record)
--------------------------------------------------------
1.  refine_record       – normalise time strings, strip non-numeric chars
2.  calculate totals    – factory hours / audit hours from start→end times
3.  find_missing_fields – re-scan other sheets for any still-empty fields
4.  refine_record       – clean newly found values
5.  recalculate totals  – if new times were found in stage 3
6.  defect qty fallback – scan summary section for Major Defects total
7.  PO qty routing      – parse "1200 PCS" / "300 SET" into typed fields
8.  defect percentage   – defect_qty / audit_qty * 100
9.  country from style  – first 2 chars of style_no → country code
10. audit type from name– infer inspection_type from the file name
"""

import logging
import re
from dataclasses import fields
from datetime import datetime, timedelta
from pathlib import Path

from ...models.audit_record import AuditRecord
from ..core.sheet_reader import read_all_sheets
from ..core.cell_grid import CellGrid
from .label_config import LABELS, STYLE_COUNTRY_MAP, NUMERIC_FIELDS
from .rule_extractor import extract_fields
from .text_number_extractor import extract_first_number_only
from .defect_qty_extractor import extract_defect_qty_with_fallback
from .audit_type_resolver import resolve_audit_type


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

_TIME_FIELDS = (
    "factory_in_time",
    "factory_out_time",
    "audit_start_time",
    "audit_end_time",
)


def _parse_hhmm(time_string: str) -> str:
    """
    Convert a loose time string to strict "HH:MM" (24-hour).
    Accepts: "9:30", "09:30", "9.30", "930", "9:30 AM", "09:30 PM", etc.
    Returns the original string unchanged if parsing fails.
    """
    if not isinstance(time_string, str):
        return ""

    time_string = time_string.strip()
    match = re.search(r"(\d{1,2})[:.]?(\d{2})?\s*([APap][Mm])?", time_string)
    if not match:
        return time_string

    hour_str, minute_str, am_pm = match.groups()
    hour   = int(hour_str)
    minute = int(minute_str) if minute_str else 0

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return time_string

    if am_pm:
        am_pm_lower = am_pm.lower()
        if am_pm_lower.startswith("p") and hour != 12:
            hour += 12
        elif am_pm_lower.startswith("a") and hour == 12:
            hour = 0

    try:
        return datetime.strptime(f"{hour}:{minute}", "%H:%M").strftime("%H:%M")
    except ValueError:
        return time_string


def refine_record(record: AuditRecord) -> AuditRecord:
    """
    1. Format all time fields to HH:MM.
    2. Strip non-numeric characters from numeric-only fields.
    """
    for field_name in _TIME_FIELDS:
        raw = getattr(record, field_name, "")
        if raw:
            refined = _parse_hhmm(raw)
            if refined != raw:
                logging.debug(f"  time refined [{field_name}]: '{raw}' → '{refined}'")
            setattr(record, field_name, refined)

    for field_name in NUMERIC_FIELDS:
        raw = getattr(record, field_name, None)
        if raw and isinstance(raw, str):
            cleaned = extract_first_number_only(raw)
            if cleaned and cleaned != raw:
                logging.debug(f"  numeric cleaned [{field_name}]: '{raw}' → '{cleaned}'")
                setattr(record, field_name, cleaned)

    return record


# ---------------------------------------------------------------------------
# Duration calculation
# ---------------------------------------------------------------------------

def _duration_hours(start: str, end: str) -> str | None:
    """
    Return decimal hours between two "HH:MM" strings, or None on error.
    Handles overnight spans (end < start) by adding 24 h.
    """
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
        logging.warning(f"Duration calc failed ('{start}' → '{end}'): {exc}")
        return None


# ---------------------------------------------------------------------------
# Missing-field search  (scans all other sheets)
# ---------------------------------------------------------------------------

def find_missing_fields(record: AuditRecord, path: Path) -> None:
    """
    For every still-empty field in *record*, scan all sheets of *path* and
    fill in any values found.  Modifies *record* in place.
    """
    missing = {
        f.name for f in fields(record)
        if not getattr(record, f.name)
        and f.name in LABELS
    }

    if not missing:
        return

    logging.info(f"Searching other sheets for: {missing}")
    targeted = {f: LABELS[f] for f in missing}

    for i, sheet_df in enumerate(read_all_sheets(path)):
        if not targeted:
            break

        grid = CellGrid(sheet_df)
        found = extract_fields(grid, targeted)

        for field_name, value in found.items():
            if value:
                setattr(record, field_name, value)
                del targeted[field_name]
                logging.info(f"  [{field_name}] found in sheet {i + 1}: '{value}'")


# ---------------------------------------------------------------------------
# Defect qty fallback
# ---------------------------------------------------------------------------

def apply_defect_qty_fallback(record: AuditRecord, path: Path) -> None:
    """
    If defect_qty is still empty, run the custom "second Major label" search
    on the first sheet.  Mutates *record* in place.
    """
    if record.defect_qty:
        return

    logging.info("defect_qty empty – running fallback extraction")
    df   = read_all_sheets(path)[0]
    grid = CellGrid(df)

    value = extract_defect_qty_with_fallback(grid, primary_value="")
    if value:
        record.defect_qty = value
        logging.info(f"  defect_qty (fallback): '{value}'")


# ---------------------------------------------------------------------------
# PO quantity routing
# ---------------------------------------------------------------------------

_PO_UNIT_MAP = {
    "pcs":  "po_qty_pcs",
    "pack": "po_qty_pack",
    "set":  "po_qty_set",
}


def apply_po_qty_extraction(record: AuditRecord) -> AuditRecord:
    """
    Parse record.po_qty ("1200 PCS", "300 SET", "500 PACK", bare "1200")
    and write the integer to the correct typed field (po_qty_pcs etc.).
    """
    raw = getattr(record, "po_qty", None)
    if not raw:
        return record

    raw_lower = raw.strip().lower()
    numeric_match = re.search(r"(\d+(?:\.\d+)?)", raw_lower)
    if not numeric_match:
        logging.warning(f"po_qty: no number found in '{raw}'")
        return record

    numeric_value = int(float(numeric_match.group(1)))
    target_field  = "po_qty_pcs"  # default

    for keyword, field_name in _PO_UNIT_MAP.items():
        if keyword in raw_lower:
            target_field = field_name
            break

    setattr(record, target_field, numeric_value)
    logging.debug(f"  po_qty '{raw}' → {target_field}={numeric_value}")
    return record


# ---------------------------------------------------------------------------
# Derived calculations
# ---------------------------------------------------------------------------

def _calc_defect_percentage(record: AuditRecord) -> None:
    """Set record.defect_percentage from defect_qty / audit_qty."""
    try:
        if not record.defect_qty or not record.audit_qty:
            record.defect_percentage = ""
            return

        defect_int = int(str(record.defect_qty).strip())
        audit_int  = int(str(record.audit_qty).strip())

        if audit_int == 0:
            record.defect_percentage = ""
            logging.warning(f"audit_qty=0 → cannot calc defect % for {record.file_name}")
            return

        pct = round(defect_int / audit_int * 100, 2)
        record.defect_percentage = f"{pct}%"

    except (ValueError, TypeError) as exc:
        record.defect_percentage = ""
        logging.warning(f"defect % calc failed for {record.file_name}: {exc}")


def _set_country_from_style(record: AuditRecord) -> None:
    """Derive record.country from the first 2 characters of style_no."""
    style = str(record.style_no).strip()
    if not style or len(style) < 2:
        record.country = "UNKNOWN"
        return
    record.country = STYLE_COUNTRY_MAP.get(style[:2], "UNKNOWN")


# ---------------------------------------------------------------------------
# Master post-processor
# ---------------------------------------------------------------------------

def post_process_record(record: AuditRecord, path: Path) -> AuditRecord:
    """
    Run all enrichment stages on *record* and return the updated record.
    This is the single entry point called from main.py.
    """
    # Stage 1 – normalise times & clean numeric fields
    record = refine_record(record)

    # Stage 2 – derive totals from times found in stage 1
    record.audit_total_hours   = _duration_hours(record.audit_start_time, record.audit_end_time)
    record.factory_total_hours = _duration_hours(record.factory_in_time, record.factory_out_time)

    # Stage 3 – search other sheets for still-missing fields
    find_missing_fields(record, path)

    # Stage 4 – re-clean newly found values
    record = refine_record(record)

    # Stage 5 – recalculate totals if new times were discovered
    if not record.audit_total_hours:
        record.audit_total_hours = _duration_hours(record.audit_start_time, record.audit_end_time)
    if not record.factory_total_hours:
        record.factory_total_hours = _duration_hours(record.factory_in_time, record.factory_out_time)

    # Stage 6 – defect qty fallback
    apply_defect_qty_fallback(record, path)

    # Stage 7 – route PO qty to typed sub-field
    record = apply_po_qty_extraction(record)

    # Stage 8 – calculated metrics
    _calc_defect_percentage(record)

    # Stage 9 – country from style prefix
    _set_country_from_style(record)

    # Stage 10 – inspection type from file name (if not already set)
    if not record.inspection_type:
        record.inspection_type = resolve_audit_type(record)
        logging.info(f"[{record.file_name}] inspection_type → '{record.inspection_type}'")

    return record
