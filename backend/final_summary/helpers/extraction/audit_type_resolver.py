"""
audit_type_resolver.py
----------------------
Infers the audit type from the Excel *file name* when the sheet itself does
not contain an explicit "Inspection Type" / "Audit Type" label.

Decision tree (evaluated top-to-bottom):
  1. RE-FINAL  (e.g. "2nd time RE-FINAL 50%")
  2. FINAL     (e.g. "FACTORY_FINAL_AUDIT")
  3. INLINE / SAMPLE / CMF  (keyword match, returned as-is)
  4. UNKNOWN   (no keyword matched)

BUG FIXED: RE-FINAL fall-through
----------------------------------
Previously the RE-FINAL branch only returned inside the `if nth_match` block,
so filenames like "RE-FINAL_audit.xlsx" (no ordinal) fell through to the FINAL
branch and were incorrectly typed as "FINAL N%".  Now the function returns
unconditionally from the RE-FINAL branch.
"""

import logging
import re

from ...models.audit_record import AuditRecord
from .label_config import AUDIT_PATTERNS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_pct(audit_qty: str, ship_qty: str) -> str:
    """Return 'NN.NN' percentage string, or '' if either quantity is invalid."""
    try:
        pct = round(int(audit_qty) / int(ship_qty) * 100, 2)
        return str(pct)
    except (ValueError, TypeError, ZeroDivisionError):
        logging.warning(
            f"Cannot compute audit % – audit_qty={audit_qty!r}, "
            f"ship_qty={ship_qty!r}"
        )
        return ""


# ---------------------------------------------------------------------------
# Main resolver
# ---------------------------------------------------------------------------

def resolve_audit_type(record: AuditRecord) -> str:
    """
    Derive the inspection type string from the record's file name.

    Returns one of:
      - "NN.NN% RE-FINAL"
      - "NTH TIME NN.NN% RE-FINAL"
      - "NN.NN% FINAL AUDIT"
      - "INLINE" | "SAMPLE" | "CMF"
      - "UNKNOWN"
    """
    if not record.file_name:
        return "UNKNOWN"

    name = record.file_name.lower().strip()

    # ── RE-FINAL ─────────────────────────────────────────────────────────────
    if re.search(AUDIT_PATTERNS["RE-FINAL"], name):
        pct       = _safe_pct(record.audit_qty, record.ship_qty)
        nth_match = re.search(r"\b(\d+(?:st|nd|rd|th))\s+time\b", name)

        if nth_match:
            nth_time = nth_match.group(1).upper()
            return f"{nth_time} RE-FINAL {pct}%" if pct else f"{nth_time} RE-FINAL"

        # BUG FIX: always return from the RE-FINAL branch; never fall through
        return f"RE-FINAL {pct}%" if pct else "RE-FINAL"

    # ── FINAL ─────────────────────────────────────────────────────────────────
    if re.search(AUDIT_PATTERNS["FINAL"], name):
        pct = _safe_pct(record.audit_qty, record.ship_qty)
        return f"FINAL {pct}%" if pct else "FINAL"

    # ── Other known types ─────────────────────────────────────────────────────
    for audit_type in ("INLINE", "SAMPLE", "CMF"):
        if re.search(AUDIT_PATTERNS[audit_type], name):
            return audit_type

    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Convenience wrapper used by post_processor
# ---------------------------------------------------------------------------

def extract_and_set_audit_type(record: AuditRecord) -> AuditRecord:
    """
    Set record.inspection_type from the file name if not already populated.
    Returns the (possibly mutated) record.
    """
    if not record.inspection_type:
        record.inspection_type = resolve_audit_type(record)
    return record
