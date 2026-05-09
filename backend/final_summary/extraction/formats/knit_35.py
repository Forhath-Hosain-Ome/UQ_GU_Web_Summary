"""
------------------------------
Extractor for Knit garment reports with 35 defect columns.

This format uses the standard SPI layout.
No overrides needed — all defaults from BaseExtractor apply.

To customise for differences found in real files:
  - Override _field_extractors() to add/swap individual field extractors.
  - Override post_process() to apply field corrections after base extraction.
  - Override _read_sheet() if the sheet has header rows to skip.
"""

from .base import BaseExtractor


class Knit35Extractor(BaseExtractor):
    """Knit garment audit report — 35 defect columns."""

    REPORT_TYPE = "KNIT_35"

    # Standard SPI layout — no overrides needed at this time.
    # Add post_process() here when format-specific corrections are needed.