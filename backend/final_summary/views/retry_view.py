"""
views/retry_view.py
--------------------
POST /final-summary/retry/

After a bulk upload some records fail blocking validation (e.g. factory
name missing, date unreadable).  The task writes those blocked records into
batch.error_log as a newline list.  The frontend can download a structured
error JSON via GET /final-summary/batches/<pk>/logs/error-json/ and let the
user fix the fields manually, then re-upload the corrected JSON here.

Flow
----
1. Frontend downloads  GET /final-summary/batches/<pk>/logs/error-json/
   → returns { batch_id, records: [{file_name, factory, client, ...}, ...] }
2. User opens JSON, fixes the flagged fields.
3. Frontend POSTs the fixed JSON to this endpoint.
4. We re-validate every record in the JSON.
5. Records that now pass → saved to DB, linked to the original batch.
6. Records that still fail → returned in the response as "still_blocked".

Request body (JSON):
  {
    "batch_id": 42,          ← required: links saved records to the original batch
    "records": [
      {
        "file_name": "DH26-01ABC-001.xlsx",
        "factory":   "BABL Factory",
        "client":    "UNIQLO",
        "date_of_issue": "01/15/2026",
        ... (all AuditRecord fields)
      },
      ...
    ]
  }

Response:
  {
    "batch_id":      42,
    "submitted":     5,
    "saved":         4,
    "still_blocked": [{ "file_name": "...", "blocking_errors": [...] }]
  }
"""
import json
import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from final_summary.models import UploadBatch, AuditReport, DefectEntry

logger = logging.getLogger(__name__)


def _save_fixed_record(batch: UploadBatch, record, user) -> bool:
    """
    Persist one fixed AuditRecord that passed re-validation.
    Skips if file_name already exists in this batch (idempotent).
    Returns True on success.
    """
    from django.utils.dateparse import parse_date
    from datetime import datetime

    def _to_date(value):
        if not value:
            return None
        s = str(value).strip()
        d = parse_date(s)
        if d:
            return d
        for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%m-%d-%Y"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None

    if AuditReport.objects.filter(batch=batch, file_name=record.file_name).exists():
        logger.info("Retry: duplicate skipped — %s", record.file_name)
        return False

    try:
        report = AuditReport.objects.create(
            batch               = batch,
            created_by          = user,
            file_name           = record.file_name,
            factory             = record.factory or "",
            client              = record.client or "",
            date_of_issue       = _to_date(record.date_of_issue),
            inspection_type     = record.inspection_type or "",
            report_no           = record.report_no or "",
            audit_report        = record.audit_report or "",
            item_name           = record.item_name or "",
            style_no            = record.style_no or "",
            po_no               = record.po_no or "",
            country             = record.country or "",
            factory_in_time     = record.factory_in_time or "",
            factory_out_time    = record.factory_out_time or "",
            factory_total_hours = record.factory_total_hours or "",
            audit_start_time    = record.audit_start_time or "",
            audit_end_time      = record.audit_end_time or "",
            audit_total_hours   = record.audit_total_hours or "",
            audit_result        = record.audit_result or "-",
            po_qty              = record.po_qty or "",
            po_qty_pcs          = int(record.po_qty_pcs or 0),
            po_qty_pack         = int(record.po_qty_pack or 0),
            po_qty_set          = int(record.po_qty_set or 0),
            do_qty              = int(record.do_qty or 0),
            ship_qty            = str(record.ship_qty or ""),
            audit_qty           = str(record.audit_qty or ""),
            exf                 = _to_date(record.exf),
            po_edt              = _to_date(record.po_edt),
            po_wh               = _to_date(record.po_wh),
            plan_edt            = _to_date(record.plan_edt),
            plan_wh             = _to_date(record.plan_wh),
            defect_qty            = str(record.defect_qty or ""),
            acceptable_defect_qty = str(record.acceptable_defect_qty or "-"),
            defect_percentage     = str(record.defect_percentage or ""),
            person              = record.person or "",
            inspector           = record.inspector or "",
            carton              = record.carton or "",
            needle_detector     = record.needle_detector or "",
            remarks             = record.remarks or "",
            do_set_col_size     = record.do_set_col_size or "",
            do_note             = record.do_note or "",
            has_validation_errors = bool(record.validation_errors),
            validation_errors     = ", ".join(record.validation_errors or []),
            blocking_errors       = "",   # cleared — record passed re-validation
            do_orders_json        = json.dumps(record.do_orders or []),
        )

        defect_objects = []
        for d in (record.defect_rows or []):
            if not isinstance(d, dict):
                continue
            cat     = (d.get("category") or "").strip()
            item    = (d.get("item") or "").strip()
            major   = int(d.get("major", 0) or 0)
            minor   = int(d.get("minor", 0) or 0)
            comment = (d.get("comment") or "").strip()
            if not cat and not item:
                continue
            if major == 0 and minor == 0 and not comment:
                continue
            defect_objects.append(DefectEntry(
                report=report, created_by=user,
                category=cat, item=item,
                major=major, minor=minor, comment=comment,
            ))
        if defect_objects:
            DefectEntry.objects.bulk_create(defect_objects)

        # Update batch counters
        batch.processed_files += 1
        if batch.failed_files > 0:
            batch.failed_files -= 1
        # Re-evaluate status
        if batch.failed_files == 0:
            batch.status = UploadBatch.Status.COMPLETED
        else:
            batch.status = UploadBatch.Status.PARTIAL
        batch.save(update_fields=["processed_files", "failed_files", "status"])

        logger.info("Retry saved: %s → AuditReport #%s", record.file_name, report.pk)
        return True

    except Exception as exc:
        logger.exception("Retry: failed to save %s: %s", record.file_name, exc)
        return False


class AuditRetryView(APIView):
    """
    POST /final-summary/retry/

    Body: { batch_id: int, records: [AuditRecord-shaped dicts] }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        batch_id = request.data.get("batch_id")
        records_raw = request.data.get("records")

        if not batch_id:
            return Response(
                {"detail": "batch_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(records_raw, list) or not records_raw:
            return Response(
                {"detail": "records must be a non-empty list."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Fetch the batch — user must own it (unless staff)
        try:
            qs = UploadBatch.objects.all()
            if not request.user.is_staff:
                qs = qs.filter(created_by=request.user)
            batch = qs.get(pk=batch_id)
        except UploadBatch.DoesNotExist:
            return Response({"detail": "Batch not found."}, status=status.HTTP_404_NOT_FOUND)

        # Import the AuditRecord dataclass + validators
        from final_summary.models.audit_record import AuditRecord
        from final_summary.helpers.validator import validate_blocking, apply_refinement_rules
        import dataclasses

        valid_fields = {f.name for f in dataclasses.fields(AuditRecord)}

        saved         = 0
        still_blocked = []

        for raw in records_raw:
            if not isinstance(raw, dict):
                continue

            # Build AuditRecord from the dict — ignore unknown keys
            kwargs = {k: v for k, v in raw.items() if k in valid_fields}
            try:
                record = AuditRecord(**kwargs)
            except Exception as exc:
                still_blocked.append({
                    "file_name":       raw.get("file_name", "unknown"),
                    "blocking_errors": [f"Could not parse record: {exc}"],
                })
                continue

            # Clear old error state so we validate from scratch
            record.blocking_errors   = []
            record.validation_errors = []

            # Re-apply date/time formatting
            record = apply_refinement_rules(record)

            # Re-run blocking validation
            record = validate_blocking(record)

            if record.blocking_errors:
                still_blocked.append({
                    "file_name":       record.file_name,
                    "blocking_errors": record.blocking_errors,
                    "validation_errors": record.validation_errors,
                })
                logger.warning(
                    "Retry: still blocked — %s: %s",
                    record.file_name, record.blocking_errors,
                )
                continue

            if _save_fixed_record(batch, record, request.user):
                saved += 1

        return Response(
            {
                "batch_id":      batch.pk,
                "submitted":     len(records_raw),
                "saved":         saved,
                "still_blocked": still_blocked,
            },
            status=status.HTTP_200_OK,
        )