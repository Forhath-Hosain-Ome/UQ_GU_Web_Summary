"""
final_summary/views/report_view.py
-----------------------------------
Django API endpoint for generating the audit summary Excel report.

Endpoint
--------
POST /top-5/

Request body (JSON)
-------------------
{
  "date_from":   "2025-01-01",          # required
  "date_to":     "2025-01-31",          # required
  "factory":     "ABC Factory Ltd",     # optional
  "client":      "H&M",                 # optional
  "format":      "buyer" | "internal"   # required
}

Response
--------
Binary .xlsx file download with Content-Disposition header.
On error: JSON { "error": "..." }

URL registration (urls.py)
--------------------------
    from final_summary.views.report_view import AuditReportGenerateView
    path("api/audit/report/generate/", AuditReportGenerateView.as_view(), name="audit-report-generate"),
"""

import logging
import traceback
from datetime import datetime
from pathlib import Path

from django.http import FileResponse, HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from services.report_aggregator import aggregate_report
from services.report_excel_writer import generate_report_excel

logger = logging.getLogger(__name__)

# Path to the pre-designed template (optional — set to None to auto-generate)
# Place your branded template at this path on the server.
TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "audit_report_template.xlsx"


@method_decorator(csrf_exempt, name="dispatch")
class AuditReportGenerateView(View):
    """
    POST  /api/audit/report/generate/
    Generates and streams the audit summary Excel report.
    """

    def post(self, request, *args, **kwargs):
        import json

        # ── Parse body ────────────────────────────────────────────────────────
        try:
            body = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON body."}, status=400)

        # ── Validate required fields ──────────────────────────────────────────
        date_from_str = body.get("date_from", "").strip()
        date_to_str   = body.get("date_to",   "").strip()
        report_format = body.get("format",    "buyer").strip().lower()
        factory       = body.get("factory",   "").strip()
        client        = body.get("client",    "").strip()

        if not date_from_str or not date_to_str:
            return JsonResponse({"error": "date_from and date_to are required."}, status=400)

        if report_format not in ("buyer", "internal"):
            return JsonResponse(
                {"error": "format must be 'buyer' or 'internal'."},
                status=400,
            )

        try:
            date_from = datetime.strptime(date_from_str, "%Y-%m-%d").date()
            date_to   = datetime.strptime(date_to_str,   "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse(
                {"error": "Dates must be in YYYY-MM-DD format."},
                status=400,
            )

        if date_from > date_to:
            return JsonResponse(
                {"error": "date_from must not be after date_to."},
                status=400,
            )

        # ── Aggregate data ────────────────────────────────────────────────────
        try:
            aggregated = aggregate_report(
                date_from=date_from,
                date_to=date_to,
                factory=factory,
                client=client,
                report_format=report_format,
            )
        except Exception as exc:
            logger.exception("Report aggregation failed: %s", exc)
            return JsonResponse({"error": f"Aggregation error: {exc}"}, status=500)

        if not aggregated["by_type"]:
            return JsonResponse(
                {"error": "No audit records found for the given filters."},
                status=404,
            )

        # ── Generate Excel ────────────────────────────────────────────────────
        try:
            template = TEMPLATE_PATH if TEMPLATE_PATH.exists() else None
            excel_buffer = generate_report_excel(
                aggregated=aggregated,
                template_path=template,
            )
        except Exception as exc:
            logger.exception("Excel generation failed: %s", exc)
            return JsonResponse({"error": f"Excel generation error: {exc}"}, status=500)

        # ── Build filename ────────────────────────────────────────────────────
        fmt_label = "buyer" if report_format == "buyer" else "internal"
        parts = ["audit_summary", fmt_label, date_from_str, "to", date_to_str]
        if factory:
            parts.insert(2, factory.replace(" ", "_")[:20])
        if client:
            parts.insert(2, client.replace(" ", "_")[:20])
        filename = "_".join(parts) + ".xlsx"

        # ── Stream response ───────────────────────────────────────────────────
        response = HttpResponse(
            content=excel_buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["X-Report-Format"]     = report_format
        response["X-Inspection-Types"]  = ", ".join(aggregated["by_type"].keys())

        logger.info(
            "Report generated: format=%s factory=%r client=%r %s→%s types=%s",
            report_format, factory, client, date_from_str, date_to_str,
            list(aggregated["by_type"].keys()),
        )
        return response