"""
top5/tasks.py
--------------
Celery task that runs the Excel extraction + template fill in the background.

Since the result is a file download (not stored persistently), we return
the output bytes via the Celery result backend so the view can stream them.

Flow
----
1. View receives upload → creates Top5Job(status=PENDING) → fires task → returns job_id
2. Frontend polls GET /top5/jobs/<pk>/ until status=DONE or FAILED
3. On DONE, frontend hits GET /top5/jobs/<pk>/download/ to get the file
4. Task stores result bytes in Django cache (keyed by job pk) for 5 minutes
"""
import logging
import asyncio
from pathlib import Path
from django.conf import settings

from celery import shared_task
from django.core.cache import cache
from top_five.models import Top5Job
from services.top_five_extractor import process

logger = logging.getLogger(__name__)

top_five     = settings.TOP_FIVE_SETTINGS

# Template lives at  <django_project_root>/top5/template/template.xlsx
TEMPLATE_PATH = Path(top_five["TOP_FIVE_TEMPLATE_PATH"])

CACHE_TTL = 5 * 60  # seconds — result held in cache for 5 min


def _send_progress(job_pk, status, stage="", progress_percent=0):
    """Send progress update via WebSocket."""
    try:
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        group_name = f"top5_job_{job_pk}"
        event = {
            "type": "top5_progress",
            "job_id": job_pk,
            "status": status,
            "stage": stage,
            "progress_percent": progress_percent,
        }
        # Use run_until_complete with error handling
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(channel_layer.group_send(group_name, event))
        finally:
            loop.close()
    except Exception as exc:
        logger.warning("Failed to send WebSocket progress update: %s", exc)


def _send_complete(job_pk, status):
    """Send completion notification via WebSocket."""
    try:
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        group_name = f"top5_job_{job_pk}"
        event = {
            "type": "top5_complete",
            "job_id": job_pk,
            "status": status,
        }
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(channel_layer.group_send(group_name, event))
        finally:
            loop.close()
    except Exception as exc:
        logger.warning("Failed to send WebSocket complete notification: %s", exc)


def _send_error(job_pk, error_message):
    """Send error notification via WebSocket."""
    try:
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        group_name = f"top5_job_{job_pk}"
        event = {
            "type": "top5_error",
            "job_id": job_pk,
            "error_message": error_message,
        }
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(channel_layer.group_send(group_name, event))
        finally:
            loop.close()
    except Exception as exc:
        logger.warning("Failed to send WebSocket error notification: %s", exc)


@shared_task(bind=True, max_retries=0, time_limit=600, soft_time_limit=550)
def run_top5_job(self, job_pk, file_bytes_hex, original_filename):
    """
    Celery task to process Top5 Excel upload.
    
    Parameters
    ----------
    job_pk : int
        Top5Job database record ID
    file_bytes_hex : str
        Uploaded file bytes as hex string (Celery JSON serializer limitation)
    original_filename : str
        Original uploaded filename for logging
    """
    try:
        # Fetch job record
        job = Top5Job.objects.get(pk=job_pk)
        job.status = Top5Job.Status.PROCESSING
        job.save(update_fields=["status", "updated_at"])
        _send_progress(job_pk, job.status, "Processing", 10)

        # Validate template exists
        if not TEMPLATE_PATH.exists():
            raise FileNotFoundError(
                f"Template not found at {TEMPLATE_PATH}. "
                "Ensure TOP_FIVE_TEMPLATE_PATH is correctly configured in settings."
            )

        # Convert hex string back to bytes and extract data
        file_bytes = bytes.fromhex(file_bytes_hex)
        _send_progress(job_pk, job.status, "Extracting data", 30)
        
        result_buf = process(file_bytes, TEMPLATE_PATH)
        _send_progress(job_pk, job.status, "Generating report", 70)

        # Store result in cache for 5 minutes (download view retrieves it)
        cache_key = f"top5_result_{job_pk}"
        cache.set(cache_key, result_buf.getvalue(), timeout=CACHE_TTL)

        # Mark job as completed
        job.status = Top5Job.Status.DONE
        job.save(update_fields=["status", "updated_at"])
        _send_complete(job_pk, job.status)

        logger.info("✓ top5 job #%s completed — file: %s", job_pk, original_filename)

    except Exception as exc:
        logger.exception("✗ top5 job #%s failed — file: %s — error: %s", job_pk, original_filename, exc)
        try:
            job = Top5Job.objects.get(pk=job_pk)
            job.status = Top5Job.Status.FAILED
            job.error = str(exc)[:500]  # Truncate error message to 500 chars
            job.save(update_fields=["status", "error", "updated_at"])
            _send_error(job_pk, str(exc))
        except Exception as db_error:
            logger.error("Failed to update job status in DB: %s", db_error)