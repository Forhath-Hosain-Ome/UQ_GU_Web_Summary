# backend/image_processor/tasks/cleanup_task.py
"""
Periodic Celery task that removes stale temporary directories.

Runs every 24 hours via Celery Beat.  Cleans up:
  1. /tmp/batch_uploads/<uuid>/   — upload staging dirs created by FolderUploadView
  2. <OUTPUT_DIR>/<batch_id>/     — DOCX output dirs created by the processing task

Both are deleted if they are older than MAX_AGE_HOURS (default 24 h).
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)

# ── Tuneable constants ────────────────────────────────────────────────────────
MAX_AGE_HOURS   = 24
MAX_AGE_SECONDS = MAX_AGE_HOURS * 3600


def _dir_age_seconds(path: Path) -> float:
    """Return how many seconds ago the directory was last modified."""
    try:
        return time.time() - path.stat().st_mtime
    except OSError:
        return 0.0


def _remove_dir(path: Path) -> None:
    """Delete a directory tree, logging the outcome."""
    try:
        shutil.rmtree(path)
        logger.info("Cleanup: removed %s", path)
    except Exception as exc:
        logger.warning("Cleanup: failed to remove %s — %s", path, exc)


def _clean_directory(parent: Path, label: str) -> dict:
    """
    Iterate immediate children of `parent`.
    Delete any subdirectory older than MAX_AGE_SECONDS.
    Returns a summary dict.
    """
    removed = 0
    skipped = 0
    errors  = 0

    if not parent.exists():
        logger.debug("Cleanup: %s dir does not exist — skipping (%s)", label, parent)
        return {"removed": 0, "skipped": 0, "errors": 0}

    for child in parent.iterdir():
        if not child.is_dir():
            continue
        age = _dir_age_seconds(child)
        if age >= MAX_AGE_SECONDS:
            try:
                _remove_dir(child)
                removed += 1
            except Exception:
                errors += 1
        else:
            skipped += 1

    logger.info(
        "Cleanup [%s]: removed=%d  skipped=%d  errors=%d",
        label, removed, skipped, errors,
    )
    return {"removed": removed, "skipped": skipped, "errors": errors}


# ── Celery task ───────────────────────────────────────────────────────────────

@shared_task(
    name="image_processor.cleanup_temp_dirs",
    max_retries=0,           # never retry a cleanup task
    ignore_result=True,
)
def cleanup_temp_dirs_task() -> None:
    """
    Delete upload staging dirs and DOCX output dirs older than 24 hours.

    Scheduled automatically via CELERYBEAT_SCHEDULE in settings.
    """
    logger.info("cleanup_temp_dirs_task: starting")

    # 1. Upload staging dirs  →  /tmp/batch_uploads/<uuid>/
    upload_parent = Path("/tmp") / "batch_uploads"
    upload_result = _clean_directory(upload_parent, "upload_staging")

    # 2. DOCX output dirs  →  OUTPUT_DIR/<batch_id>/
    image_settings = getattr(settings, "IMAGE_PROCESSOR_SETTINGS", {})
    output_dir = Path(
        image_settings.get(
            "OUTPUT_DIR",
            settings.BASE_DIR / "media" / "output" / "defect_image",
        )
    )
    output_result = _clean_directory(output_dir, "docx_output")

    logger.info(
        "cleanup_temp_dirs_task: done — "
        "upload[removed=%d] output[removed=%d]",
        upload_result["removed"],
        output_result["removed"],
    )