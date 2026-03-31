from django.db import models
from .inspection_batch_model import InspectionBatch
from shared.models import BaseModel
from django.utils import timezone

class InspectionReport(BaseModel):
    batch = models.ForeignKey(
        InspectionBatch, on_delete=models.CASCADE, related_name="reports"
    )

    # Which PDF this came from (name only — file is NOT stored)
    pdf_filename = models.CharField(max_length=512)

    # ── Report metadata ───────────────────────────────────────────────────────
    # Left blank at creation; filled in manually later
    report_number = models.CharField(max_length=100, blank=True, db_index=True)
 
    # Auto-set to the date the row is first created; never changes after that.
    # This is the "report generation date", separate from inspection_date.
    report_date = models.DateField(default=timezone.localdate, editable=False)

    # ── Extracted data ────────────────────────────────────────────────────────
    inspection_date = models.DateField(null=True, blank=True)
    style           = models.CharField(max_length=50, db_index=True)
    description     = models.CharField(max_length=512, blank=True)
    sample_size     = models.PositiveIntegerField(default=0)
    po_qty          = models.PositiveIntegerField(default=0)
    actual_qty      = models.PositiveIntegerField(default=0)
    inspected_qty   = models.PositiveIntegerField(default=0)
    major_defect    = models.CharField(max_length=30, blank=True)  # e.g. "2/32"
    minor_defect    = models.CharField(max_length=30, blank=True)  # e.g. "5/32"
    factory_code    = models.CharField(max_length=20, blank=True, db_index=True)
    factory_name    = models.CharField(max_length=255, blank=True)
    final_customer  = models.CharField(max_length=100, blank=True)


    class Meta:
        ordering = ["-inspection_date", "style"]
        verbose_name = "Inspection Report"
        verbose_name_plural = "Inspection Reports"

    def __str__(self):
        return f"{self.style} | {self.factory_code} | {self.inspection_date}"

    @property
    def style_with_pos(self):
        """e.g. '123456(4600000001,4600000002)' — used in Excel summary sheet."""
        pos = list(self.po_numbers.values_list("number", flat=True))
        return f"{self.style}({','.join(pos)})"
    
    @property
    def created_by(self):
        """Convenience accessor — delegates to the parent batch."""
        return self.batch.created_by