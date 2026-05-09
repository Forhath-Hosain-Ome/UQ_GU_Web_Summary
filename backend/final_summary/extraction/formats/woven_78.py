"""
-------------------------------
Extractor for SPI Woven garment reports with 78 defect columns.

The PQC format files (like BEACON KNIT WEAR) use this layout.
Key differences handled here:
  - Sheet name is "Audit Report" (not the active sheet)
  - Times are inline in cells: "FACTORY IN TIME: 08.00 AM"
  - Category cells use Japanese + English: "A素材不良\n Material Defects"
  - Report No may be a sequential number like "01"

The inline time and category differences are already handled generically
by the shared field extractors. This class documents the format differences
and provides a post_process() hook for any remaining corrections.
"""

from pathlib import Path

from .base import BaseExtractor, AuditRecord
from final_summary.extraction.core import CellGrid


class Woven78Extractor(BaseExtractor):
    """SPI Woven garment audit report — 78 defect columns (PQC format)."""

    REPORT_TYPE = "WOVEN_78"

    def post_process(
        self,
        record: AuditRecord,
        grid: CellGrid,
        path: Path,
    ) -> AuditRecord:
        """
        PQC-specific corrections applied after base extraction.

        1. report_no: bare sequential numbers like "01" are valid — do not
           replace them with "" even if they fail the standard pattern.
           (The validator treats this as a soft warning, not a block.)

        2. audit_result: PQC sheets may not have an explicit result cell.
           If still empty after extraction, leave as "-" (the default).
        """
        # Ensure report_no is kept as-is even if it's just "01"
        if record.report_no and not record.report_no.strip():
            record.report_no = ""

        return record