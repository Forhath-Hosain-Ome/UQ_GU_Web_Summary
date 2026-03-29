from django.db import models
from .inspection_batch_model import InspectionBatch
from shared.models import BaseModel


class BatchFailedPDF(BaseModel):
    """
    Structured record of a single PDF that failed during batch processing.
    One row per failed file — replaces the free-text error_log for machine use.
    The error_log TextField on InspectionBatch is kept as a raw debug dump.
    """

    batch = models.ForeignKey(
        InspectionBatch,
        on_delete=models.CASCADE,
        related_name="failed_pdfs",
    )
    filename = models.CharField(max_length=512)
    reason   = models.TextField(blank=True)
    retried  = models.BooleanField(default=False)   # flipped when a retry succeeds

    class Meta:
        ordering = ["filename"]
        verbose_name = "Batch Failed PDF"
        verbose_name_plural = "Batch Failed PDFs"

    def __str__(self):
        return f"{self.filename} — Batch #{self.batch_id}"