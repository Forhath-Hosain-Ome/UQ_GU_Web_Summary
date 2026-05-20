"""
extraction/formats/sweater_37.py
---------------------------------
Extractor for Sweater / knitwear reports with 37 defect columns.

Sweater reports use General-Final-37.xlsx template at export.
The extraction layout is the same as Woven37 — only the product category
and template differ.
"""

from .base import BaseExtractor


class Sweater37Extractor(BaseExtractor):
    """Sweater / knitwear audit report — 37 defect columns."""

    REPORT_TYPE = "SWEATER_37"

    # Same layout as Woven37 — no overrides needed at this time.