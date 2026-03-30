import logging
from pathlib import Path

from celery import shared_task
from django.conf import settings

from puma_summary.models import (
    BatchFailedPDF,
    InspectionBatch,
    InspectionReport,
    PONumber,
)
from services.builder import write_excel
from services.file_manager.copy_and_rename import copy_and_rename
from services.certificate import generate_all_certificates

logger = logging.getLogger(__name__)

# Stage labels — consumed by the WS consumer for UI display
STAGE_EXTRACTING = "EXTRACTING"
STAGE_SAVING     = "SAVING_TO_DB"
STAGE_EXCEL      = "BUILDING_EXCEL"
STAGE_DONE       = "DONE"


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_channel_layer():
    from channels.layers import get_channel_layer
    return get_channel_layer()


def _group_name(batch_id: int) -> str:
    return f"batch_{batch_id}"


async def _push(group: str, message: dict):
    """Fire-and-forget push to the channel layer group."""
    from asgiref.sync import async_to_sync
    layer = _get_channel_layer()
    async_to_sync(layer.group_send)(group, message)


def _push_progress(batch: InspectionBatch, stage: str = "", failed_count: int = 0):
    """Push an incremental progress event to all connected WS clients."""
    _push(_group_name(batch.pk), {
        "type":             "batch.progress",   # → consumer.batch_progress()
        "batch_id":         batch.pk,
        "status":           batch.status,
        "stage":            stage,
        "progress_percent": batch.progress_percent,
        "processed":        batch.processed_pdfs,
        "total":            batch.total_pdfs,
        "failed":           failed_count,
        "success_rate":     batch.success_rate,
    })


def _push_complete(batch: InspectionBatch):
    """
    Push the final summary event.
    Includes structured failed_details and excel_available flag.
    """
    from puma_summary.serializers import BatchFailedPDFSerializer

    excel_available = False
    if batch.excel_report_path:
        full = settings.BASE_DIR / "media" / batch.excel_report_path
        excel_available = full.exists()

    failed_qs      = batch.batch_failed_pdfs.all()
    failed_details = BatchFailedPDFSerializer(failed_qs, many=True).data

    _push(_group_name(batch.pk), {
        "type":            "batch.complete",    # → consumer.batch_complete()
        "batch_id":        batch.pk,
        "status":          batch.status,
        "progress_percent": 100,
        "processed":       batch.processed_pdfs,
        "total":           batch.total_pdfs,
        "failed":          failed_qs.count(),
        "success_rate":    batch.success_rate,
        "report_count":    batch.reports.count(),
        "failed_details":  list(failed_details),
        "excel_available": excel_available,
    })


def _push_error(batch: InspectionBatch, message: str):
    """Push a task-crash error event."""
    _push(_group_name(batch.pk), {
        "type":          "batch.error",         # → consumer.batch_error()
        "batch_id":      batch.pk,
        "status":        InspectionBatch.Status.FAILED,
        "error_message": message,
    })


def _save_failed_pdfs(batch: InspectionBatch, failures: list[tuple[str, str]]):
    """
    Persist structured failure rows.
    `failures` is a list of (filename, reason) tuples from the extractor.
    Also appends to the raw error_log for debugging.
    """
    if not failures:
        return

    BatchFailedPDF.objects.bulk_create(
        [BatchFailedPDF(batch=batch, filename=fn, reason=reason)
         for fn, reason in failures],
        ignore_conflicts=True,
    )

    raw_lines = "\n".join(f"{fn}: {reason}" for fn, reason in failures)
    if batch.error_log:
        batch.error_log += f"\n{raw_lines}"
    else:
        batch.error_log = raw_lines
    batch.save(update_fields=["error_log"])


def _build_excel(batch: InspectionBatch, records: list[dict], factory_code: str):
    """Write the Excel file and persist the relative path on the batch."""
    puma      = settings.PUMA_SETTINGS
    excel_dir = puma["OUTPUT_DIR"] / "excel" / str(batch.pk)
    excel_dir.mkdir(parents=True, exist_ok=True)

    safe_code      = (factory_code or "UNKNOWN").replace("/", "_")
    excel_filename = f"AQL_Inspection_Report_{safe_code}_{len(records)}_reports.xlsx"
    excel_path     = excel_dir / excel_filename

    write_excel(records, excel_path)

    batch.excel_report_path = str(
        excel_path.relative_to(settings.BASE_DIR / "media")
    )
    batch.save(update_fields=["excel_report_path"])
    return excel_path


# ─────────────────────────────────────────────────────────────────────────────
#  TASK 1 — PROCESS INSPECTION BATCH
#  Called by BatchUploadView after saving uploaded PDFs to disk.
# ─────────────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    queue="puma_summary",
    max_retries=2,
    soft_time_limit=1500,
    time_limit=1800,
    name="puma_summary.process_inspection_batch",
)
def process_inspection_batch(self, batch_id: int) -> dict:
    from services.extractor import extract_folder, extract_files
    """
    Full pipeline for one InspectionBatch:
      1. Extract data from every PDF in source_folder
      2. Save extracted records + PO numbers to DB
      3. Build Excel report to disk
      4. Push WebSocket events throughout

    Nothing is stored as DB blobs — only text fields + paths.
    Certificates are generated on-demand per report (see CertificateDownloadView).
    """
    try:
        batch = InspectionBatch.objects.get(pk=batch_id)
    except InspectionBatch.DoesNotExist:
        logger.error("Batch %s not found", batch_id)
        return {"error": "Batch not found"}

    try:
        # ── 1. EXTRACT ────────────────────────────────────────────────────
        batch.status = InspectionBatch.Status.PROCESSING
        batch.save(update_fields=["status"])
        _push_progress(batch, STAGE_EXTRACTING)

        folder          = Path(batch.source_folder)
        # extract_folder returns (records, failures)
        # failures: list of (filename, reason) tuples
        records, failures = extract_folder(folder)

        batch.total_pdfs  = len(records) + len(failures)
        batch.save(update_fields=["total_pdfs"])

        _save_failed_pdfs(batch, failures)

        if not records:
            raise ValueError(
                "No records could be extracted — check PDF contents and logs."
            )

        # ── 2. SAVE TO DB ─────────────────────────────────────────────────
        _push_progress(batch, STAGE_SAVING, failed_count=len(failures))

        factory_code       = records[0].get("factory_code", "")
        batch.factory_code = factory_code
        batch.save(update_fields=["factory_code"])

        report_objs = [
            InspectionReport(
                batch=batch,
                pdf_filename=r["pdf_filename"],
                inspection_date=r["inspection_date"] or None,
                style=r["style"],
                description=r["description"],
                sample_size=r["sample_size"],
                po_qty=r["po_qty"],
                actual_qty=r["actual_qty"],
                inspected_qty=r["inspected_qty"],
                major_defect=r["major_defect"],
                minor_defect=r["minor_defect"],
                factory_code=r["factory_code"],
                factory_name=r["factory_name"],
                final_customer=r["final_customer"],
            )
            for r in records
        ]
        created = InspectionReport.objects.bulk_create(report_objs)

        batch.processed_pdfs = len(created)
        batch.save(update_fields=["processed_pdfs"])

        _push_progress(batch, STAGE_SAVING, failed_count=len(failures))

        PONumber.objects.bulk_create(
            [
                PONumber(report=report, number=po)
                for report, rec in zip(created, records)
                for po in rec["po_numbers"]
            ],
            ignore_conflicts=True,
        )

        # ── 3. BUILD EXCEL ────────────────────────────────────────────────
        _push_progress(batch, STAGE_EXCEL, failed_count=len(failures))
        _build_excel(batch, records, factory_code)

        # ── 4. RENAME PDFs ────────────────────────────────────────────────
        puma = settings.PUMA_SETTINGS
        renamed_pdf_dir = puma["RENAMED_PDF_DIR"] / str(batch.pk)
        renamed_pdf_dir.mkdir(parents=True, exist_ok=True)

        for record in records:
            try:
                source_path = Path(batch.source_folder) / record["pdf_filename"]
                if source_path.exists():
                    copy_and_rename(source_path, record, renamed_pdf_dir)
            except Exception as exc:
                logger.warning("Failed to rename PDF %s: %s", record["pdf_filename"], exc)

        # ── 5. GENERATE CERTIFICATES ──────────────────────────────────────
        certificate_dir = puma["CERTIFICATE_DIR"] / str(batch.pk)
        certificate_dir.mkdir(parents=True, exist_ok=True)

        template_path = puma["CERTIFICATE_TEMPLATE_PATH"]
        if template_path.exists():
            cert_records = [
                {
                    "style": r["style"],
                    "inspection_date": r["inspection_date"],
                    "po_qty": r["po_qty"],
                    "actual_qty": r["actual_qty"],
                    "inspected_qty": r["inspected_qty"],
                    "factory_name": r["factory_name"],
                    "factory_code": r["factory_code"],
                    "final_customer": r["final_customer"],
                    "po_numbers": r["po_numbers"],
                }
                for r in records
            ]
            generate_all_certificates(cert_records, template_path, certificate_dir)
        else:
            logger.warning("Certificate template not found at %s", template_path)

        # ── 6. FINALISE ───────────────────────────────────────────────────
        batch.status = (
            InspectionBatch.Status.PARTIAL
            if failures
            else InspectionBatch.Status.COMPLETED
        )
        batch.save(update_fields=["status"])

        _push_complete(batch)

        logger.info(
            "Batch #%s done — %d saved, %d failed.",
            batch_id, len(records), len(failures),
        )
        return {
            "batch_id":  batch_id,
            "status":    batch.status,
            "processed": len(records),
            "failed":    len(failures),
        }

    except Exception as exc:
        # Mark failed + push error event before retrying
        try:
            batch.status    = InspectionBatch.Status.FAILED
            batch.error_log = (batch.error_log or "") + f"\n[TASK CRASH] {exc}"
            batch.save(update_fields=["status", "error_log"])
            _push_error(batch, str(exc))
        except Exception:
            pass  # don't mask the original exception

        logger.exception("Batch #%s FAILED: %s", batch_id, exc)
        raise self.retry(exc=exc, countdown=60)


# ─────────────────────────────────────────────────────────────────────────────
#  TASK 2 — RETRY FAILED PDFS
#  Called by BatchRetryView.
#  Re-processes only the filenames passed in — does NOT touch successful rows.
# ─────────────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    queue="puma_summary",
    max_retries=2,
    soft_time_limit=900,
    time_limit=1200,
    name="puma_summary.retry_failed_pdfs",
)
def retry_failed_pdfs(self, batch_id: int, filenames: list[str]) -> dict:
    """
    Re-extract and re-save only the specified failed PDF filenames.

    Steps:
      1. Locate each file in batch.source_folder
      2. Re-extract with extract_files()  (subset version of extract_folder)
      3. Save new InspectionReport + PONumber rows
      4. Mark BatchFailedPDF rows as retried=True for successes
      5. Rebuild the Excel report to include the newly recovered records
      6. Push WebSocket events throughout
    """
    try:
        batch = (
            InspectionBatch.objects
            .prefetch_related("batch_failed_pdfs", "reports")
            .get(pk=batch_id)
        )
    except InspectionBatch.DoesNotExist:
        logger.error("Retry — Batch #%s not found", batch_id)
        return {"error": "Batch not found"}

    try:
        batch.status = InspectionBatch.Status.PROCESSING
        batch.save(update_fields=["status"])
        _push_progress(batch, STAGE_EXTRACTING)

        folder     = Path(batch.source_folder)
        pdf_paths  = [folder / fn for fn in filenames if (folder / fn).exists()]
        missing    = [fn for fn in filenames if not (folder / fn).exists()]

        if missing:
            logger.warning(
                "Retry Batch #%s — %d files not found on disk: %s",
                batch_id, len(missing), missing,
            )

        # ── 1. EXTRACT ONLY THE REQUESTED FILES ───────────────────────────
        # extract_files() is a subset helper — same interface as extract_folder
        # but accepts an explicit list of Path objects instead of a directory.
        records, new_failures = extract_files(pdf_paths)

        # Files that were on disk but still failed
        new_failure_names = {fn for fn, _ in new_failures}

        # Files that are now recovered
        recovered_names = {
            r["pdf_filename"] for r in records
        }

        _push_progress(batch, STAGE_SAVING, failed_count=len(new_failures))

        # ── 2. SAVE NEW REPORTS ───────────────────────────────────────────
        report_objs = [
            InspectionReport(
                batch=batch,
                pdf_filename=r["pdf_filename"],
                inspection_date=r["inspection_date"] or None,
                style=r["style"],
                description=r["description"],
                sample_size=r["sample_size"],
                po_qty=r["po_qty"],
                actual_qty=r["actual_qty"],
                inspected_qty=r["inspected_qty"],
                major_defect=r["major_defect"],
                minor_defect=r["minor_defect"],
                factory_code=r["factory_code"],
                factory_name=r["factory_name"],
                final_customer=r["final_customer"],
            )
            for r in records
        ]
        created = InspectionReport.objects.bulk_create(report_objs)

        PONumber.objects.bulk_create(
            [
                PONumber(report=report, number=po)
                for report, rec in zip(created, records)
                for po in rec["po_numbers"]
            ],
            ignore_conflicts=True,
        )

        # ── 3. UPDATE COUNTERS ────────────────────────────────────────────
        batch.processed_pdfs += len(created)
        batch.batch_failed_pdfs.filter(filename__in=recovered_names).update(retried=True)

        # Persist new structured failure rows for files that still fail
        _save_failed_pdfs(batch, new_failures)

        batch.save(update_fields=["processed_pdfs"])
        _push_progress(batch, STAGE_SAVING, failed_count=len(new_failures))

        # ── 4. REBUILD EXCEL ──────────────────────────────────────────────
        # Collect ALL records for this batch (original + newly recovered)
        _push_progress(batch, STAGE_EXCEL, failed_count=len(new_failures))

        all_reports = batch.reports.prefetch_related("po_numbers").all()
        all_records = [
            {
                "pdf_filename":    rpt.pdf_filename,
                "inspection_date": str(rpt.inspection_date or ""),
                "style":           rpt.style,
                "description":     rpt.description,
                "sample_size":     rpt.sample_size,
                "po_qty":          rpt.po_qty,
                "actual_qty":      rpt.actual_qty,
                "inspected_qty":   rpt.inspected_qty,
                "major_defect":    rpt.major_defect,
                "minor_defect":    rpt.minor_defect,
                "factory_code":    rpt.factory_code,
                "factory_name":    rpt.factory_name,
                "final_customer":  rpt.final_customer,
                "po_numbers":      list(
                    rpt.po_numbers.values_list("number", flat=True)
                ),
            }
            for rpt in all_reports
        ]

        factory_code = batch.factory_code or (
            all_records[0]["factory_code"] if all_records else "UNKNOWN"
        )
        _build_excel(batch, all_records, factory_code)

        # ── 5. RENAME PDFs ────────────────────────────────────────────────
        puma = settings.PUMA_SETTINGS
        renamed_pdf_dir = puma["RENAMED_PDF_DIR"] / str(batch.pk)
        renamed_pdf_dir.mkdir(parents=True, exist_ok=True)

        for record in all_records:
            try:
                source_path = Path(batch.source_folder) / record["pdf_filename"]
                if source_path.exists():
                    copy_and_rename(source_path, record, renamed_pdf_dir)
            except Exception as exc:
                logger.warning("Failed to rename PDF %s: %s", record["pdf_filename"], exc)

        # ── 6. GENERATE CERTIFICATES ──────────────────────────────────────
        certificate_dir = puma["CERTIFICATE_DIR"] / str(batch.pk)
        certificate_dir.mkdir(parents=True, exist_ok=True)

        template_path = puma["CERTIFICATE_TEMPLATE_PATH"]
        if template_path.exists():
            cert_records = [
                {
                    "style": r["style"],
                    "inspection_date": r["inspection_date"],
                    "po_qty": r["po_qty"],
                    "actual_qty": r["actual_qty"],
                    "inspected_qty": r["inspected_qty"],
                    "factory_name": r["factory_name"],
                    "factory_code": r["factory_code"],
                    "final_customer": r["final_customer"],
                    "po_numbers": r["po_numbers"],
                }
                for r in all_records
            ]
            generate_all_certificates(cert_records, template_path, certificate_dir)
        else:
            logger.warning("Certificate template not found at %s", template_path)

        # ── 7. FINALISE ───────────────────────────────────────────────────
        still_unretried = batch.batch_failed_pdfs.filter(retried=False).exists()
        batch.status = (
            InspectionBatch.Status.PARTIAL
            if still_unretried or missing
            else InspectionBatch.Status.COMPLETED
        )
        batch.save(update_fields=["status"])

        _push_complete(batch)

        logger.info(
            "Retry Batch #%s done — recovered: %d, still failed: %d, missing: %d",
            batch_id, len(created), len(new_failures), len(missing),
        )
        return {
            "batch_id":  batch_id,
            "status":    batch.status,
            "recovered": len(created),
            "failed":    len(new_failures),
            "missing":   len(missing),
        }

    except Exception as exc:
        try:
            batch.status     = InspectionBatch.Status.FAILED
            batch.error_log += f"\n[RETRY CRASH] {exc}"
            batch.save(update_fields=["status", "error_log"])
            _push_error(batch, str(exc))
        except Exception:
            pass

        logger.exception("Retry Batch #%s FAILED: %s", batch_id, exc)
        raise self.retry(exc=exc, countdown=60)