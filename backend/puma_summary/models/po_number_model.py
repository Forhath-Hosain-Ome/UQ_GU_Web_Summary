from django.db import models
from django.contrib.auth.models import User
from .inspection_report_model import InspectionReport
from shared.models import BaseModel

class PONumber(BaseModel):
    """
    Individual PO number belonging to one InspectionReport.
    Stored as a proper child row so POs are independently searchable/filterable.
    One report → many POs.
    """

    report = models.ForeignKey(
        InspectionReport, on_delete=models.CASCADE, related_name="po_numbers"
    )

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="po_numbers",
    )

    number = models.CharField(max_length=50, db_index=True)

    class Meta:
        ordering = ["number"]
        unique_together = [["report", "number"]]
        verbose_name = "PO Number"

    def __str__(self):
        return self.number