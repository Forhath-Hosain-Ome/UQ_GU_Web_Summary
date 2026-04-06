from django.db import models
from shared.models import BaseModel
from django.contrib.auth.models import User


class FolderBatch(BaseModel):
    """
    One per upload session.
    Tracks the Celery job and aggregated counters.
    Each folder in the batch will produce one PDF output.
    """

    class Status(models.TextChoices):
        PENDING    = "PENDING",    "Pending"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED  = "COMPLETED",  "Completed"
        PARTIAL    = "PARTIAL",    "Partial"   # some folders failed
        FAILED     = "FAILED",     "Failed"

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="folder_batches",
    )

    # Celery tracking
    celery_task_id = models.CharField(max_length=255, blank=True, db_index=True)
    status         = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    # Where the folders were on disk (used by retry task; not stored persistently for new uploads)
    source_folder  = models.CharField(max_length=512, blank=True)

    # Counters — filled in progressively by the Celery task
    total_folders     = models.PositiveIntegerField(default=0)
    processed_folders = models.PositiveIntegerField(default=0)
    failed_folders    = models.PositiveIntegerField(default=0)

    # Raw error dump (kept for debugging alongside structured FolderFailedPDF rows)
    error_log      = models.TextField(blank=True)

    # How many times this batch (or its failed folders) have been retried
    retry_count    = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Folder Batch"
        verbose_name_plural = "Folder Batches"

    def __str__(self):
        user = self.created_by.username if self.created_by_id else "unknown"
        return f"FolderBatch #{self.pk} | {self.status} | by {user}"

    @property
    def success_rate(self):
        if not self.total_folders:
            return 0.0
        return round(self.processed_folders / self.total_folders * 100, 1)

    @property
    def progress_percent(self):
        """Percentage complete — consumed by the WebSocket consumer."""
        if self.status in (self.Status.COMPLETED, self.Status.PARTIAL):
            return 100
        if not self.total_folders:
            return 0
        return int(self.processed_folders / self.total_folders * 100)
