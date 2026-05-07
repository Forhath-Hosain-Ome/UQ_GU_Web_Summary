"""
-----------------------
One row per defect line item in an audit report.
"""

from django.db import models
from shared.models import BaseModel
from .audit_report import AuditReport


class DefectEntry(BaseModel):
    """One defect row extracted from the defect table in an audit Excel."""

    report = models.ForeignKey(
        AuditReport,
        on_delete=models.CASCADE,
        related_name="defect_entries",
    )

    category = models.CharField(max_length=100, blank=True, db_index=True)
    item     = models.CharField(max_length=512, blank=True)
    major    = models.PositiveIntegerField(default=0)
    minor    = models.PositiveIntegerField(default=0)
    comment  = models.TextField(blank=True)

    class Meta:
        ordering = ["category", "item"]
        verbose_name = "Defect Entry"
        verbose_name_plural = "Defect Entries"

    def __str__(self) -> str:
        return f"{self.category} / {self.item} — {self.major}M/{self.minor}m"