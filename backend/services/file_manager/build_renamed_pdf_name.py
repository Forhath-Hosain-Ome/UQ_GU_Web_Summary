import logging
import re
import shutil
from pathlib import Path

from utils.constants import REGEX_TRAILING_COUNTER
from shared.exceptions import FileProcessingError

logger = logging.getLogger(__name__)


def build_renamed_pdf_name(record: dict) -> str:
    """Build the standardised PDF filename for a processed report."""
    po_first = record["po_numbers"][0] if record["po_numbers"] else "NO_PO"
    name = (
        f"Apparel Report_{record['style']} {record['factory_code']}, "
        f"Puma Warehouse WH AQL, PO {po_first}, "
        f"Customer {record['final_customer']}.pdf"
    )
    return re.sub(REGEX_TRAILING_COUNTER, "", name)
