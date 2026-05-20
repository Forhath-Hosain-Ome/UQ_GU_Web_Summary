"""
-------------------------------
Extractor for Woven garment reports with 37 defect columns.

Same base layout as Knit35 — only the defect column count differs,
which is handled at export time via the BuyerFactoryPair template.
"""

from .base import BaseExtractor


class Woven37Extractor(BaseExtractor):
    """Woven garment audit report — 37 defect columns."""

    REPORT_TYPE = "WOVEN_37"

    # Standard layout — no overrides needed at this time.