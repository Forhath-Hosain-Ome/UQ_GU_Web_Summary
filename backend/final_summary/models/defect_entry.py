from django.db import models
from shared.models import BaseModel
from .audit_report import AuditReport


class DefectEntry(BaseModel):
    """
    One row per defect line item in an audit report.
    Replaces the flat JSON defect_rows list with a proper relational table
    so defects can be aggregated across reports for the summary output.
    """

    report      = models.ForeignKey(
        AuditReport, on_delete=models.CASCADE, related_name="defect_entries",
    )
    category    = models.CharField(max_length=100, blank=True, db_index=True)
    item        = models.CharField(max_length=512, blank=True)
    major       = models.PositiveIntegerField(default=0)
    minor       = models.PositiveIntegerField(default=0)
    comment     = models.TextField(blank=True)

    class Meta:
        ordering = ["category", "item"]
        verbose_name = "Defect Entry"
        verbose_name_plural = "Defect Entries"
        indexes = [
            models.Index(fields=["report", "category"]),
        ]

    def __str__(self):
        return f"{self.category} / {self.item} — {self.major}M/{self.minor}m"