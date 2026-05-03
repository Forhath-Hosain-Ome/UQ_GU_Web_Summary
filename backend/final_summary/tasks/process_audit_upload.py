"""
tasks/process_audit_upload.py
------------------------------
Celery task: full audit-extraction pipeline for one UploadBatch.

Pipeline
--------
1. Discover all .xlsx / .xls files in the temp upload folder
2. extract_record()   — runs the existing rule-extractor on each file
3. validate_all_records() + validate_blocking_all()
4. _save_record()     — persist AuditReport + DefectEntry rows
5. Update UploadBatch counters / status
6. Push WebSocket events at each stage
7. Always clean up the temp folder in finally
"""

import json
import logging
import shutil
from pathlib import Path

from celery import shared_task
from django.utils.dateparse import parse_date

from final_summary.models import UploadBatch, AuditReport, DefectEntry

logger = logging.getLogger(__name__)


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
    """Coerce any date-like value to a Python date, or return None."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # Try ISO first
    d = parse_date(s)
    if d:
        return d
    # Try common regional formats
    from datetime import datetime
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%m-%d-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    logger.debug("Could not parse date: %r", s)
    return None


# ── Persist one record ────────────────────────────────────────────────────────

def _save_record(batch: UploadBatch, record) -> bool:
    """
    Persist one AuditRecord (dataclass from extractor_service) to the DB.
    Returns True on success, False if skipped or failed.
    """
    # Skip exact duplicates within this batch
    if AuditReport.objects.filter(batch=batch, file_name=record.file_name).exists():
        logger.info("Duplicate skipped: %s", record.file_name)
        return False

    try:
        report = AuditReport.objects.create(
            batch               = batch,
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
            blocking_errors       = ", ".join(record.blocking_errors or []),
            do_orders_json        = json.dumps(record.do_orders or []),
        )

        # Bulk-save defect entries
        defect_objects = []
        for d in (record.defect_rows or []):
            if not isinstance(d, dict):
                continue
            cat     = (d.get("category") or "").strip()
            item    = (d.get("item") or "").strip()
            major   = int(d.get("major", 0) or 0)
            minor   = int(d.get("minor", 0) or 0)
            comment = (d.get("comment") or "").strip()

            # Skip empty rows
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
    max_retries=0,       # no retry — temp folder is deleted in finally
    soft_time_limit=1800,
    time_limit=2100,
    name="final_summary.process_audit_upload",
)
def process_audit_upload(self, batch_id: int, upload_folder: str, format_type: str = "SPI") -> dict:
    """
    Parameters
    ----------
    batch_id      : UploadBatch PK
    upload_folder : absolute path to the temp dir containing uploaded Excel files
    """
    # Lazy imports keep circular-import risk low
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

        # Discover files (skip temp files Excel creates)
        excel_files = sorted(
            p for p in upload_path.rglob("*")
            if p.suffix.lower() in (".xlsx", ".xls") and not p.name.startswith("~$")
        )

        if not excel_files:
            raise ValueError("No Excel files found in upload folder.")

        # Do not set total_files yet — determine after sheet expansion
        batch.save(update_fields=["status"])
        _push_progress(batch, stage="EXTRACTING")

        # ── Stage 1: Extract ──────────────────────────────────────────────────
        # Sheet configuration based on format_type
        fmt = format_type.upper() if format_type else "SPI"
        SHEET_CONFIG = {
            "SPI":     ["Final", "Re-Final", "INLINE"],
            "REGULAR": ["Final", "Refinal", "Inline", "Sample"],
            "SWEATER": ["Final", "Refinal", "Sample"],
        }
        target_sheets = SHEET_CONFIG.get(fmt, SHEET_CONFIG["SPI"])

        extracted        = []
        extract_failures = []

        for excel_path in excel_files:
            # Determine which sheets exist in this workbook
            try:
                import openpyxl
                wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
                sheet_names = wb.sheetnames
                wb.close()
            except Exception as exc:
                logger.exception("Failed to read workbook sheets: %s", exc)
                extract_failures.append(f"{excel_path.name}: cannot read sheets")
                continue

            # Match target sheets (case-insensitive)
            sheets_to_process = []
            for tname in target_sheets:
                match = next((s for s in sheet_names if s.lower() == tname.lower()), None)
                if match:
                    sheets_to_process.append(match)

            # If none found, fall back to first sheet to preserve backward compatibility
            if not sheets_to_process:
                if sheet_names:
                    sheets_to_process = [sheet_names[0]]
                else:
                    extract_failures.append(f"{excel_path.name}: no sheets found")
                    continue

            for sheet_name in sheets_to_process:
                try:
                    record = extract_record(excel_path, sheet_name=sheet_name)
                    # Tag record with sheet for uniqueness
                    record.file_name = f"{excel_path.name} ({sheet_name})"
                    extracted.append(record)
                except Exception as exc:
                    logger.exception("Extraction failed: %s (%s) — %s", excel_path.name, sheet_name, exc)
                    extract_failures.append(f"{excel_path.name} ({sheet_name}): {exc}")

        # Update total expected records
        batch.total_files = len(extracted)
        batch.save(update_fields=["total_files"])
        _push_progress(batch, stage="VALIDATING")

        # ── Stage 2: Validate ─────────────────────────────────────────────────
        validated = validate_all_records(extracted)
        validated = validate_blocking_all(validated)

        clean   = [r for r in validated if not r.blocking_errors]
        blocked = [r for r in validated if r.blocking_errors]

        _push_progress(batch, stage="SAVING")

        # ── Stage 3: Save ─────────────────────────────────────────────────────
        saved = 0
        for record in clean:
            if _save_record(batch, record):
                saved += 1
                batch.processed_files += 1
            else:
                batch.failed_files += 1
            batch.save(update_fields=["processed_files", "failed_files"])
            _push_progress(batch, stage="SAVING")

        # Blocked + extract failures count as failed
        batch.failed_files += len(blocked) + len(extract_failures)
        batch.save(update_fields=["failed_files"])

        # ── Finalise status ───────────────────────────────────────────────────
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
            "batch_id": batch_id, "status": batch.status,
            "saved": saved, "blocked": len(blocked),
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
        # Always clean up temp folder
        shutil.rmtree(upload_folder, ignore_errors=True)
        logger.info("Cleaned up temp folder: %s", upload_folder)