"""
-----------------------
One upload session = one batch.

Key changes from old model
---------------------------
- buyer_factory_pair FK replaces the free-text format_type field.
  The pair drives which extractor and which template are used.
- inspection_date is set by the user at upload time and applied to
  every AuditReport in this batch (not extracted from Excel).
- format_type property is derived from the pair for backward compat.
"""

from django.db import models
from shared.models import BaseModel
from .buyer_factory_pair import BuyerFactoryPair


class UploadBatch(BaseModel):
    """One bulk-upload session of Excel audit files."""

    class Status(models.TextChoices):
        PENDING    = "PENDING",    "Pending"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED  = "COMPLETED",  "Completed"
        PARTIAL    = "PARTIAL",    "Partial"
        FAILED     = "FAILED",     "Failed"

    # ── Registration link ─────────────────────────────────────────────────────
    pair = models.ForeignKey(
        BuyerFactoryPair,
        on_delete=models.PROTECT,
        related_name="batches",
        help_text="The buyer–factory pair this batch belongs to.",
    )

    # ── User inputs at upload time ────────────────────────────────────────────
    inspection_date = models.DateField(
        help_text=(
            "Inspection date entered by the user at upload. "
            "Applied to every report in this batch instead of extracting "
            "it from the Excel files."
        ),
    )

    # ── Tracking ──────────────────────────────────────────────────────────────
    celery_task_id = models.CharField(max_length=255, blank=True, db_index=True)
    status         = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    # ── Counters ──────────────────────────────────────────────────────────────
    total_files     = models.PositiveIntegerField(default=0)
    processed_files = models.PositiveIntegerField(default=0)
    failed_files    = models.PositiveIntegerField(default=0)

    # ── Error log ─────────────────────────────────────────────────────────────
    error_log = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Upload Batch"
        verbose_name_plural = "Upload Batches"

    def __str__(self) -> str:
        user = self.created_by.username if self.created_by_id else "unknown"
        return (
            f"Batch #{self.pk} | {self.pair} | "
            f"{self.inspection_date} | {self.status} | by {user}"
        )

    # ── Derived properties ────────────────────────────────────────────────────

    @property
    def format_type(self) -> str:
        """Backward-compatible alias — derive from the pair."""
        return self.pair.report_type

    @property
    def buyer(self):
        return self.pair.buyer

    @property
    def factory(self):
        return self.pair.factory

    @property
    def success_rate(self) -> float:
        if not self.total_files:
            return 0.0
        return round(self.processed_files / self.total_files * 100, 1)

    @property
    def progress_percent(self) -> int:
        if self.status in (self.Status.COMPLETED, self.Status.PARTIAL):
            return 100
        if not self.total_files:
            return 0
        return int(self.processed_files / self.total_files * 100)