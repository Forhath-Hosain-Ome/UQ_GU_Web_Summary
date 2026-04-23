from django.db import models
from django.contrib.auth.models import User
from shared.models import BaseModel


class UploadBatch(BaseModel):
    """
    Represents one bulk-upload session of Excel files.
    Each batch contains many AuditReports extracted from those files.
    """

    class Status(models.TextChoices):
        PENDING    = "PENDING",    "Pending"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED  = "COMPLETED",  "Completed"
        PARTIAL    = "PARTIAL",    "Partial"   # some files failed
        FAILED     = "FAILED",     "Failed"

    created_by     = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="audit_upload_batches",
    )
    celery_task_id = models.CharField(max_length=255, blank=True, db_index=True)
    status         = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    # Counters
    total_files     = models.PositiveIntegerField(default=0)
    processed_files = models.PositiveIntegerField(default=0)
    failed_files    = models.PositiveIntegerField(default=0)

    # Raw error dump
    error_log = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Upload Batch"
        verbose_name_plural = "Upload Batches"

    def __str__(self):
        user = self.created_by.username if self.created_by_id else "unknown"
        return f"AuditBatch #{self.pk} | {self.status} | by {user}"

    @property
    def success_rate(self):
        if not self.total_files:
            return 0.0
        return round(self.processed_files / self.total_files * 100, 1)

    @property
    def progress_percent(self):
        if self.status in (self.Status.COMPLETED, self.Status.PARTIAL):
            return 100
        if not self.total_files:
            return 0
        return int(self.processed_files / self.total_files * 100)