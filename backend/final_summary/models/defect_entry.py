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

    # ── Canonical fields from defect_master ──────────────────────────────────
    category_code  = models.CharField(
        max_length=10,
        blank=True,
        db_index=True,
        help_text="Single-letter category code from defect_master (e.g. 'A', 'B').",
    )
    category_label = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Human-readable category label (e.g. 'Fabrics', 'Sewing').",
    )
    defect_name = models.CharField(
        max_length=512,
        blank=True,
        help_text="Canonical defect item name from defect_master.",
    )

    # ── Counts ────────────────────────────────────────────────────────────────
    major   = models.PositiveIntegerField(default=0)
    minor   = models.PositiveIntegerField(default=0)
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ["category_code", "defect_name"]
        verbose_name = "Defect Entry"
        verbose_name_plural = "Defect Entries"

    def __str__(self) -> str:
        return (
            f"{self.category_code} / {self.defect_name} "
            f"— {self.major}M/{self.minor}m"
        )