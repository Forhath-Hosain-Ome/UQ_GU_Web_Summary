"""
views/top_5_view.py
--------------------
POST /api/final-summary/top-5/

Generates and streams a top-5 defect summary Excel report.

Request body (JSON)
-------------------
{
  "date_from":   "2025-01-01",          # required  YYYY-MM-DD
  "date_to":     "2025-01-31",          # required  YYYY-MM-DD
  "factory":     "ABC Factory Ltd",     # optional
  "client":      "H&M",                 # optional
  "format":      "buyer" | "internal"   # required
}

Response
--------
Binary .xlsx file download.
On error: JSON { "error": "..." }
"""

import json
import logging
import traceback
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from final_summary.models import AuditReport, DefectEntry

logger = logging.getLogger(__name__)

TEMPLATE_PATH = (
    Path(settings.BASE_DIR)
    / "media"
    / "templates"
    / "audit_report_template.xlsx"
)


# ---------------------------------------------------------------------------
# Data aggregation
# ---------------------------------------------------------------------------

def aggregate_report(
    date_from,
    date_to,
    factory: str = "",
    client: str = "",
    report_format: str = "buyer",
) -> dict:
    """
    Aggregate audit records and defect data for the top-5 report.

    Returns
    -------
    {
        "date_from":   date,
        "date_to":     date,
        "factory":     str,
        "client":      str,
        "format":      str,
        "by_type":     {inspection_type: [record_dict, ...]},
        "defect_map":  {report_id: [defect_dict, ...]},
        "top5_defects":{inspection_type: [(item, count), ...]},
    }
    """
    qs = AuditReport.objects.select_related(
        "batch", "batch__pair", "batch__pair__buyer", "batch__pair__factory"
    ).filter(
        date_of_issue__gte=date_from,
        date_of_issue__lte=date_to,
    )

    if factory:
        qs = qs.filter(factory__icontains=factory)
    if client:
        qs = qs.filter(client__icontains=client)

    reports    = list(qs.order_by("date_of_issue", "factory"))
    report_ids = [r.pk for r in reports]

    # Build defect map
    defect_map: dict[int, list[dict]] = {}
    for de in DefectEntry.objects.filter(report_id__in=report_ids):
        defect_map.setdefault(de.report_id, []).append({
            "category":    de.category,
            "item":        de.defect_name,    # keep key as "item" — only used locally
            "major_count": de.major,
            "minor_count": de.minor,
        })

    # Group by canonical inspection type
    def _canonical(itype: str) -> str:
        import re
        u = (itype or "").upper().strip()
        if re.search(r"RE[\s\-]?FINAL|REFINAL", u): return "RE-FINAL"
        if re.search(r"\bFINAL\b", u):               return "FINAL"
        if re.search(r"IN[\s\-]?LINE", u):           return "INLINE"
        if re.search(r"\bSAMPLE\b", u):              return "SAMPLE"
        if re.search(r"\bCMF\b", u):                 return "CMF"
        return "UNKNOWN"

    by_type: dict[str, list] = {}
    for r in reports:
        key = _canonical(r.inspection_type)
        by_type.setdefault(key, []).append({
            "report_id":       r.pk,
            "file_name":       r.file_name,
            "factory":         r.factory,
            "client":          r.client,
            "style_no":        r.style_no,
            "inspection_type": r.inspection_type,
            "date_of_issue":   str(r.date_of_issue) if r.date_of_issue else "",
            "audit_result":    r.audit_result,
            "ship_qty":        r.ship_qty,
            "audit_qty":       r.audit_qty,
            "defect_qty":      r.defect_qty,
            "defect_percentage": r.defect_percentage,
        })

    # Top-5 defects per inspection type
    from collections import Counter
    top5_defects: dict[str, list] = {}
    for itype, recs in by_type.items():
        counter: Counter = Counter()
        for rec in recs:
            for d in defect_map.get(rec["report_id"], []):
                counter[d["item"]] += int(d.get("major_count", 0) or 0)
        top5_defects[itype] = counter.most_common(5)

    return {
        "date_from":    date_from,
        "date_to":      date_to,
        "factory":      factory,
        "client":       client,
        "format":       report_format,
        "by_type":      by_type,
        "defect_map":   defect_map,
        "top5_defects": top5_defects,
    }


# ---------------------------------------------------------------------------
# Excel writer
# ---------------------------------------------------------------------------

def generate_report_excel(aggregated: dict, template_path: Path = None) -> object:
    """
    Generate a top-5 defect summary Excel workbook.

    Uses openpyxl to build a simple workbook — one sheet per inspection type,
    prefix summary rows then a top-5 defect table.

    Returns a BytesIO buffer ready for streaming.
    """
    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    _THIN   = Side(style="thin")
    _BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
    _YELLOW = PatternFill("solid", fgColor="FFFF00")
    _GREY   = PatternFill("solid", fgColor="D9D9D9")
    _BOLD   = Font(bold=True, size=9)
    _NORM   = Font(size=9)
    _CTR    = Alignment(horizontal="center", vertical="center")
    _LEFT   = Alignment(horizontal="left",   vertical="center")

    wb = openpyxl.Workbook()
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    ORDER = ["FINAL", "RE-FINAL", "INLINE", "SAMPLE", "CMF", "UNKNOWN"]

    for itype in ORDER:
        recs = aggregated["by_type"].get(itype)
        if not recs:
            continue

        ws = wb.create_sheet(title=itype[:31])
        ws.freeze_panes = "A4"

        # ── Header rows ───────────────────────────────────────────────────
        ws.merge_cells("A1:H1")
        c = ws["A1"]
        c.value     = (
            f"Top-5 Defect Summary | {itype} | "
            f"{aggregated['date_from']} → {aggregated['date_to']}"
        )
        c.font      = Font(bold=True, size=11)
        c.alignment = _CTR

        headers = [
            "Factory", "Style No", "Date", "Inspection Type",
            "Ship Qty", "Audit Qty", "Defect Qty", "Result",
        ]
        for col, hdr in enumerate(headers, start=1):
            cell = ws.cell(row=2, column=col, value=hdr)
            cell.font      = _BOLD
            cell.fill      = _YELLOW
            cell.alignment = _CTR
            cell.border    = _BORDER

        # ── Data rows ─────────────────────────────────────────────────────
        for row_idx, rec in enumerate(recs, start=3):
            row_data = [
                rec["factory"],
                rec["style_no"],
                rec["date_of_issue"],
                rec["inspection_type"],
                rec["ship_qty"],
                rec["audit_qty"],
                rec["defect_qty"],
                rec["audit_result"],
            ]
            for col, val in enumerate(row_data, start=1):
                cell = ws.cell(row=row_idx, column=col, value=val)
                cell.font      = _NORM
                cell.alignment = _CTR
                cell.border    = _BORDER

        next_row = len(recs) + 3 + 2   # gap

        # ── Top-5 defects ─────────────────────────────────────────────────
        top5 = aggregated["top5_defects"].get(itype, [])
        if top5:
            ws.cell(row=next_row, column=1, value="Top 5 Defects").font = _BOLD
            next_row += 1

            for rank, (item, count) in enumerate(top5, start=1):
                ws.cell(row=next_row, column=1, value=rank).font      = _NORM
                ws.cell(row=next_row, column=2, value=item).font      = _NORM
                ws.cell(row=next_row, column=3, value=count).font     = _NORM
                for col in range(1, 4):
                    ws.cell(row=next_row, column=col).border    = _BORDER
                    ws.cell(row=next_row, column=col).alignment = _CTR
                next_row += 1

        # Column widths
        col_widths = [26, 16, 12, 22, 10, 10, 10, 8]
        for i, w in enumerate(col_widths, start=1):
            ws.column_dimensions[
                openpyxl.utils.get_column_letter(i)
            ].width = w

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name="dispatch")
class AuditReportGenerateView(View):
    """
    POST /api/final-summary/top-5/
    """

    def post(self, request, *args, **kwargs):
        # ── Parse body ────────────────────────────────────────────────────
        try:
            body = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON body."}, status=400)

        date_from_str = body.get("date_from", "").strip()
        date_to_str   = body.get("date_to",   "").strip()
        report_format = body.get("format",    "buyer").strip().lower()
        factory       = body.get("factory",   "").strip()
        client        = body.get("client",    "").strip()

        if not date_from_str or not date_to_str:
            return JsonResponse(
                {"error": "date_from and date_to are required."},
                status=400,
            )

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

        # ── Aggregate ─────────────────────────────────────────────────────
        try:
            aggregated = aggregate_report(
                date_from=date_from,
                date_to=date_to,
                factory=factory,
                client=client,
                report_format=report_format,
            )
        except Exception as exc:
            logger.exception("Top-5 aggregation failed: %s", exc)
            return JsonResponse(
                {"error": f"Aggregation error: {exc}"},
                status=500,
            )

        if not aggregated["by_type"]:
            return JsonResponse(
                {"error": "No audit records found for the given filters."},
                status=404,
            )

        # ── Generate Excel ────────────────────────────────────────────────
        try:
            template = TEMPLATE_PATH if TEMPLATE_PATH.exists() else None
            buffer   = generate_report_excel(
                aggregated=aggregated,
                template_path=template,
            )
        except Exception as exc:
            logger.exception("Top-5 Excel generation failed: %s", exc)
            return JsonResponse(
                {"error": f"Excel generation error: {exc}"},
                status=500,
            )

        # ── Build filename ────────────────────────────────────────────────
        parts = [
            "top5_defect",
            report_format,
            date_from_str,
            "to",
            date_to_str,
        ]
        if factory:
            parts.insert(2, factory.replace(" ", "_")[:20])
        if client:
            parts.insert(2, client.replace(" ", "_")[:20])
        filename = "_".join(parts) + ".xlsx"

        # ── Stream ────────────────────────────────────────────────────────
        response = HttpResponse(
            content=buffer.getvalue(),
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["X-Report-Format"]     = report_format
        response["X-Inspection-Types"]  = ", ".join(aggregated["by_type"].keys())

        logger.info(
            "Top-5 report generated: format=%s factory=%r client=%r %s→%s types=%s",
            report_format, factory, client, date_from_str, date_to_str,
            list(aggregated["by_type"].keys()),
        )
        return response