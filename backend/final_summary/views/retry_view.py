"""
---------------------
Three endpoints for the Stage 3 Fix & Retry flow.

GET  /api/final-summary/retry/search/
  Search blocked records by date and/or style.
  Returns last 20 if no filters given.
  Query params: date (YYYY-MM-DD), style (partial), limit (default 20)

GET  /api/final-summary/retry/<batch_id>/download/
  Download the error JSON for a batch (blocked records only).

POST /api/final-summary/retry/upload/
  Upload a user-fixed error JSON file.
  Body: multipart with field "file" (JSON file) and "batch_id".
  Each record is re-validated; clean ones are saved; still-blocked ones
  are returned in the response.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db.models import Q
from django.http import JsonResponse
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from final_summary.models import AuditReport, UploadBatch, DefectEntry
from utils.error_json import build_error_payload, read_error_json

logger = logging.getLogger(__name__)


# ── Search ────────────────────────────────────────────────────────────────────

class RetrySearchView(APIView):
    """
    GET /api/final-summary/retry/search/

    Returns blocked AuditReport records matching the given filters.
    If no filters are given, returns the last 20 blocked records.

    Query params
    ------------
    date   : YYYY-MM-DD — filter by date_of_issue
    style  : partial string — filter by style_no (case-insensitive)
    limit  : max records to return (default 20, max 100)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_str  = request.query_params.get("date",  "").strip()
        style_str = request.query_params.get("style", "").strip()
        try:
            limit = min(int(request.query_params.get("limit", 20)), 100)
        except (ValueError, TypeError):
            limit = 20

        qs = AuditReport.objects.select_related(
            "batch", "batch__pair", "batch__pair__buyer", "batch__pair__factory"
        ).exclude(blocking_errors="")

        if not request.user.is_staff:
            qs = qs.filter(batch__created_by=request.user)

        if date_str:
            qs = qs.filter(date_of_issue=date_str)

        if style_str:
            qs = qs.filter(style_no__icontains=style_str)

        qs = qs.order_by("-date_of_issue", "-created_at")[:limit]

        records = []
        for r in qs:
            records.append({
                "report_id":        r.pk,
                "batch_id":         r.batch_id,
                "file_name":        r.file_name,
                "date_of_issue":    str(r.date_of_issue) if r.date_of_issue else "",
                "style_no":         r.style_no,
                "factory":          r.factory,
                "client":           r.client,
                "inspection_type":  r.inspection_type,
                "blocking_errors":  [e for e in r.blocking_errors.split("\n") if e],
                "validation_errors":[e for e in r.validation_errors.split("\n") if e],
                "cross_check_warnings": [e for e in r.cross_check_warnings.split("\n") if e],
            })

        return Response({
            "count":   len(records),
            "filters": {"date": date_str, "style": style_str},
            "records": records,
        })


# ── Download error JSON ───────────────────────────────────────────────────────

class RetryDownloadView(APIView):
    """
    GET /api/final-summary/retry/<batch_id>/download/

    Returns the error JSON for all blocked records in a batch.
    The user downloads this, fixes it, and re-uploads via RetryUploadView.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, batch_id: int):
        try:
            qs = UploadBatch.objects.all()
            if not request.user.is_staff:
                qs = qs.filter(created_by=request.user)
            batch = qs.get(pk=batch_id)
        except UploadBatch.DoesNotExist:
            return Response({"detail": "Batch not found."}, status=404)

        # Collect blocked reports
        blocked_reports = list(
            batch.reports.exclude(blocking_errors="").order_by("file_name")
        )

        if not blocked_reports:
            return Response({
                "batch_id":      batch_id,
                "total_blocked": 0,
                "records":       [],
                "message":       "No blocked records — nothing to download.",
            })

        # Build a lightweight serialisable record for each blocked report
        records_out = []
        for r in blocked_reports:
            defect_entries = list(
                DefectEntry.objects.filter(report=r).values(
                    "category", "item", "major", "minor", "comment"
                )
            )
            do_orders = []
            try:
                do_orders = json.loads(r.do_orders_json or "[]")
            except (json.JSONDecodeError, TypeError):
                pass

            records_out.append({
                "file_name":            r.file_name,
                "blocking_errors":      [e for e in r.blocking_errors.split("\n") if e],
                "validation_errors":    [e for e in r.validation_errors.split("\n") if e],
                "cross_check_warnings": [e for e in r.cross_check_warnings.split("\n") if e],
                "factory":              r.factory,
                "client":               r.client,
                "date_of_issue":        str(r.date_of_issue) if r.date_of_issue else "",
                "inspection_type":      r.inspection_type,
                "report_no":            r.report_no,
                "audit_report":         r.audit_report,
                "item_name":            r.item_name,
                "style_no":             r.style_no,
                "po_no":                r.po_no,
                "country":              r.country,
                "factory_in_time":      r.factory_in_time,
                "factory_out_time":     r.factory_out_time,
                "factory_total_hours":  r.factory_total_hours,
                "audit_start_time":     r.audit_start_time,
                "audit_end_time":       r.audit_end_time,
                "audit_total_hours":    r.audit_total_hours,
                "audit_result":         r.audit_result,
                "po_qty":               r.po_qty,
                "po_qty_pcs":           r.po_qty_pcs,
                "po_qty_pack":          r.po_qty_pack,
                "po_qty_set":           r.po_qty_set,
                "do_qty":               r.do_qty,
                "ship_qty":             r.ship_qty,
                "audit_qty":            r.audit_qty,
                "exf":                  str(r.exf)      if r.exf      else "",
                "po_edt":               str(r.po_edt)   if r.po_edt   else "",
                "po_wh":                str(r.po_wh)    if r.po_wh    else "",
                "plan_edt":             str(r.plan_edt) if r.plan_edt else "",
                "plan_wh":              str(r.plan_wh)  if r.plan_wh  else "",
                "defect_qty":           r.defect_qty,
                "acceptable_defect_qty":r.acceptable_defect_qty,
                "defect_percentage":    r.defect_percentage,
                "person":               r.person,
                "inspector":            r.inspector,
                "carton":               r.carton,
                "needle_detector":      r.needle_detector,
                "remarks":              r.remarks,
                "do_set_col_size":      r.do_set_col_size,
                "do_note":              r.do_note,
                "defect_rows":          [
                    {"category": d["category"], "item": d["item"],
                     "major": d["major"], "minor": d["minor"], "comment": d["comment"]}
                    for d in defect_entries
                ],
                "do_orders":            do_orders,
            })

        from datetime import datetime as _dt
        payload = {
            "version":       "2.0",
            "batch_id":      batch_id,
            "generated_at":  _dt.utcnow().isoformat(timespec="seconds"),
            "total_blocked": len(records_out),
            "instructions":  (
                "Fix the fields in 'blocking_errors' for each record. "
                "Then upload this file via the 'Upload Fixed JSON' button. "
                "Do NOT change 'file_name'."
            ),
            "records": records_out,
        }

        return Response(payload)


# ── Upload fixed JSON ─────────────────────────────────────────────────────────

class RetryUploadView(APIView):
    """
    POST /api/final-summary/retry/upload/

    Body: multipart/form-data
      batch_id : int   — which batch these records belong to
      file     : file  — the fixed error JSON file

    Each record is re-validated. Clean records are saved to the DB.
    Still-blocked records are returned in the response so the user
    can fix them again.
    """
    permission_classes = [IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser]

    def post(self, request):
        batch_id = request.data.get("batch_id")
        if not batch_id:
            return Response(
                {"detail": "batch_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response(
                {"detail": "A JSON file is required (field: 'file')."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Fetch batch
        try:
            qs = UploadBatch.objects.select_related("pair", "pair__buyer", "pair__factory")
            if not request.user.is_staff:
                qs = qs.filter(created_by=request.user)
            batch = qs.get(pk=batch_id)
        except UploadBatch.DoesNotExist:
            return Response({"detail": "Batch not found."}, status=404)

        # Parse JSON
        try:
            raw_json = uploaded_file.read().decode("utf-8")
            records  = read_error_json(raw=raw_json)
        except Exception as exc:
            return Response(
                {"detail": f"Could not parse JSON file: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not records:
            return Response(
                {"detail": "No records found in the uploaded JSON."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Re-validate and save
        from final_summary.extraction.validation import run_validation
        from final_summary.tasks.process_audit_upload import _save_record

        validated     = run_validation(records)
        clean         = [r for r in validated if not r.blocking_errors]
        still_blocked = [r for r in validated if r.blocking_errors]

        saved = 0
        for record in clean:
            if _save_record(batch, record):
                saved += 1
                batch.processed_files += 1
                if batch.failed_files > 0:
                    batch.failed_files -= 1

        if batch.failed_files == 0:
            batch.status = UploadBatch.Status.COMPLETED
        elif saved > 0:
            batch.status = UploadBatch.Status.PARTIAL

        batch.save(update_fields=["processed_files", "failed_files", "status"])

        logger.info(
            "Retry | batch #%s | submitted=%d | saved=%d | still_blocked=%d",
            batch_id, len(records), saved, len(still_blocked),
        )

        return Response({
            "batch_id":      batch.pk,
            "submitted":     len(records),
            "saved":         saved,
            "still_blocked": [
                {
                    "file_name":      r.file_name,
                    "blocking_errors":r.blocking_errors,
                    "validation_errors": r.validation_errors,
                }
                for r in still_blocked
            ],
        })