"""
-----------------------
One row per defect line item in an audit report.

category is stored as a single combined field: "<code> - <label>"
e.g. "A - Fabrics", "B - Sewing", "A - SPEC"

No separate category_code / category_label columns — keep it flat.
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

    # ── Position / ordering ───────────────────────────────────────────────────
    serial = models.PositiveIntegerField(
        default=0,
        help_text="item_no from defect_master — stable position in the template.",
    )

    # ── Category (combined code + label) ─────────────────────────────────────
    category = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text=(
            "Combined category string: '<code> - <label>'. "
            "E.g. 'A - Fabrics', 'B - Sewing Defects', 'A - SPEC'."
        ),
    )

    # ── Defect name ───────────────────────────────────────────────────────────
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
        ordering = ["serial"]
        verbose_name = "Defect Entry"
        verbose_name_plural = "Defect Entries"

    def __str__(self) -> str:
        return (
            f"[{self.serial}] {self.category} / {self.defect_name} "
            f"— {self.major}M/{self.minor}m"
        )