"""
export_view.py
--------------
GET /api/final-summary/export/

Query parameters (all optional except factory + date range which are required):
  factory    : exact factory name (required)
  client     : exact client/buyer name (required)
  date_from  : YYYY-MM-DD (required)
  date_to    : YYYY-MM-DD (required)
  style      : partial match on style_no (optional)
  po         : partial match on po_no (optional)

Builds the Excel summary workbook using summary_writer.py and streams it.
"""

import logging
import tempfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.http import FileResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from final_summary.models import AuditReport, DefectEntry

logger = logging.getLogger(__name__)


def _build_records_for_writer(reports):
    """
    Convert Django AuditReport QuerySet into the list-of-dicts format
    that summary_writer.write_summary() expects (mirrors v_audit_full view).
    """
    report_ids = [r.pk for r in reports]

    # Batch-fetch all defect entries
    defect_map: dict[int, list[dict]] = {}
    for de in DefectEntry.objects.filter(report_id__in=report_ids).order_by("category", "item"):
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
            "report_id":       r.pk,
            "file_name":       r.file_name,
            "factory":         r.factory,
            "buyer":           r.client,
            "style_no":        r.style_no,
            "item_name":       r.item_name,
            "country":         r.country,
            "po_no":           r.po_no,
            "inspection_type": r.inspection_type,
            "date_of_issue":   str(r.date_of_issue) if r.date_of_issue else "",
            "audit_result":    r.audit_result,
            "ship_qty":        r.ship_qty,
            "audit_qty":       r.audit_qty,
            "defect_qty":      r.defect_qty,
            "defect_percentage": r.defect_percentage,
            "inspector":       r.inspector,
            "person":          r.person,
            "po_qty_pcs":      r.po_qty_pcs,
            "po_qty_pack":     r.po_qty_pack,
            "po_qty_set":      r.po_qty_set,
            "po_wh":           str(r.po_wh) if r.po_wh else "",
            "exf":             str(r.exf) if r.exf else "",
            "po_edt":          str(r.po_edt) if r.po_edt else "",
            "plan_edt":        str(r.plan_edt) if r.plan_edt else "",
            "plan_wh":         str(r.plan_wh) if r.plan_wh else "",
            "factory_in":      r.factory_in_time,
            "factory_out":     r.factory_out_time,
            "factory_total_hours": r.factory_total_hours,
            "audit_start":     r.audit_start_time,
            "audit_end":       r.audit_end_time,
            "audit_total_hours": r.audit_total_hours,
            "acceptable_defect_qty": r.acceptable_defect_qty,
            "has_validation_errors": r.has_validation_errors,
            "created_at":      r.created_at,
        })

    return records, defect_map


class AuditExportView(APIView):
    """
    GET /api/final-summary/export/

    Required params: factory, client, date_from, date_to
    Optional params: style, po
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # ── Parse params ──────────────────────────────────────────────────────
        factory   = request.query_params.get("factory", "").strip()
        client    = request.query_params.get("client", "").strip()
        date_from = request.query_params.get("date_from", "").strip()
        date_to   = request.query_params.get("date_to", "").strip()
        style     = request.query_params.get("style", "").strip()
        po        = request.query_params.get("po", "").strip()

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

        # ── Query DB ──────────────────────────────────────────────────────────
        try:
            qs = AuditReport.objects.filter(
                factory__iexact=factory,
                client__iexact=client,
                date_of_issue__gte=date_from,
                date_of_issue__lte=date_to,
            ).order_by("date_of_issue", "style_no")

            if style:
                qs = qs.filter(style_no__icontains=style)
            if po:
                qs = qs.filter(po_no__icontains=po)

            if not request.user.is_staff:
                qs = qs.filter(batch__created_by=request.user)

            reports = list(qs)
        except Exception as exc:
            logger.exception("Export query failed: %s", exc)
            return Response({"detail": "Query failed."}, status=500)

        if not reports:
            return Response(
                {"detail": "No records found for the given filters."},
                status=404,
            )

        # ── Build data for writer ─────────────────────────────────────────────
        records, defect_map = _build_records_for_writer(reports)

        # ── Generate Excel ────────────────────────────────────────────────────
        output_dir = Path(settings.BASE_DIR) / "media" / "output" / "final_summary"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename  = f"audit_summary_{factory.replace(' ', '_')}_{timestamp}.xlsx"
        output_path = output_dir / filename

        try:
            from final_summary.helpers.summary_writer import write_summary
            write_summary(records, defect_map, output_path)
        except Exception as exc:
            logger.exception("Summary generation failed: %s", exc)
            return Response({"detail": "Could not generate Excel file."}, status=500)

        response = FileResponse(
            open(output_path, "rb"),
            as_attachment=True,
            filename=filename,
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            ),
        )
        return response