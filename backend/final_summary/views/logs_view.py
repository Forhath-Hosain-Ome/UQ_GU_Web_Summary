"""
views/logs_view.py
-------------------
Two read-only endpoints for batch error/log inspection:

GET /final-summary/batches/<pk>/logs/
  Returns a structured breakdown of what failed in a batch — each error
  line from batch.error_log split into file_name + reason.

GET /final-summary/batches/<pk>/logs/error-json/
  Returns a downloadable JSON payload that the user can fix and re-POST
  to /final-summary/retry/.  Only blocked records (those in error_log)
  are included — successfully extracted records are not re-exported.

Error-JSON shape (same as utils/error_json_writer.py):
  {
    "version":       "1.0",
    "batch_id":      42,
    "generated_at":  "2026-01-05T10:30:00",
    "total_blocked": 3,
    "instructions":  "...",
    "records": [
      {
        "file_name":       "DH26-01ABC-001.xlsx",
        "blocking_errors": ["REQUIRED_FIELD | factory | Factory name is missing"],
        "validation_errors": [],
        "factory": "",
        "client":  "",
        ... (all other AuditRecord fields the user can edit)
      }
    ]
  }
"""
import logging
from datetime import datetime

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from final_summary.models import UploadBatch, AuditReport

logger = logging.getLogger(__name__)

_INSTRUCTIONS = (
    "Fix the fields listed in 'blocking_errors' for each record. "
    "Then POST this file (with batch_id) to /final-summary/retry/. "
    "Do NOT change the 'file_name' field — it is the unique identifier."
)


def _parse_error_lines(error_log: str) -> list[dict]:
    """
    Split batch.error_log into structured dicts.

    Each line has the format:
      "<file_name>: <reason>"
    or just a plain reason string if no colon is present.
    """
    parsed = []
    for raw_line in (error_log or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ": " in line:
            file_name, _, reason = line.partition(": ")
            parsed.append({
                "file_name": file_name.strip(),
                "reason":    reason.strip(),
            })
        else:
            parsed.append({
                "file_name": "",
                "reason":    line,
            })
    return parsed


class AuditBatchLogsView(APIView):
    """
    GET /final-summary/batches/<pk>/logs/
    Returns structured error log for a batch.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            qs = UploadBatch.objects.all()
            if not request.user.is_staff:
                qs = qs.filter(created_by=request.user)
            batch = qs.get(pk=pk)
        except UploadBatch.DoesNotExist:
            return Response({"detail": "Batch not found."}, status=status.HTTP_404_NOT_FOUND)

        error_lines = _parse_error_lines(batch.error_log)

        return Response({
            "batch_id":      batch.pk,
            "status":        batch.status,
            "total_files":   batch.total_files,
            "processed":     batch.processed_files,
            "failed":        batch.failed_files,
            "success_rate":  batch.success_rate,
            "error_count":   len(error_lines),
            "errors":        error_lines,
            "raw_error_log": batch.error_log or "",
        })


class AuditBatchErrorJsonView(APIView):
    """
    GET /final-summary/batches/<pk>/logs/error-json/

    Returns a JSON payload containing one record stub per failed file.
    The user fills in the missing/wrong fields and POSTs the result
    to /final-summary/retry/ to save them to the DB.

    For files that were blocked during extraction (no AuditReport row
    was created), we return a minimal stub with only the file_name and
    blocking_errors populated — the user must fill in the rest.

    For files that were extracted but blocked during validation, we
    return the full AuditReport data pre-populated so the user only
    needs to fix the flagged fields.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            qs = UploadBatch.objects.all()
            if not request.user.is_staff:
                qs = qs.filter(created_by=request.user)
            batch = qs.get(pk=pk)
        except UploadBatch.DoesNotExist:
            return Response({"detail": "Batch not found."}, status=status.HTTP_404_NOT_FOUND)

        error_lines = _parse_error_lines(batch.error_log)

        if not error_lines:
            return Response({
                "batch_id":      batch.pk,
                "total_blocked": 0,
                "records":       [],
                "message":       "No errors — nothing to retry.",
            })

        records_out = []

        for err in error_lines:
            file_name = err["file_name"]
            reason    = err["reason"]

            # Try to find an existing (partially-saved) AuditReport for this file
            existing = None
            if file_name:
                existing = AuditReport.objects.filter(
                    batch=batch, file_name=file_name
                ).first()

            if existing:
                # Pre-populate from DB so user fixes as little as possible
                records_out.append({
                    "file_name":         existing.file_name,
                    "blocking_errors":   [r for r in (existing.blocking_errors or "").split(", ") if r],
                    "validation_errors": [r for r in (existing.validation_errors or "").split(", ") if r],
                    "factory":           existing.factory,
                    "client":            existing.client,
                    "date_of_issue":     str(existing.date_of_issue) if existing.date_of_issue else "",
                    "inspection_type":   existing.inspection_type,
                    "report_no":         existing.report_no,
                    "audit_report":      existing.audit_report,
                    "item_name":         existing.item_name,
                    "style_no":          existing.style_no,
                    "po_no":             existing.po_no,
                    "country":           existing.country,
                    "factory_in_time":   existing.factory_in_time,
                    "factory_out_time":  existing.factory_out_time,
                    "factory_total_hours": existing.factory_total_hours,
                    "audit_start_time":  existing.audit_start_time,
                    "audit_end_time":    existing.audit_end_time,
                    "audit_total_hours": existing.audit_total_hours,
                    "audit_result":      existing.audit_result,
                    "po_qty":            existing.po_qty,
                    "po_qty_pcs":        existing.po_qty_pcs,
                    "po_qty_pack":       existing.po_qty_pack,
                    "po_qty_set":        existing.po_qty_set,
                    "do_qty":            existing.do_qty,
                    "ship_qty":          existing.ship_qty,
                    "audit_qty":         existing.audit_qty,
                    "exf":               str(existing.exf) if existing.exf else "",
                    "po_edt":            str(existing.po_edt) if existing.po_edt else "",
                    "po_wh":             str(existing.po_wh) if existing.po_wh else "",
                    "plan_edt":          str(existing.plan_edt) if existing.plan_edt else "",
                    "plan_wh":           str(existing.plan_wh) if existing.plan_wh else "",
                    "defect_qty":        existing.defect_qty,
                    "acceptable_defect_qty": existing.acceptable_defect_qty,
                    "defect_percentage": existing.defect_percentage,
                    "person":            existing.person,
                    "inspector":         existing.inspector,
                    "carton":            existing.carton,
                    "needle_detector":   existing.needle_detector,
                    "remarks":           existing.remarks,
                    "do_set_col_size":   existing.do_set_col_size,
                    "do_note":           existing.do_note,
                    "defect_rows":       [],   # user cannot edit these; defects stay as-is
                    "do_orders":         [],
                })
            else:
                # Extraction failed entirely — return a minimal stub
                records_out.append({
                    "file_name":         file_name,
                    "blocking_errors":   [reason],
                    "validation_errors": [],
                    # All editable fields blank — user must fill in
                    "factory":           "",
                    "client":            "",
                    "date_of_issue":     "",
                    "inspection_type":   "",
                    "report_no":         "",
                    "audit_report":      "",
                    "item_name":         "",
                    "style_no":          "",
                    "po_no":             "",
                    "country":           "",
                    "factory_in_time":   "",
                    "factory_out_time":  "",
                    "factory_total_hours": "",
                    "audit_start_time":  "",
                    "audit_end_time":    "",
                    "audit_total_hours": "",
                    "audit_result":      "-",
                    "po_qty":            "",
                    "po_qty_pcs":        0,
                    "po_qty_pack":       0,
                    "po_qty_set":        0,
                    "do_qty":            0,
                    "ship_qty":          "",
                    "audit_qty":         "",
                    "exf":               "",
                    "po_edt":            "",
                    "po_wh":             "",
                    "plan_edt":          "",
                    "plan_wh":           "",
                    "defect_qty":        "",
                    "acceptable_defect_qty": "-",
                    "defect_percentage": "",
                    "person":            "",
                    "inspector":         "",
                    "carton":            "",
                    "needle_detector":   "",
                    "remarks":           "",
                    "do_set_col_size":   "",
                    "do_note":           "",
                    "defect_rows":       [],
                    "do_orders":         [],
                })

        return Response({
            "version":       "1.0",
            "batch_id":      batch.pk,
            "generated_at":  datetime.utcnow().isoformat(timespec="seconds"),
            "total_blocked": len(records_out),
            "instructions":  _INSTRUCTIONS,
            "records":       records_out,
        })