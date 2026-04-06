import logging
from pathlib import Path

from celery import shared_task

from ..utils.config import DB_PATH, ensure_app_dir
from ..db.db_manager import DBManager
from ..helpers.extractor_service import extract_record
from ..helpers.validator import validate_all_records, validate_blocking_all

logger = logging.getLogger(__name__)


@shared_task(name="final_summary.process_excel_upload")
def process_excel_upload(upload_folder: str) -> dict:
    upload_path = Path(upload_folder)
    if not upload_path.exists() or not upload_path.is_dir():
        logger.error("Excel upload folder not found: %s", upload_folder)
        return {"status": "error", "message": "Upload folder not found."}

    ensure_app_dir()
    db = DBManager(DB_PATH)
    db.connect()
    db.init_db()

    excel_files = sorted(upload_path.glob("*.xlsx")) + sorted(upload_path.glob("*.xls"))
    processed = 0
    failed = []
    extracted_records = []

    for excel_path in excel_files:
        try:
            record = extract_record(excel_path)
            extracted_records.append(record)
            processed += 1
        except Exception as exc:
            logger.exception("Failed to extract Excel file %s: %s", excel_path, exc)
            failed.append({"file": excel_path.name, "error": str(exc)})

    validated_records = validate_all_records(extracted_records)
    validated_records = validate_blocking_all(validated_records)

    clean_records = [r for r in validated_records if not r.blocking_errors]
    blocked_records = [r for r in validated_records if r.blocking_errors]

    saved = 0
    skipped = 0
    for record in clean_records:
        result = db.save_record(record)
        if result is None:
            skipped += 1
        else:
            saved += 1

    blocked_data = None
    if blocked_records:
        blocked_data = [r.to_json_dict() for r in blocked_records]
        logger.info("Blocked records prepared for response: %d records", len(blocked_records))

    db.close()

    result = {
        "status": "completed",
        "upload_folder": upload_path.name,
        "processed_files": processed,
        "saved_records": saved,
        "skipped_records": skipped,
        "blocked_records_count": len(blocked_records),
        "failed_files": failed,
    }
    if blocked_data:
        result["blocked_records"] = blocked_data

    return result
