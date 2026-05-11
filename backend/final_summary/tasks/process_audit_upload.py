"""
------------------------------
Celery task: full audit-extraction pipeline for one UploadBatch.

Pipeline
--------
1. Load the BuyerFactoryPair from the batch.
2. Get the correct extractor via FORMAT_REGISTRY.
3. Discover Excel files in the temp upload folder.
4. For each file: resolve sheet → extract record (with injected inspection_date).
5. Run run_validation() on all records.
6. Save clean records to DB; collect blocked records for error log.
7. Update UploadBatch counters and status.
8. Push WebSocket progress events at each stage.
9. Clean up temp folder.

Key design decisions
--------------------
- date_of_issue is injected from batch.inspection_date, never extracted.
- format_type is derived from batch.pair.report_type, never user-selected.
- factory / client are set from pair registration after cross-check.
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


def _push(group: str, message: dict) -> None:
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        async_to_sync(layer.group_send)(group, message)
    except Exception as exc:
        logger.debug("WS push failed: %s", exc)


def _push_progress(batch: UploadBatch, stage: str = "") -> None:
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


def _push_complete(batch: UploadBatch) -> None:
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


def _push_error(batch: UploadBatch, message: str) -> None:
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
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# ── DB save ───────────────────────────────────────────────────────────────────

def _save_record(batch: UploadBatch, record) -> bool:
    """
    Persist one AuditRecord dataclass to the Django ORM.
    Returns True on success, False if skipped or failed.
    """
    # Skip exact duplicates within this batch
    if AuditReport.objects.filter(
        batch=batch, file_name=record.file_name
    ).exists():
        logger.info("Duplicate skipped: %s", record.file_name)
        return False

    try:
        report = AuditReport.objects.create(
            batch                 = batch,
            file_name             = record.file_name,
            factory               = record.factory or "",
            factory_extracted     = record.factory_extracted or "",
            client                = record.client or "",
            client_extracted      = record.client_extracted or "",
            cross_check_warnings  = "\n".join(record.cross_check_warnings or []),
            date_of_issue         = batch.inspection_date,
            inspection_type       = record.inspection_type or "",
            report_no             = record.report_no or "",
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
            validation_errors     = "\n".join(record.validation_errors or []),
            blocking_errors       = "\n".join(record.blocking_errors or []),
            do_orders_json        = json.dumps(record.do_orders or []),
        )

        # Bulk-create defect entries
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
                report=report,
                category=cat,
                item=item,
                major=major,
                minor=minor,
                comment=comment,
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
    self,
    batch_id: int,
    upload_folder: str,
) -> dict:
    """
    Parameters
    ----------
    batch_id      : UploadBatch PK
    upload_folder : absolute path to the temp dir containing uploaded files

    Note: format_type and inspection_date are both loaded from the batch
    record — they are not passed as task arguments.
    """
    from final_summary.extraction.formats import get_extractor
    from final_summary.extraction.validation import run_validation
    from utils.sheet_resolver import resolve_sheet_name

    try:
        batch = UploadBatch.objects.select_related(
            "pair", "pair__buyer", "pair__factory"
        ).get(pk=batch_id)
    except UploadBatch.DoesNotExist:
        logger.error("Batch #%s not found", batch_id)
        return {"error": "Batch not found"}

    pair            = batch.pair
    inspection_date = batch.inspection_date
    extractor       = get_extractor(pair)

    logger.info(
        "Batch #%s | pair=%s | format=%s | date=%s",
        batch_id, pair, pair.report_type, inspection_date,
    )

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

        # ── Stage 1: Extract ──────────────────────────────────────────────
        extracted        = []
        extract_failures = []

        # ── Resolve target sheets per inspection type from the pair ──────
        target_reports = batch.pair.available_reports or ["FINAL", "RE_FINAL", "INLINE"]
        # Fallback if available_reports is empty
        if not target_reports:
            target_reports = ["FINAL", "RE_FINAL", "INLINE"]

        extracted        = []   # <-- already declared above, keep the list
        extract_failures = []   # <-- already declared above, keep the list

        import openpyxl

        for excel_path in excel_files:
            logger.debug("Processing file: %s", excel_path.name)
            logger.debug("  Full path: %s", excel_path)
            # Get actual sheet names from the workbook
            wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
            available_sheets = wb.sheetnames
            wb.close()

            # Find sheets that match the target inspection types (case‑insensitive)
            sheets_to_process = []
            for report_type in target_reports:
                # Many reports have sheet names like "Final", "Re-Final", "INLINE"
                match = next(
                    (s for s in available_sheets if s.lower() == report_type.lower()),
                    None,
                )
                if match:
                    sheets_to_process.append(match)

            # If no matching sheet found, fall back to the first sheet
            if not sheets_to_process:
                logger.warning("  No matching sheets found for %s", excel_path.name)
                logger.warning("    Available sheets: %s", available_sheets)
                sheets_to_process = [available_sheets[0]]

            for sheet_name in sheets_to_process:
                try:
                    logger.info("  -> Extracting %s sheet: '%s'", excel_path.name, sheet_name)
                    record = extractor.extract(
                        path=excel_path,
                        sheet_name=sheet_name,
                        inspection_date=inspection_date,
                        pair=pair,
                    )
                    # Make file_name unique per sheet so duplicates aren't skipped
                    record.file_name = f"{excel_path.name} ({sheet_name})"
                    extracted.append(record)
                except Exception as exc:
                    msg = f"{excel_path.name} ({sheet_name}): {exc}"
                    logger.exception("Extraction failed – %s", msg)
                    extract_failures.append(msg)

        # Update total after extraction — we now know exactly how many records
        batch.total_files = len(extracted)
        batch.save(update_fields=["total_files"])
        _push_progress(batch, stage="VALIDATING")

        # ── Stage 2: Validate ─────────────────────────────────────────────
        validated = run_validation(extracted)
        clean     = [r for r in validated if not r.blocking_errors]
        blocked   = [r for r in validated if r.blocking_errors]

        _push_progress(batch, stage="SAVING")

        # ── Stage 3: Save ─────────────────────────────────────────────────
        saved = 0
        for record in clean:
            if _save_record(batch, record):
                saved += 1
                batch.processed_files += 1
            else:
                batch.failed_files += 1
            batch.save(update_fields=["processed_files", "failed_files"])
            _push_progress(batch, stage="SAVING")

        # Save blocked records to DB so they can be downloaded / retried later.
        # They carry their blocking_errors but are not counted as "processed".
        for record in blocked:
            _save_record(batch, record)

        # Blocked + extract failures count as failed
        batch.failed_files += len(blocked) + len(extract_failures)
        batch.save(update_fields=["failed_files"])

        # ── Finalise status ───────────────────────────────────────────────
        if batch.failed_files == 0:
            batch.status = UploadBatch.Status.COMPLETED
        elif saved == 0:
            batch.status = UploadBatch.Status.FAILED
        else:
            batch.status = UploadBatch.Status.PARTIAL

        error_lines = list(extract_failures) + [
            f"{r.file_name}: {'; '.join(r.blocking_errors)}"
            for r in blocked
        ]
        if error_lines:
            batch.error_log = "\n".join(error_lines)

        batch.save(update_fields=["status", "error_log"])
        _push_complete(batch)

        logger.info(
            "Batch #%s done | saved=%d blocked=%d extract_fail=%d",
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