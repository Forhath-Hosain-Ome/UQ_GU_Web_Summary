"""
tasks/process_audit_upload.py
------------------------------
Celery task: full audit-extraction pipeline for one UploadBatch.

Sheet selection (per file):
  1. First sheet whose name contains a preferred keyword
     ("audit report", "inspection report", "final audit") — case-insensitive
  2. Active sheet (open when file was last saved)
  3. First sheet
"""

import json
import logging
import shutil
from pathlib import Path

from celery import shared_task
from django.utils.dateparse import parse_date

from final_summary.models import UploadBatch, AuditReport, DefectEntry

logger = logging.getLogger(__name__)

# Sheet name substrings checked in priority order (case-insensitive)
_PREFERRED_SHEET_KEYWORDS = ["audit report", "inspection report", "final audit"]


# ── WebSocket helpers ─────────────────────────────────────────────────────────

def _group_name(batch_id: int) -> str:
    return f"audit_batch_{batch_id}"


def _push(group: str, message: dict):
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        async_to_sync(layer.group_send)(group, message)
    except Exception as exc:
        logger.debug("WS push failed: %s", exc)


def _push_progress(batch: UploadBatch, stage: str = ""):
    _push(_group_name(batch.pk), {
        "type":             "audit.progress",
        "batch_id":         batch.pk,
        "status":           batch.status,
        "stage":            stage,
        "progress_percent": batch.progress_percent,
        "processed":        batch.processed_files,
        "total":            batch.total_files,
        "failed":           batch.failed_files,
    })


def _push_complete(batch: UploadBatch):
    _push(_group_name(batch.pk), {
        "type":             "audit.complete",
        "batch_id":         batch.pk,
        "status":           batch.status,
        "progress_percent": 100,
        "processed":        batch.processed_files,
        "total":            batch.total_files,
        "failed":           batch.failed_files,
        "report_count":     batch.reports.count(),
    })


def _push_error(batch: UploadBatch, message: str):
    _push(_group_name(batch.pk), {
        "type":          "audit.error",
        "batch_id":      batch.pk,
        "status":        UploadBatch.Status.FAILED,
        "error_message": message,
    })


# ── Date coercion ─────────────────────────────────────────────────────────────

def _to_date(value):
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    d = parse_date(s)
    if d:
        return d
    from datetime import datetime
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%m-%d-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    logger.debug("Could not parse date: %r", s)
    return None


# ── Sheet resolver ────────────────────────────────────────────────────────────

def _resolve_sheet_name(excel_path: Path) -> tuple[str | None, str]:
    """
    Choose the best sheet to extract the audit record from.

    Priority
    --------
    1. Keyword match  — first sheet whose name contains a preferred keyword
    2. Active sheet   — sheet open when file was last saved
    3. First sheet    — guaranteed fallback

    Returns (sheet_name, human_readable_reason).
    """
    try:
        import openpyxl
        wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
        sheet_names = wb.sheetnames

        if not sheet_names:
            wb.close()
            return None, "no sheets found in workbook"

        # 1. Keyword match
        for sheet in sheet_names:
            lower = sheet.lower().strip()
            for kw in _PREFERRED_SHEET_KEYWORDS:
                if kw in lower:
                    wb.close()
                    return sheet, f"keyword match '{kw}' → sheet '{sheet}'"

        # 2. Active sheet
        active = wb.active
        if active is not None:
            name = active.title
            wb.close()
            return name, f"active sheet '{name}'"

        # 3. First sheet
        first = sheet_names[0]
        wb.close()
        return first, f"first sheet '{first}' (fallback)"

    except Exception as exc:
        logger.warning("Could not read sheets from '%s': %s", excel_path.name, exc)
        return None, f"error reading workbook: {exc}"


# ── Persist one record ────────────────────────────────────────────────────────

def _save_record(batch: UploadBatch, record) -> bool:
    if AuditReport.objects.filter(batch=batch, file_name=record.file_name).exists():
        logger.info("Duplicate skipped: %s", record.file_name)
        return False

    try:
        report = AuditReport.objects.create(
            batch                 = batch,
            file_name             = record.file_name,
            factory               = record.factory or "",
            client                = record.client or "",
            date_of_issue         = _to_date(record.date_of_issue),
            inspection_type       = record.inspection_type or "",
            report_no             = record.report_no or "",
            audit_report          = record.audit_report or "",
            item_name             = record.item_name or "",
            style_no              = record.style_no or "",
            po_no                 = record.po_no or "",
            country               = record.country or "",
            factory_in_time       = record.factory_in_time or "",
            factory_out_time      = record.factory_out_time or "",
            factory_total_hours   = record.factory_total_hours or "",
            audit_start_time      = record.audit_start_time or "",
            audit_end_time        = record.audit_end_time or "",
            audit_total_hours     = record.audit_total_hours or "",
            audit_result          = record.audit_result or "-",
            po_qty                = record.po_qty or "",
            po_qty_pcs            = int(record.po_qty_pcs or 0),
            po_qty_pack           = int(record.po_qty_pack or 0),
            po_qty_set            = int(record.po_qty_set or 0),
            do_qty                = int(record.do_qty or 0),
            ship_qty              = str(record.ship_qty or ""),
            audit_qty             = str(record.audit_qty or ""),
            exf                   = _to_date(record.exf),
            po_edt                = _to_date(record.po_edt),
            po_wh                 = _to_date(record.po_wh),
            plan_edt              = _to_date(record.plan_edt),
            plan_wh               = _to_date(record.plan_wh),
            defect_qty            = str(record.defect_qty or ""),
            acceptable_defect_qty = str(record.acceptable_defect_qty or "-"),
            defect_percentage     = str(record.defect_percentage or ""),
            person                = record.person or "",
            inspector             = record.inspector or "",
            carton                = record.carton or "",
            needle_detector       = record.needle_detector or "",
            remarks               = record.remarks or "",
            do_set_col_size       = record.do_set_col_size or "",
            do_note               = record.do_note or "",
            has_validation_errors = bool(record.validation_errors),
            validation_errors     = ", ".join(record.validation_errors or []),
            blocking_errors       = ", ".join(record.blocking_errors or []),
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
                report=report, category=cat, item=item,
                major=major, minor=minor, comment=comment,
            ))

        if defect_objects:
            DefectEntry.objects.bulk_create(defect_objects)

        logger.info("Saved: %s → AuditReport #%s", record.file_name, report.pk)
        return True

    except Exception as exc:
        logger.exception("Failed to save %s: %s", record.file_name, exc)
        return False


# ── Main task ─────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=0,
    soft_time_limit=1800,
    time_limit=2100,
    name="final_summary.process_audit_upload",
)
def process_audit_upload(
    self, batch_id: int, upload_folder: str, format_type: str = "SPI"
) -> dict:
    """
    format_type is stored on the batch for template selection at export time.
    It does NOT affect which sheet is extracted — that is always resolved by
    _resolve_sheet_name() above.
    """
    from final_summary.helpers.extractor_service import extract_record
    from final_summary.helpers.validator import validate_all_records, validate_blocking_all

    try:
        batch = UploadBatch.objects.get(pk=batch_id)
    except UploadBatch.DoesNotExist:
        logger.error("Batch #%s not found", batch_id)
        return {"error": "Batch not found"}

    batch.status = UploadBatch.Status.PROCESSING
    batch.save(update_fields=["status"])
    _push_progress(batch, stage="EXTRACTING")

    try:
        upload_path = Path(upload_folder)
        if not upload_path.exists():
            raise FileNotFoundError(f"Upload folder missing: {upload_folder}")

        excel_files = sorted(
            p for p in upload_path.rglob("*")
            if p.suffix.lower() in (".xlsx", ".xls")
            and not p.name.startswith("~$")
        )

        if not excel_files:
            raise ValueError("No Excel files found in upload folder.")

        batch.total_files = len(excel_files)
        batch.save(update_fields=["total_files"])
        _push_progress(batch, stage="EXTRACTING")

        extracted        = []
        extract_failures = []

        for excel_path in excel_files:
            sheet_name, reason = _resolve_sheet_name(excel_path)

            if sheet_name is None:
                msg = f"{excel_path.name}: {reason}"
                logger.error("Extraction skipped — %s", msg)
                extract_failures.append(msg)
                continue

            logger.info("Extracting '%s' using %s", excel_path.name, reason)

            try:
                record = extract_record(excel_path, sheet_name=sheet_name)
                extracted.append(record)
            except Exception as exc:
                msg = f"{excel_path.name}: {exc}"
                logger.exception("Extraction failed — %s", msg)
                extract_failures.append(msg)

        _push_progress(batch, stage="VALIDATING")

        validated = validate_all_records(extracted)
        validated = validate_blocking_all(validated)

        clean   = [r for r in validated if not r.blocking_errors]
        blocked = [r for r in validated if r.blocking_errors]

        _push_progress(batch, stage="SAVING")

        saved = 0
        for record in clean:
            if _save_record(batch, record):
                saved += 1
                batch.processed_files += 1
            else:
                batch.failed_files += 1
            batch.save(update_fields=["processed_files", "failed_files"])
            _push_progress(batch, stage="SAVING")

        batch.failed_files += len(blocked) + len(extract_failures)
        batch.save(update_fields=["failed_files"])

        if batch.failed_files == 0:
            batch.status = UploadBatch.Status.COMPLETED
        elif saved == 0:
            batch.status = UploadBatch.Status.FAILED
        else:
            batch.status = UploadBatch.Status.PARTIAL

        error_lines = extract_failures + [
            f"{r.file_name}: {'; '.join(r.blocking_errors)}" for r in blocked
        ]
        if error_lines:
            batch.error_log = "\n".join(error_lines)

        batch.save(update_fields=["status", "error_log"])
        _push_complete(batch)

        logger.info(
            "Batch #%s done — saved:%d blocked:%d extract_fail:%d",
            batch_id, saved, len(blocked), len(extract_failures),
        )
        return {
            "batch_id":       batch_id,
            "status":         batch.status,
            "saved":          saved,
            "blocked":        len(blocked),
            "failed_extract": len(extract_failures),
        }

    except Exception as exc:
        logger.exception("Batch #%s fatal error: %s", batch_id, exc)
        batch.status    = UploadBatch.Status.FAILED
        batch.error_log = str(exc)
        batch.save(update_fields=["status", "error_log"])
        _push_error(batch, str(exc))
        return {"error": str(exc)}

    finally:
        shutil.rmtree(upload_folder, ignore_errors=True)
        logger.info("Cleaned up temp folder: %s", upload_folder)