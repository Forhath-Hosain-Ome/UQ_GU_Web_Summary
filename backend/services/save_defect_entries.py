"""
save_defect_entries.py
----------------------
Persists defect_rows (already enriched by defects.py) into the DefectEntry
DB table.

defects.py has ALREADY done the defect_master lookup — each row dict
coming in has:
    {
        "item_no":       int,   # 1-based position = serial
        "category_code": str,   # e.g. "A"
        "category":      str,   # e.g. "Fabrics"  (label only, from master)
        "item":          str,   # canonical defect name
        "major":         int,
        "minor":         int,
        "comment":       str,
        "name_matched":  bool,
    }

This module just writes them to the DB.  No second master lookup needed.

The stored `category` field combines code + label so the DB is self-contained:
    "A - Fabrics", "B - Sewing", "A - SPEC", etc.

Usage
-----
    from final_summary.services.save_defect_entries import save_defect_entries

    save_defect_entries(audit_report=report_instance, defect_rows=record.defect_rows)

Idempotency
-----------
Existing DefectEntry rows for the report are deleted before re-inserting.
Safe to call multiple times (e.g. on retry).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from django.db import transaction

from final_summary.models import DefectEntry

logger = logging.getLogger(__name__)


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return default


def save_defect_entries(
    audit_report,                        # saved AuditReport Django model instance
    defect_rows: List[Dict[str, Any]],
) -> int:
    """
    Delete existing DefectEntry rows for *audit_report*, then bulk-insert
    fresh ones from *defect_rows*.

    Parameters
    ----------
    audit_report : AuditReport instance (must already be saved to DB)
    defect_rows  : list of dicts produced by defects.py extract()

    Returns
    -------
    Number of DefectEntry rows inserted.
    """
    # ── Wipe old rows (idempotent re-runs) ────────────────────────────────
    deleted, _ = DefectEntry.objects.filter(report=audit_report).delete()
    if deleted:
        logger.debug(
            "save_defect_entries: deleted %d old row(s) for report_id=%s",
            deleted, audit_report.pk,
        )

    # ── Build new rows ─────────────────────────────────────────────────────
    to_create: List[DefectEntry] = []

    for row in (defect_rows or []):
        major   = _safe_int(row.get("major"))
        minor   = _safe_int(row.get("minor"))
        comment = str(row.get("comment") or "").strip()

        # Skip rows with nothing in them
        if not major and not minor and not comment:
            continue

        code  = str(row.get("category_code") or "").strip()
        label = str(row.get("category") or "").strip()

        # Combine into single field: "A - Fabrics", "B - Sewing", etc.
        # If either part is missing, store whatever we have gracefully.
        if code and label:
            category = f"{code} - {label}"
        elif code:
            category = code
        else:
            category = label

        to_create.append(
            DefectEntry(
                report      = audit_report,
                serial      = _safe_int(row.get("item_no")),
                category    = category,
                defect_name = str(row.get("item") or "").strip(),
                major       = major,
                minor       = minor,
                comment     = comment,
            )
        )

    # ── Bulk insert ────────────────────────────────────────────────────────
    with transaction.atomic():
        DefectEntry.objects.bulk_create(to_create)

    logger.info(
        "save_defect_entries: inserted %d row(s) for report_id=%s",
        len(to_create), audit_report.pk,
    )
    return len(to_create)