from django.db import models
<<<<<<< HEAD
=======
from django.contrib.auth.models import User
>>>>>>> feature/final-summary
from .folder_batch_model import FolderBatch
from shared.models import BaseModel
from django.utils import timezone


class FolderReport(BaseModel):
    """
    One row per folder that was processed.
    Stores the path to the generated PDF output.
    """
    batch = models.ForeignKey(
        FolderBatch, on_delete=models.CASCADE, related_name="reports"
    )

<<<<<<< HEAD
=======
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="folder_reports",
    )

>>>>>>> feature/final-summary
    # Which folder this came from (relative path)
    folder_name = models.CharField(max_length=512)

    # Path to the generated PDF output (relative to media/)
    pdf_output_path = models.CharField(max_length=512, blank=True)

    # Status of this specific folder processing
    class Status(models.TextChoices):
        PENDING    = "PENDING",    "Pending"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED  = "COMPLETED",  "Completed"
        FAILED     = "FAILED",     "Failed"

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )

    # Error message if processing failed
    error_message = models.TextField(blank=True)

    # Number of images in the folder
    image_count = models.PositiveIntegerField(default=0)

    # Processing metadata (stored as JSON string)
    metadata = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at", "folder_name"]
        verbose_name = "Folder Report"
        verbose_name_plural = "Folder Reports"

    def __str__(self):
        return f"{self.folder_name} | {self.status} | Batch #{self.batch_id}"

    @property
<<<<<<< HEAD
    def created_by(self):
=======
    def created_by_user(self):
>>>>>>> feature/final-summary
        """Convenience accessor — delegates to the parent batch."""
        return self.batch.created_by
