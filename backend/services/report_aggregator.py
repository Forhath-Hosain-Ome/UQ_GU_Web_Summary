"""
/services/report_aggregator.py
--------------------------------------------
Aggregates AuditReport + DefectEntry data from PostgreSQL for the
summary Excel report. Supports filtering by date range and factory/client.

Returns a dict keyed by inspection_type, each containing:
  - summary metrics (total_check, total_pass, total_defect, etc.)
  - top_5_defects list
  - date_rows list (one per unique date)
"""

from collections import defaultdict
from datetime import date
from typing import Any

from django.db.models import Count, Max, Sum, Q

from final_summary.models import AuditReport, DefectEntry


# ─────────────────────────────────────────────────────────────────────────────
# Public entry-point
# ─────────────────────────────────────────────────────────────────────────────

def aggregate_report(
    date_from: date,
    date_to: date,
    factory: str = "",
    client: str = "",
    report_format: str = "buyer",   # "buyer" | "internal"
) -> dict[str, Any]:
    """
    Returns:
    {
      "meta": { date_from, date_to, factory, client, format },
      "by_type": {
        "FINAL": { ...metrics... },
        "INLINE": { ...metrics... },
        ...
      }
    }
    """
    qs = AuditReport.objects.filter(
        date_of_issue__gte=date_from,
        date_of_issue__lte=date_to,
    )
    if factory:
        qs = qs.filter(factory__iexact=factory)
    if client:
        qs = qs.filter(client__iexact=client)

    inspection_types = list(
        qs.values_list("inspection_type", flat=True)
        .distinct()
        .order_by("inspection_type")
    )

    by_type = {}
    for itype in inspection_types:
        type_qs = qs.filter(inspection_type=itype)
        by_type[itype] = _build_type_block(type_qs, itype, report_format)

    return {
        "meta": {
            "date_from": date_from,
            "date_to": date_to,
            "factory": factory,
            "client": client,
            "format": report_format,
        },
        "by_type": by_type,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Per-inspection-type block
# ─────────────────────────────────────────────────────────────────────────────

def _safe_int(value) -> int:
    try:
        return int(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0


def _build_type_block(qs, inspection_type: str, report_format: str) -> dict:
    reports = list(qs.select_related().order_by("date_of_issue"))
    if not reports:
        return {}

    report_ids = [r.pk for r in reports]

    # ── Aggregate totals ──────────────────────────────────────────────────────
    total_check   = sum(_safe_int(r.audit_qty)  for r in reports)
    total_defect  = sum(_safe_int(r.defect_qty) for r in reports)
    total_pass    = total_check - total_defect
    total_audits  = len(reports)

    # ── Date range + unique dates ─────────────────────────────────────────────
    dates = sorted({r.date_of_issue for r in reports if r.date_of_issue})
    date_from = dates[0]  if dates else None
    date_to   = dates[-1] if dates else None
    total_days = len(dates)

    # ── Unique item names (capitalised) ──────────────────────────────────────
    item_names = sorted({
        r.item_name.strip().upper()
        for r in reports
        if r.item_name.strip()
    })

    # ── Auditors (unique, comma-joined) ───────────────────────────────────────
    auditors = sorted({
        r.inspector.strip()
        for r in reports
        if r.inspector.strip()
    })

    # ── Date rows — one per unique inspection date ────────────────────────────
    date_rows = _build_date_rows(reports, dates)

    # ── Top-5 defects ─────────────────────────────────────────────────────────
    top5 = _build_top5_defects(
        report_ids=report_ids,
        denominator=total_check if report_format == "buyer" else total_defect,
        report_format=report_format,
    )

    return {
        "inspection_type": inspection_type,
        "total_check":     total_check,
        "total_pass":      total_pass,
        "total_defect":    total_defect,
        "total_audits":    total_audits,
        "total_days":      total_days,
        "date_from":       date_from,
        "date_to":         date_to,
        "item_names":      item_names,
        "auditors":        auditors,
        "date_rows":       date_rows,
        "top5_defects":    top5,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Date rows  (one row per unique date_of_issue)
# ─────────────────────────────────────────────────────────────────────────────

def _build_date_rows(reports: list, dates: list) -> list[dict]:
    """
    For each unique date:
      - sum audit_qty  → check
      - sum defect_qty → defect
      - pass = check - defect
      - person = MAX(person) across all entries for that date
        (per spec: take the highest person value to avoid double-counting)
      - auditors = comma-joined unique inspector names
    """
    by_date = defaultdict(list)
    for r in reports:
        if r.date_of_issue:
            by_date[r.date_of_issue].append(r)

    rows = []
    for d in dates:
        day_reports = by_date[d]
        check  = sum(_safe_int(r.audit_qty)  for r in day_reports)
        defect = sum(_safe_int(r.defect_qty) for r in day_reports)
        person_values = [_safe_int(r.person) for r in day_reports if r.person]
        person = max(person_values) if person_values else 0

        day_auditors = sorted({
            r.inspector.strip()
            for r in day_reports
            if r.inspector.strip()
        })

        rows.append({
            "date":     d,
            "check":    check,
            "defect":   defect,
            "pass":     check - defect,
            "person":   person,
            "auditor":  ", ".join(day_auditors),
            "audits":   len(day_reports),
        })
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Top-5 defects
# ─────────────────────────────────────────────────────────────────────────────

def _build_top5_defects(
    report_ids: list[int],
    denominator: int,
    report_format: str,
) -> list[dict]:
    """
    Rules:
    - Aggregate DefectEntry rows (major + minor) grouped by category + item
    - Rank by total quantity descending
    - Take top 5 slots
    - Tie-breaking: if multiple items share the same qty for a rank slot,
        - If from the SAME category   → one category entry, items comma-joined
        - If from DIFFERENT categories → categories comma-joined, items comma-joined
    - Percentage:
        buyer    → qty / total_audit_qty   × 100
        internal → qty / total_defect_qty  × 100
    """
    entries = (
        DefectEntry.objects
        .filter(report_id__in=report_ids)
        .values("category", "defect_name")
        .annotate(qty=Sum("major") + Sum("minor"))
        .order_by("-qty")
    )

    # Group by qty to detect ties
    qty_groups: dict[int, list[dict]] = defaultdict(list)
    for e in entries:
        qty_groups[e["qty"]].append(e)

    top5 = []
    rank = 1
    for qty in sorted(qty_groups.keys(), reverse=True):
        if rank > 5:
            break
        group = qty_groups[qty]

        # Gather unique categories and items
        categories = list(dict.fromkeys(e["category"] for e in group))  # preserve order, dedup
        items_by_cat: dict[str, list[str]] = defaultdict(list)
        for e in group:
            items_by_cat[e["category"]].append(e["defect_name"])

        if len(categories) == 1:
            # Same category — one category, items comma-joined
            cat_label  = categories[0]
            item_label = ", ".join(dict.fromkeys(items_by_cat[categories[0]]))
        else:
            # Different categories — both comma-joined
            cat_label  = ", ".join(categories)
            item_label = ", ".join(
                item
                for cat in categories
                for item in items_by_cat[cat]
            )

        pct = round(qty / denominator * 100, 2) if denominator else 0.0

        top5.append({
            "rank":       rank,
            "category":   cat_label,
            "item":       item_label,
            "qty":        qty,
            "percentage": pct,
        })
        rank += 1

    return top5