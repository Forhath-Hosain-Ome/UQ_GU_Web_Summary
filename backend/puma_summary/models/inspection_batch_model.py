from django.db import models
from shared.models import BaseModel
from django.contrib.auth.models import User


class InspectionBatch(BaseModel):
    """
    One per upload session.
    Tracks the Celery job and aggregated counters.
    No files are stored — only extracted data lives in the DB.
    """

    class Status(models.TextChoices):
        PENDING    = "PENDING",    "Pending"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED  = "COMPLETED",  "Completed"
        PARTIAL    = "PARTIAL",    "Partial"   # some PDFs failed
        FAILED     = "FAILED",     "Failed"

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inspection_batches",
    )

    # Celery tracking
    celery_task_id = models.CharField(max_length=255, blank=True, db_index=True)
    status         = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    # Where the PDFs were on disk (used by retry task; not stored persistently for new uploads)
    source_folder  = models.CharField(max_length=512, blank=True)

    # Counters — filled in progressively by the Celery task
    total_pdfs     = models.PositiveIntegerField(default=0)
    processed_pdfs = models.PositiveIntegerField(default=0)
    failed_pdfs    = models.PositiveIntegerField(default=0)

    # Derived from the first successfully processed PDF
    factory_code   = models.CharField(max_length=20, blank=True)

    # Raw error dump (kept for debugging alongside structured BatchFailedPDF rows)
    error_log      = models.TextField(blank=True)

    # Relative path to the generated Excel file under media/
    # Plain CharField — Django does NOT manage this file's lifecycle
    excel_report_path = models.CharField(max_length=512, blank=True)

    # How many times this batch (or its failed PDFs) have been retried
    retry_count    = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Inspection Batch"
        verbose_name_plural = "Inspection Batches"

    def __str__(self):
        user = self.created_by.username if self.created_by_id else "unknown"
        return f"Batch #{self.pk} | {self.factory_code or 'Unknown'} | {self.status} | by {user}"

    @property
    def success_rate(self):
        if not self.total_pdfs:
            return 0.0
        return round(self.processed_pdfs / self.total_pdfs * 100, 1)

    @property
    def progress_percent(self):
        """Percentage complete — consumed by the WebSocket consumer."""
        if self.status in (self.Status.COMPLETED, self.Status.PARTIAL):
            return 100
        if not self.total_pdfs:
            return 0
        return int(self.processed_pdfs / self.total_pdfs * 100)