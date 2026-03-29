from django.db import models


class InspectionBatch(models.Model):
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

    # Celery tracking
    celery_task_id = models.CharField(max_length=255, blank=True, db_index=True)
    status         = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    # Where the PDFs were on disk (used by the task; not stored persistently)
    source_folder  = models.CharField(max_length=512)

    # Counters — filled in progressively by the Celery task
    total_pdfs     = models.PositiveIntegerField(default=0)
    processed_pdfs = models.PositiveIntegerField(default=0)
    failed_pdfs    = models.PositiveIntegerField(default=0)

    # Derived from the first successfully processed PDF
    factory_code   = models.CharField(max_length=20, blank=True)

    # Error log for failed PDFs (filenames + reasons)
    error_log      = models.TextField(blank=True)

    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Inspection Batch"
        verbose_name_plural = "Inspection Batches"

    def __str__(self):
        return f"Batch #{self.pk} | {self.factory_code or 'Unknown'} | {self.status}"

    @property
    def success_rate(self):
        if not self.total_pdfs:
            return 0.0
        return round(self.processed_pdfs / self.total_pdfs * 100, 1)

    @property
    def progress_percent(self):
        """Percentage complete — consumed by the JS polling endpoint."""
        if self.status in (self.Status.COMPLETED, self.Status.PARTIAL):
            return 100
        if not self.total_pdfs:
            return 0
        return int(self.processed_pdfs / self.total_pdfs * 100)