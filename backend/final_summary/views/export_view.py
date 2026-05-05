"""
export_view.py
--------------
GET /api/final-summary/export/

Query parameters:
  factory    : exact factory name (required)
  client     : exact client/buyer name (required)
  date_from  : YYYY-MM-DD (required)
  date_to    : YYYY-MM-DD (required)
  style      : comma-separated partial matches on style_no (optional)
               e.g. style=A001,B002  → style_no LIKE %A001% OR style_no LIKE %B002%
  po         : comma-separated partial matches on po_no (optional)
               e.g. po=P001,P002    → po_no LIKE %P001% OR po_no LIKE %P002%

Filter logic:
  (factory AND client AND date_range)
  AND (style_1 OR style_2 OR ... OR po_1 OR po_2 OR ...)

Format-type mismatch:
  If filtered records come from batches with different format_type values,
  the export is blocked and the conflicting records are surfaced for the
  user to fix/skip via the Stage 3 Retry flow.

Template selection (by UploadBatch.format_type):
  SPI     → SPI-Final-78.xlsx
  REGULAR → General-Final-37.xlsx
  SWEATER → General-Final-37.xlsx  (same column layout as REGULAR/37)
"""

import logging
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db.models import Q
from django.http import FileResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from final_summary.models import AuditReport, DefectEntry, UploadBatch

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_csv_param(value: str) -> list[str]:
    """
    Split a comma-separated query param into a stripped list of non-empty strings.
    '  A001 , B002,  ' → ['A001', 'B002']
    """
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _build_style_po_filter(styles: list[str], pos: list[str]) -> Q | None:
    """
    Build an OR filter across all supplied styles and POs.
    style_A OR style_B OR po_X OR po_Y
    Returns None when both lists are empty (no filter applied).
    """
    if not styles and not pos:
        return None

    q = Q()
    for s in styles:
        q |= Q(style_no__icontains=s)
    for p in pos:
        q |= Q(po_no__icontains=p)
    return q


def _build_records_for_writer(reports):
    """
    Convert a Django AuditReport QuerySet/list into the list-of-dicts format
    that summary_writer.write_summary() expects (mirrors v_audit_full).
    Also batch-fetches DefectEntry rows and returns defect_map.
    """
    report_ids = [r.pk for r in reports]

    defect_map: dict[int, list[dict]] = {}
    for de in (
        DefectEntry.objects
        .filter(report_id__in=report_ids)
        .order_by("category", "item")
    ):
        defect_map.setdefault(de.report_id, []).append({
            "audit_report_id": de.report_id,
            "category":        de.category,
            "item":            de.item,
            "major_count":     de.major,
            "minor_count":     de.minor,
            "comment":         de.comment,
        })

    records = []
    for r in reports:
        records.append({
            "report_id":             r.pk,
            "file_name":             r.file_name,
            "factory":               r.factory,
            "buyer":                 r.client,
            "client":                r.client,
            "style_no":              r.style_no,
            "item_name":             r.item_name,
            "country":               r.country,
            "po_no":                 r.po_no,
            "inspection_type":       r.inspection_type,
            "date_of_issue":         str(r.date_of_issue) if r.date_of_issue else "",
            "audit_result":          r.audit_result,
            "ship_qty":              r.ship_qty,
            "audit_qty":             r.audit_qty,
            "defect_qty":            r.defect_qty,
            "defect_percentage":     r.defect_percentage,
            "inspector":             r.inspector,
            "person":                r.person,
            "po_qty_pcs":            r.po_qty_pcs,
            "po_qty_pack":           r.po_qty_pack,
            "po_qty_set":            r.po_qty_set,
            "po_wh":                 str(r.po_wh)    if r.po_wh    else "",
            "exf":                   str(r.exf)      if r.exf      else "",
            "po_edt":                str(r.po_edt)   if r.po_edt   else "",
            "plan_edt":              str(r.plan_edt) if r.plan_edt else "",
            "plan_wh":               str(r.plan_wh)  if r.plan_wh  else "",
            "factory_in":            r.factory_in_time,
            "factory_out":           r.factory_out_time,
            "factory_total_hours":   r.factory_total_hours,
            "audit_start":           r.audit_start_time,
            "audit_end":             r.audit_end_time,
            "audit_total_hours":     r.audit_total_hours,
            "acceptable_defect_qty": r.acceptable_defect_qty,
            "has_validation_errors": r.has_validation_errors,
            "created_at":            r.created_at,
            # batch format_type for mismatch detection (not written to sheet)
            "_format_type":          r.batch.format_type if r.batch_id else "SPI",
        })

    return records, defect_map


def _detect_format_mismatch(records: list[dict]) -> tuple[str | None, list[dict]]:
    """
    Check that all records share the same format_type.

    Returns
    -------
    (dominant_format, mismatched_records)
      dominant_format   : the format_type that appears most (or None if empty)
      mismatched_records: records whose format_type differs from dominant_format
    """
    if not records:
        return None, []

    from collections import Counter
    counts = Counter(r["_format_type"] for r in records)
    dominant = counts.most_common(1)[0][0]
    mismatched = [r for r in records if r["_format_type"] != dominant]
    return dominant, mismatched


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------

class AuditExportView(APIView):
    """
    GET /api/final-summary/export/

    Required params : factory, client, date_from, date_to
    Optional params : style (CSV), po (CSV)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # ── 1. Parse & validate params ────────────────────────────────────────
        factory   = request.query_params.get("factory",   "").strip()
        client    = request.query_params.get("client",    "").strip()
        date_from = request.query_params.get("date_from", "").strip()
        date_to   = request.query_params.get("date_to",   "").strip()
        styles    = _parse_csv_param(request.query_params.get("style", ""))
        pos       = _parse_csv_param(request.query_params.get("po",    ""))

        missing = []
        if not factory:   missing.append("factory")
        if not client:    missing.append("client")
        if not date_from: missing.append("date_from")
        if not date_to:   missing.append("date_to")

        if missing:
            return Response(
                {"detail": f"Required parameters missing: {', '.join(missing)}"},
                status=400,
            )

        # ── 2. Build queryset ─────────────────────────────────────────────────
        try:
            qs = (
                AuditReport.objects
                .select_related("batch")
                .filter(
                    factory__iexact=factory,
                    client__iexact=client,
                    date_of_issue__gte=date_from,
                    date_of_issue__lte=date_to,
                )
                .order_by("date_of_issue", "style_no")
            )

            # Optional style / PO OR filter
            sp_filter = _build_style_po_filter(styles, pos)
            if sp_filter is not None:
                qs = qs.filter(sp_filter)

            reports = list(qs)

        except Exception as exc:
            logger.exception("Export query failed: %s", exc)
            return Response({"detail": "Query failed."}, status=500)

        if not reports:
            return Response(
                {"detail": "No records found for the given filters."},
                status=404,
            )

        # ── 3. Build writer data ──────────────────────────────────────────────
        records, defect_map = _build_records_for_writer(reports)

        # ── 4. Format-type mismatch check ─────────────────────────────────────
        dominant_format, mismatched = _detect_format_mismatch(records)

        if mismatched:
            mismatch_details = [
                {
                    "file_name":    r["file_name"],
                    "format_type":  r["_format_type"],
                    "expected":     dominant_format,
                    "factory":      r["factory"],
                    "date_of_issue": r["date_of_issue"],
                }
                for r in mismatched
            ]
            return Response(
                {
                    "detail": (
                        f"Format-type mismatch detected. "
                        f"Dominant format is '{dominant_format}' but "
                        f"{len(mismatched)} record(s) use a different format. "
                        f"Please fix or skip these records via the Retry flow "
                        f"before exporting."
                    ),
                    "dominant_format":  dominant_format,
                    "mismatch_count":   len(mismatched),
                    "mismatched_records": mismatch_details,
                },
                status=409,
            )

        # Strip internal key before passing to writer
        for r in records:
            r.pop("_format_type", None)

        # ── 5. Select template ────────────────────────────────────────────────
        TEMPLATE_MAP = {
            "SPI":     "SPI-Final-78.xlsx",
            "REGULAR": "General-Final-37.xlsx",
            "SWEATER": "General-Final-37.xlsx",
        }
        template_name = TEMPLATE_MAP.get(dominant_format, "SPI-Final-78.xlsx")
        template_path = (
            Path(settings.BASE_DIR) / "media" / "templates" / template_name
        )

        if not template_path.exists():
            logger.error("Template not found: %s", template_path)
            return Response(
                {"detail": f"Template file '{template_name}' not found on server."},
                status=500,
            )

        # ── 6. Generate Excel ─────────────────────────────────────────────────
        output_dir = Path(settings.BASE_DIR) / "media" / "output" / "final_summary"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename  = (
            f"audit_summary_{factory.replace(' ', '_')}_"
            f"{client.replace(' ', '_')}_{timestamp}.xlsx"
        )
        output_path = output_dir / filename

        try:
            from final_summary.helpers.summary_writer import write_summary
            write_summary(
                records=records,
                defect_items_by_report=defect_map,
                output_path=output_path,
                template_path=template_path,
                format_type=dominant_format,
            )
        except Exception as exc:
            logger.exception("Summary generation failed: %s", exc)
            return Response(
                {"detail": f"Could not generate Excel file: {exc}"},
                status=500,
            )

        # ── 7. Stream file ────────────────────────────────────────────────────
        logger.info(
            "Export generated: factory=%r client=%r %s→%s template=%s records=%d",
            factory, client, date_from, date_to, template_name, len(records),
        )
        return FileResponse(
            open(output_path, "rb"),
            as_attachment=True,
            filename=filename,
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            ),
        )