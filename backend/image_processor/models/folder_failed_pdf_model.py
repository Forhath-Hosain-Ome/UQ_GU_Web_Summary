from django.db import models
from django.contrib.auth.models import User
from .folder_batch_model import FolderBatch
from shared.models import BaseModel


class FolderFailedPDF(BaseModel):
    """
    Structured log entry for each folder that failed during processing.
    One row per failed folder — linked to the parent FolderBatch.
    """
    batch = models.ForeignKey(
        FolderBatch, on_delete=models.CASCADE, related_name="batch_failed_folders"
    )

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="folder_failed_pdfs",
    )

    folder_name = models.CharField(max_length=512)
    reason      = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Folder Failed PDF"
        verbose_name_plural = "Folder Failed PDFs"

    def __str__(self):
        return f"{self.folder_name} | Batch #{self.batch_id}"
