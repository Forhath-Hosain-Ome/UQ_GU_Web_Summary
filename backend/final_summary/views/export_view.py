"""
---------------------
GET /api/final-summary/export/

Generates and streams a filled Excel summary workbook using the pre-built
template determined by the BuyerFactoryPair.report_type.

Query parameters
----------------
Required:
  factory    exact factory name
  client     exact client/buyer name
  date_from  YYYY-MM-DD
  date_to    YYYY-MM-DD

Optional:
  style      comma-separated partial matches on style_no (OR logic)
  po         comma-separated partial matches on po_no    (OR logic)

Filter logic
------------
  (factory AND client AND date_range)
  AND (style_1 OR style_2 OR ... OR po_1 OR po_2 OR ...)

Error responses (JSON)
----------------------
  400  missing required params
  404  no records found
  409  format-type mismatch between records
  422  defect item(s) have no matching template column
  500  server / template / generation error
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

from final_summary.models import AuditReport, DefectEntry

logger = logging.getLogger(__name__)

# Template files live here
TEMPLATE_DIR = Path(settings.BASE_DIR) / "media" / "templates"

# report_type → template filename
TEMPLATE_MAP: dict[str, str] = {
    "KNIT_35":    "General-Final-35.xlsx",
    "WOVEN_37":   "General-Final-37.xlsx",
    "WOVEN_78":   "SPI-Final-78.xlsx",
    "SWEATER_37": "General-Final-37.xlsx",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_csv(value: str) -> list[str]:
    """'A001, B002' → ['A001', 'B002']"""
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _style_po_filter(styles: list[str], pos: list[str]) -> Q | None:
    """(style_A OR style_B OR po_X OR po_Y)"""
    if not styles and not pos:
        return None
    q = Q()
    for s in styles:
        q |= Q(style_no__icontains=s)
    for p in pos:
        q |= Q(po_no__icontains=p)
    return q


def _detect_format_mismatch(
    records: list[dict],
) -> tuple[str | None, list[dict]]:
    """Return (dominant_format, mismatched_records)."""
    if not records:
        return None, []
    from collections import Counter
    counts   = Counter(r["_report_type"] for r in records)
    dominant = counts.most_common(1)[0][0]
    mismatch = [r for r in records if r["_report_type"] != dominant]
    return dominant, mismatch


def _build_writer_data(
    reports,
) -> tuple[list[dict], dict[int, list[dict]]]:
    """Build records list + defect_map for summary_writer."""
    ids = [r.pk for r in reports]

    defect_map: dict[int, list[dict]] = {}
    for de in (
        DefectEntry.objects
        .filter(report_id__in=ids)
        .order_by("category", "defect_name")
    ):
        defect_map.setdefault(de.report_id, []).append({
            "audit_report_id": de.report_id,
            "category":        de.category,
            "item":            de.defect_name,
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
            # Internal — for mismatch detection only, stripped before writer
            "_report_type": r.batch.pair.report_type,
        })

    return records, defect_map


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------

class AuditExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # ── 1. Params ─────────────────────────────────────────────────────
        factory   = request.query_params.get("factory",   "").strip()
        client    = request.query_params.get("client",    "").strip()
        date_from = request.query_params.get("date_from", "").strip()
        date_to   = request.query_params.get("date_to",   "").strip()
        styles    = _parse_csv(request.query_params.get("style", ""))
        pos       = _parse_csv(request.query_params.get("po",    ""))

        missing = [
            k for k, v in [
                ("factory", factory), ("client", client),
                ("date_from", date_from), ("date_to", date_to),
            ] if not v
        ]
        if missing:
            return Response(
                {"detail": f"Required parameters missing: {', '.join(missing)}"},
                status=400,
            )

        # ── 2. Query ──────────────────────────────────────────────────────
        try:
            qs = (
                AuditReport.objects
                .select_related("batch", "batch__pair", "batch__pair__buyer",
                                "batch__pair__factory")
                .filter(
                    factory__iexact=factory,
                    client__iexact=client,
                    date_of_issue__gte=date_from,
                    date_of_issue__lte=date_to,
                )
                .order_by("date_of_issue", "style_no")
            )

            sp = _style_po_filter(styles, pos)
            if sp is not None:
                qs = qs.filter(sp)

            reports = list(qs)
        except Exception as exc:
            logger.exception("Export query failed: %s", exc)
            return Response({"detail": "Query failed."}, status=500)

        if not reports:
            return Response(
                {"detail": "No records found for the given filters."},
                status=404,
            )

        # ── 3. Build writer data ──────────────────────────────────────────
        records, defect_map = _build_writer_data(reports)

        # ── 4. Format mismatch check ──────────────────────────────────────
        dominant_format, mismatched = _detect_format_mismatch(records)

        if mismatched:
            return Response(
                {
                    "detail": (
                        f"Format-type mismatch: dominant='{dominant_format}' "
                        f"but {len(mismatched)} record(s) differ. "
                        f"Fix or skip via the Retry flow before exporting."
                    ),
                    "dominant_format":    dominant_format,
                    "mismatch_count":     len(mismatched),
                    "mismatched_records": [
                        {
                            "file_name":   r["file_name"],
                            "report_type": r["_report_type"],
                            "expected":    dominant_format,
                        }
                        for r in mismatched
                    ],
                },
                status=409,
            )

        # Strip internal key
        for r in records:
            r.pop("_report_type", None)

        # ── 5. Resolve template ───────────────────────────────────────────
        template_name = TEMPLATE_MAP.get(dominant_format, "SPI-Final-78.xlsx")
        template_path = TEMPLATE_DIR / template_name

        if not template_path.exists():
            return Response(
                {"detail": f"Template '{template_name}' not found on server."},
                status=500,
            )

        # ── 6. Generate Excel ─────────────────────────────────────────────
        output_dir = Path(settings.BASE_DIR) / "media" / "output" / "final_summary"
        output_dir.mkdir(parents=True, exist_ok=True)

        ts       = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = (
            f"audit_summary_"
            f"{factory.replace(' ', '_')}_"
            f"{client.replace(' ', '_')}_"
            f"{ts}.xlsx"
        )
        output_path = output_dir / filename

        try:
            from utils.summary_writer import write_summary, DefectMismatchError
            write_summary(
                records=records,
                defect_items_by_report=defect_map,
                output_path=output_path,
                template_path=template_path,
                format_type=dominant_format,
            )

        except DefectMismatchError as exc:
            logger.warning(
                "Defect mismatch on export: %d item(s) unmatched",
                len(exc.mismatches),
            )
            return Response(
                {
                    "detail": (
                        f"{len(exc.mismatches)} defect item(s) have no matching "
                        f"column in template '{template_name}'. "
                        f"These items must exist in the template header row."
                    ),
                    "mismatch_count":     len(exc.mismatches),
                    "mismatched_defects": exc.mismatches,
                },
                status=422,
            )

        except (FileNotFoundError, ValueError) as exc:
            logger.error("Export error: %s", exc)
            return Response({"detail": str(exc)}, status=500)

        except Exception as exc:
            logger.exception("Summary generation failed: %s", exc)
            return Response(
                {"detail": f"Could not generate Excel file: {exc}"},
                status=500,
            )

        # ── 7. Stream ─────────────────────────────────────────────────────
        logger.info(
            "Export OK: factory=%r client=%r %s→%s template=%s records=%d",
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