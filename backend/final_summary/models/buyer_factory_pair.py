"""
-----------------------------
The registration record that links a buyer to a factory.

This is the single source of truth for:
  - Which report format (template) to use   →  report_type
  - Which inspection types are allowed      →  available_reports (JSON list)

Both the upload flow and the export flow look up this record to determine
which extractor class and which Excel template to use.

Report types
------------
  KNIT_35    Knit garments — 35 defect columns
  WOVEN_37   Woven garments — 37 defect columns
  WOVEN_78   Woven garments (SPI) — 78 defect columns
  SWEATER_37 Sweater / knitwear — 37 defect columns

Available report choices (stored as a JSON list)
-------------------------------------------------
  FINAL, RE_FINAL, INLINE, SAMPLE, CMF
"""

from django.db import models
from django.core.exceptions import ValidationError
from shared.models import BaseModel
from .buyer import Buyer
from .factory import Factory


class ReportType(models.TextChoices):
    KNIT_35    = "KNIT_35",    "Knit (35 defects)"
    WOVEN_37   = "WOVEN_37",   "Woven (37 defects)"
    WOVEN_78   = "WOVEN_78",   "Woven SPI (78 defects)"
    SWEATER_37 = "SWEATER_37", "Sweater (37 defects)"


class AvailableReport(models.TextChoices):
    FINAL    = "FINAL",    "Final"
    RE_FINAL = "RE_FINAL", "Re-Final"
    INLINE   = "INLINE",   "In-Line"
    SAMPLE   = "SAMPLE",   "Sample"
    CMF      = "CMF",      "CMF"


# Ordered list of all valid report choices (used for validation)
ALL_REPORT_CHOICES = [c.value for c in AvailableReport]

# Template file names keyed by report_type
TEMPLATE_FILE_MAP: dict[str, str] = {
    ReportType.KNIT_35:    "General-Final-35.xlsx",
    ReportType.WOVEN_37:   "General-Final-37.xlsx",
    ReportType.WOVEN_78:   "SPI-Final-78.xlsx",
    ReportType.SWEATER_37: "General-Final-37.xlsx",
}


class BuyerFactoryPair(BaseModel):
    """
    Registration of a buyer–factory relationship.

    One factory has exactly one report_type (e.g. Knit-35).
    The available_reports list controls which inspection types can be
    uploaded and exported for this pair.
    """

    buyer = models.ForeignKey(
        Buyer,
        on_delete=models.PROTECT,
        related_name="pair_set",
    )
    factory = models.ForeignKey(
        Factory,
        on_delete=models.PROTECT,
        related_name="pair_set",
    )
    report_type = models.CharField(
        max_length=20,
        choices=ReportType.choices,
        help_text="Excel template format for this factory.",
    )
    # Stored as a JSON list, e.g. ["FINAL", "RE_FINAL", "INLINE"]
    available_reports = models.JSONField(
        default=list,
        help_text=(
            "Inspection types allowed for this pair. "
            "Choose from: FINAL, RE_FINAL, INLINE, SAMPLE, CMF."
        ),
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["buyer__name", "factory__name"]
        unique_together = [("buyer", "factory")]
        verbose_name = "Buyer–Factory Pair"
        verbose_name_plural = "Buyer–Factory Pairs"

    def __str__(self) -> str:
        return f"{self.buyer.name} × {self.factory.name} [{self.report_type}]"

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def clean(self) -> None:
        """Validate available_reports contains only known choices."""
        if not isinstance(self.available_reports, list):
            raise ValidationError(
                {"available_reports": "Must be a list of report type strings."}
            )
        invalid = [
            r for r in self.available_reports
            if r not in ALL_REPORT_CHOICES
        ]
        if invalid:
            raise ValidationError(
                {
                    "available_reports": (
                        f"Invalid report type(s): {invalid}. "
                        f"Valid choices: {ALL_REPORT_CHOICES}"
                    )
                }
            )
        if not self.available_reports:
            raise ValidationError(
                {"available_reports": "At least one report type must be selected."}
            )

        # Factory's buyer must match pair's buyer
        if self.factory_id and self.buyer_id:
            if self.factory.buyer_id != self.buyer_id:
                raise ValidationError(
                    {
                        "factory": (
                            f"Factory '{self.factory.name}' belongs to buyer "
                            f"'{self.factory.buyer.name}', not '{self.buyer.name}'."
                        )
                    }
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def template_file(self) -> str:
        """Return the Excel template filename for this report type."""
        return TEMPLATE_FILE_MAP.get(self.report_type, "SPI-Final-78.xlsx")

    @property
    def defect_column_count(self) -> int:
        """Return the number of defect columns for this report type."""
        mapping = {
            ReportType.KNIT_35:    35,
            ReportType.WOVEN_37:   37,
            ReportType.WOVEN_78:   78,
            ReportType.SWEATER_37: 37,
        }
        return mapping.get(self.report_type, 37)

    def allows_report(self, report_type: str) -> bool:
        """Return True if report_type is in this pair's available_reports."""
        return report_type in self.available_reports