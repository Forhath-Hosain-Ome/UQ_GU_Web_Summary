import logging
from pathlib import Path

from celery import shared_task
from django.conf import settings

from puma_summary.models import (
    BatchFailedPDF,
    CertificateLog,
    InspectionBatch,
    InspectionReport,
    PONumber,
)
from services.builder import write_excel
from services.file_manager.copy_and_rename import copy_and_rename
from services.certificate import generate_certificate

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


def _push(group: str, message: dict):
    """Fire-and-forget push to the channel layer group."""
    from asgiref.sync import async_to_sync
    layer = _get_channel_layer()
    async_to_sync(layer.group_send)(group, message)


def _push_progress(batch: InspectionBatch, stage: str = "", failed_count: int = 0):
    """Push an incremental progress event to all connected WS clients."""
    _push(_group_name(batch.pk), {
        "type":             "batch.progress",
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
    """Push the final summary event."""
    from puma_summary.serializers import BatchFailedPDFSerializer

    excel_available = False
    if batch.excel_report_path:
        full = settings.BASE_DIR / "media" / batch.excel_report_path
        excel_available = full.exists()

    failed_qs      = batch.batch_failed_pdfs.all()
    failed_details = BatchFailedPDFSerializer(failed_qs, many=True).data

    _push(_group_name(batch.pk), {
        "type":             "batch.complete",
        "batch_id":         batch.pk,
        "status":           batch.status,
        "progress_percent": 100,
        "processed":        batch.processed_pdfs,
        "total":            batch.total_pdfs,
        "failed":           batch.failed_pdfs,          # integer field
        "success_rate":     batch.success_rate,
        "report_count":     batch.reports.count(),
        "failed_details":   list(failed_details),
        "excel_available":  excel_available,
    })


def _push_error(batch: InspectionBatch, message: str):
    """Push a task-crash error event."""
    _push(_group_name(batch.pk), {
        "type":          "batch.error",
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
    batch.error_log = (batch.error_log + f"\n{raw_lines}") if batch.error_log else raw_lines
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


def _generate_cert_for_report(
    report: InspectionReport,
    template_path: Path,
    cert_dir: Path,
    username: str,
) -> None:
    """
    Generate a DOCX certificate for a single InspectionReport and log the event.
    Silently logs errors — a cert failure must never block the main pipeline.
    """
    record = {
        "style":           report.style,
        "inspection_date": str(report.inspection_date or ""),
        "report_date":     str(report.report_date),
        "po_qty":          report.po_qty,
        "actual_qty":      report.actual_qty,
        "inspected_qty":   report.inspected_qty,
        "factory_name":    report.factory_name,
        "factory_code":    report.factory_code,
        "final_customer":  report.final_customer,
        "po_numbers":      list(report.po_numbers.values_list("number", flat=True)),
    }
    try:
        generate_certificate(record, template_path, cert_dir)
        CertificateLog.objects.create(
            report=report,
            generated_by=username,
        )
        logger.info("Certificate generated for report #%s (%s)", report.pk, report.style)
    except Exception as exc:
        logger.error(
            "Certificate generation failed for report #%s (%s): %s",
            report.pk, report.style, exc,
        )


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
    from services.extractor import extract_folder

    """
    Full pipeline for one InspectionBatch:
      1. Extract data from every PDF in source_folder
      2. Save each extracted report + PO numbers to DB
      3. Generate a DOCX certificate per report immediately after saving
      4. Rename each PDF in-place in source_folder
      5. Build Excel report to disk
      6. Push WebSocket events throughout

    report_date is auto-set by the model default (today's date) — no
    manual assignment needed here.
    """
    try:
        batch = InspectionBatch.objects.select_related("created_by").get(pk=batch_id)
    except InspectionBatch.DoesNotExist:
        logger.error("Batch %s not found", batch_id)
        return {"error": "Batch not found"}

    username = batch.created_by.username if batch.created_by_id else "system"
    puma     = settings.PUMA_SETTINGS

    try:
        # ── 1. EXTRACT ────────────────────────────────────────────────────
        batch.status = InspectionBatch.Status.PROCESSING
        batch.save(update_fields=["status"])

        folder            = Path(batch.source_folder)
        records, failures = extract_folder(folder)

        # BUG FIX: set total_pdfs BEFORE the first _push_progress call.
        # Previously the push fired while total_pdfs was still 0 (it hadn't
        # been written to the DB yet), so the WebSocket event told the
        # frontend "0/0" and overwrote the correct value from the HTTP response.
        batch.total_pdfs = len(records) + len(failures)
        batch.save(update_fields=["total_pdfs"])

        _push_progress(batch, STAGE_EXTRACTING)

        _save_failed_pdfs(batch, failures)

        if not records:
            raise ValueError(
                "No records could be extracted — check PDF contents and logs."
            )

        # ── 2. SAVE TO DB + CERT PER PDF ──────────────────────────────────
        _push_progress(batch, STAGE_SAVING, failed_count=len(failures))

        factory_code       = records[0].get("factory_code", "")
        batch.factory_code = factory_code
        batch.save(update_fields=["factory_code"])

        # Certificate output dir for this batch
        cert_dir = puma.get("CERTIFICATE_DIR", settings.BASE_DIR / "media" / "certificates") / str(batch.pk)
        cert_dir.mkdir(parents=True, exist_ok=True)
        template_path = Path(puma["CERTIFICATE_TEMPLATE_PATH"])
        certs_enabled = template_path.exists()
        if not certs_enabled:
            logger.warning("Certificate template not found at %s — skipping cert generation", template_path)

        # BUG FIX: renamed PDFs must land in the dedicated output directory,
        # not back into the uploads source folder.  Previously copy_and_rename
        # was called with `folder` (the uploads dir) as output_dir, which means
        # the renamed file was written alongside the originals and never reached
        # media/output/puma/renamed_pdfs/{batch_id}/.
        renamed_pdf_dir = puma["OUTPUT_DIR"] / "renamed_pdfs" / str(batch.pk)
        renamed_pdf_dir.mkdir(parents=True, exist_ok=True)

        saved_reports = []
        for r in records:
            # report_date is set automatically by the model's default=timezone.localdate
            report = InspectionReport.objects.create(
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

            # Save PO numbers
            PONumber.objects.bulk_create(
                [PONumber(report=report, number=po) for po in r["po_numbers"]],
                ignore_conflicts=True,
            )

            # Generate certificate immediately after this report is persisted
            if certs_enabled:
                _generate_cert_for_report(report, template_path, cert_dir, username)

            saved_reports.append(report)

            # Copy source PDF to the renamed_pdfs output directory with the
            # standardised filename, then delete the original from uploads.
            source_path = folder / r["pdf_filename"]
            if source_path.exists():
                try:
                    copy_and_rename(source_path, r, renamed_pdf_dir)
                except Exception as exc:
                    logger.warning("Failed to rename PDF %s: %s", r["pdf_filename"], exc)

        batch.processed_pdfs = len(saved_reports)
        batch.save(update_fields=["processed_pdfs"])
        _push_progress(batch, STAGE_SAVING, failed_count=len(failures))

        # ── 3. BUILD EXCEL ────────────────────────────────────────────────
        _push_progress(batch, STAGE_EXCEL, failed_count=len(failures))
        _build_excel(batch, records, factory_code)

        # ── 4. FINALISE ───────────────────────────────────────────────────
        batch.status = (
            InspectionBatch.Status.PARTIAL
            if failures
            else InspectionBatch.Status.COMPLETED
        )
        batch.save(update_fields=["status"])

        _push_complete(batch)

        logger.info(
            "Batch #%s done — %d saved, %d failed.",
            batch_id, len(saved_reports), len(failures),
        )
        return {
            "batch_id":  batch_id,
            "status":    batch.status,
            "processed": len(saved_reports),
            "failed":    len(failures),
        }

    except Exception as exc:
        try:
            batch.status    = InspectionBatch.Status.FAILED
            batch.error_log = (batch.error_log or "") + f"\n[TASK CRASH] {exc}"
            batch.save(update_fields=["status", "error_log"])
            _push_error(batch, str(exc))
        except Exception:
            pass

        logger.exception("Batch #%s FAILED: %s", batch_id, exc)
        raise self.retry(exc=exc, countdown=60)


# ─────────────────────────────────────────────────────────────────────────────
#  TASK 2 — RETRY FAILED PDFS
#  Called by BatchRetryView with a specific list of filenames.
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
      2. Re-extract with extract_files()
      3. Save new InspectionReport + PONumber rows
      4. Generate certificate per recovered report
      5. Rename recovered PDFs in-place
      6. Mark BatchFailedPDF rows as retried=True for successes
      7. Rebuild the Excel report to include all recovered records
      8. Push WebSocket events throughout
    """
    from services.extractor import extract_files

    try:
        batch = (
            InspectionBatch.objects
            .select_related("created_by")
            .prefetch_related("batch_failed_pdfs", "reports")
            .get(pk=batch_id)
        )
    except InspectionBatch.DoesNotExist:
        logger.error("Retry — Batch #%s not found", batch_id)
        return {"error": "Batch not found"}

    username = batch.created_by.username if batch.created_by_id else "system"
    puma     = settings.PUMA_SETTINGS

    try:
        batch.status = InspectionBatch.Status.PROCESSING
        batch.save(update_fields=["status"])
        _push_progress(batch, STAGE_EXTRACTING)

        folder    = Path(batch.source_folder)
        pdf_paths = [folder / fn for fn in filenames if (folder / fn).exists()]
        missing   = [fn for fn in filenames if not (folder / fn).exists()]

        if missing:
            logger.warning(
                "Retry Batch #%s — %d files not found on disk: %s",
                batch_id, len(missing), missing,
            )

        # ── 1. EXTRACT ────────────────────────────────────────────────────
        records, new_failures = extract_files(pdf_paths)
        recovered_names = {r["pdf_filename"] for r in records}

        _push_progress(batch, STAGE_SAVING, failed_count=len(new_failures))

        # ── 2. SAVE + CERT PER RECOVERED PDF ─────────────────────────────
        cert_dir = puma.get("CERTIFICATE_DIR", settings.BASE_DIR / "media" / "certificates") / str(batch.pk)
        cert_dir.mkdir(parents=True, exist_ok=True)
        template_path = Path(puma["CERTIFICATE_TEMPLATE_PATH"])
        certs_enabled = template_path.exists()

        # BUG FIX: same as the main task — output to renamed_pdfs dir, not back
        # into the uploads source folder.
        renamed_pdf_dir = puma["OUTPUT_DIR"] / "renamed_pdfs" / str(batch.pk)
        renamed_pdf_dir.mkdir(parents=True, exist_ok=True)

        saved_reports = []
        for r in records:
            report = InspectionReport.objects.create(
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

            PONumber.objects.bulk_create(
                [PONumber(report=report, number=po) for po in r["po_numbers"]],
                ignore_conflicts=True,
            )

            if certs_enabled:
                _generate_cert_for_report(report, template_path, cert_dir, username)

            saved_reports.append(report)

            # Rename recovered PDF into the correct output directory
            source_path = folder / r["pdf_filename"]
            if source_path.exists():
                try:
                    copy_and_rename(source_path, r, renamed_pdf_dir)
                except Exception as exc:
                    logger.warning("Failed to rename PDF %s: %s", r["pdf_filename"], exc)

        # ── 3. UPDATE COUNTERS + FAILURE RECORDS ─────────────────────────
        batch.processed_pdfs += len(saved_reports)
        batch.batch_failed_pdfs.filter(filename__in=recovered_names).update(retried=True)
        _save_failed_pdfs(batch, new_failures)
        batch.save(update_fields=["processed_pdfs"])
        _push_progress(batch, STAGE_SAVING, failed_count=len(new_failures))

        # ── 4. REBUILD EXCEL (all reports for this batch) ─────────────────
        _push_progress(batch, STAGE_EXCEL, failed_count=len(new_failures))

        all_reports  = batch.reports.prefetch_related("po_numbers").all()
        all_records  = [
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
                "po_numbers":      list(rpt.po_numbers.values_list("number", flat=True)),
            }
            for rpt in all_reports
        ]

        factory_code = batch.factory_code or (
            all_records[0]["factory_code"] if all_records else "UNKNOWN"
        )
        _build_excel(batch, all_records, factory_code)

        # ── 5. FINALISE ───────────────────────────────────────────────────
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
            batch_id, len(saved_reports), len(new_failures), len(missing),
        )
        return {
            "batch_id":  batch_id,
            "status":    batch.status,
            "recovered": len(saved_reports),
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