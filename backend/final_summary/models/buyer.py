"""
Represents a buyer / brand (e.g. UNIQLO, H&M).
One buyer can be paired with many factories.
"""

from django.db import models
from shared.models import BaseModel


class Buyer(BaseModel):
    """A brand or buying house that orders garments."""

    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Full buyer / brand name (e.g. UNIQLO CO. LTD)",
    )
    code = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        help_text="Short code used in report numbers (e.g. UNQ, HM)",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Buyer"
        verbose_name_plural = "Buyers"

    def __str__(self) -> str:
        return self.name