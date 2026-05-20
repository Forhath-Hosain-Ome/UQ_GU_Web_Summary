"""
-----------------
Represents a garment manufacturing factory.
A factory belongs to one buyer (the one it primarily produces for).
"""

from django.db import models
from shared.models import BaseModel
from .buyer import Buyer


class Factory(BaseModel):
    """A garment factory that produces for a buyer."""

    buyer = models.ForeignKey(
        Buyer,
        on_delete=models.PROTECT,
        related_name="factories",
        help_text="The buyer this factory primarily produces for.",
    )
    name = models.CharField(
        max_length=255,
        help_text="Full factory name as it appears in audit reports.",
    )
    code = models.CharField(
        max_length=20,
        blank=True,
        help_text="Short factory code (e.g. BABL, BCK).",
    )
    country = models.CharField(
        max_length=100,
        blank=True,
        help_text="Country where the factory is located.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["buyer", "name"]
        # Same factory name can exist for different buyers
        unique_together = [("buyer", "name")]
        verbose_name = "Factory"
        verbose_name_plural = "Factories"

    def __str__(self) -> str:
        return f"{self.name} ({self.buyer.name})"