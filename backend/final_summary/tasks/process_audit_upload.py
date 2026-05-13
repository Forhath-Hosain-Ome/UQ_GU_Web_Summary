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
import openpyxl
import json
import logging
import shutil
from pathlib import Path

from celery import shared_task
from django.utils.dateparse import parse_date
from final_summary.models import UploadBatch, AuditReport, DefectEntry

from final_summary.extraction.core import get_sheet_names
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

# ── Excel Convert ─────────────────────────────────────────────────────────────

def _convert_xls_to_xlsx(xls_path: Path) -> Path:
    """
    Convert .xls to .xlsx in the same temp folder.
    Returns the path to the converted .xlsx file.
    """
    import xlrd
    from xlrd import xldate_as_datetime

    xlsx_path = xls_path.with_suffix(".xlsx")
    xls_wb    = xlrd.open_workbook(str(xls_path), formatting_info=False)
    xlsx_wb   = openpyxl.Workbook()
    xlsx_wb.remove(xlsx_wb.active)  # remove default blank sheet

    for sheet_idx in range(xls_wb.nsheets):
        xls_ws  = xls_wb.sheet_by_index(sheet_idx)
        xlsx_ws = xlsx_wb.create_sheet(title=xls_ws.name)
        for row_idx in range(xls_ws.nrows):
            for col_idx in range(xls_ws.ncols):
                cell = xls_ws.cell(row_idx, col_idx)
                if cell.ctype == xlrd.XL_CELL_DATE:
                    value = xldate_as_datetime(cell.value, xls_wb.datemode)
                else:
                    value = cell.value
                xlsx_ws.cell(row=row_idx + 1, column=col_idx + 1).value = value

    xlsx_wb.save(str(xlsx_path))
    xls_wb.release_resources()
    logger.info("Converted %s → %s", xls_path.name, xlsx_path.name)
    return xlsx_path
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

        # ── Bulk-create defect entries ─────────────────────────────────────
        # defect_rows come pre-enriched from defects.py with:
        #   item_no, category_code, category (label), item (canonical name)
        # We combine code + label into the single `category` field the
        # flat DefectEntry model expects: e.g. "A - Fabrics", "B - Sewing"
        defect_objects = []
        for d in (record.defect_rows or []):
            if not isinstance(d, dict):
                continue

            major   = int(d.get("major",   0) or 0)
            minor   = int(d.get("minor",   0) or 0)
            comment = str(d.get("comment") or "").strip()

            # Skip completely empty rows
            if not major and not minor and not comment:
                continue

            code  = str(d.get("category_code") or "").strip()
            label = str(d.get("category")      or "").strip()

            # Build combined category: "A - Fabrics", fall back gracefully
            if code and label:
                category = f"{code} - {label}"
            elif code:
                category = code
            else:
                category = label

            defect_objects.append(DefectEntry(
                report      = report,
                serial      = int(d.get("item_no", 0) or 0),
                category    = category,
                defect_name = str(d.get("item") or "").strip(),
                major       = major,
                minor       = minor,
                comment     = comment,
            ))

        if defect_objects:
            DefectEntry.objects.bulk_create(defect_objects)
            logger.debug(
                "Saved %d defect entries for report #%s (%s)",
                len(defect_objects), report.pk, record.file_name,
            )
        else:
            logger.debug(
                "No defect entries to save for report #%s (%s)",
                report.pk, record.file_name,
            )

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
        if not target_reports:
            target_reports = ["FINAL", "RE_FINAL", "INLINE"]

        for excel_path in excel_files:
            logger.debug("Processing file: %s", excel_path.name)
            logger.debug("  Full path: %s", excel_path)

            # Convert .xls → .xlsx so the extractor always receives .xlsx
            actual_path = excel_path
            if excel_path.suffix.lower() == ".xls":
                try:
                    actual_path = _convert_xls_to_xlsx(excel_path)
                except Exception as exc:
                    msg = f"{excel_path.name}: failed to convert .xls to .xlsx: {exc}"
                    logger.exception("XLS conversion failed – %s", msg)
                    extract_failures.append(msg)
                    continue

            available_sheets = get_sheet_names(actual_path)  # your existing function
            if not available_sheets:
                extract_failures.append(f"{excel_path.name}: no sheets found")
                continue

            sheets_to_process = []
            for report_type in target_reports:
                match = next(
                    (s for s in available_sheets if s.lower() == report_type.lower()),
                    None,
                )
                if match:
                    sheets_to_process.append(match)

            if not sheets_to_process:
                logger.warning("  No matching sheets found for %s", excel_path.name)
                logger.warning("    Available sheets: %s", available_sheets)
                sheets_to_process = [available_sheets[0]]

            # ... rest of your existing sheet matching logic unchanged ...
            for sheet_name in sheets_to_process:
                try:
                    record = extractor.extract(
                        path=actual_path,          # always .xlsx at this point
                        sheet_name=sheet_name,
                        inspection_date=inspection_date,
                        pair=pair,
                    )
                    record.file_name = f"{excel_path.name} ({sheet_name})"  # original name
                    extracted.append(record)
                except Exception as exc:
                    msg = f"{excel_path.name} ({sheet_name}): {exc}"
                    logger.exception("Extraction failed – %s", msg)
                    extract_failures.append(msg)

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

        for record in blocked:
            _save_record(batch, record)

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