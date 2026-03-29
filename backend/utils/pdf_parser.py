import logging
from pathlib import Path

import pdfplumber

from shared.exceptions import InvalidPDFError

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    Extract full text from all pages of a PDF.
    Returns concatenated page text.
    Raises InvalidPDFError if PDF is empty or unreadable.
    """
    text_all = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_all += page_text + "\n"
    except Exception as exc:
        raise InvalidPDFError(f"Cannot open PDF {pdf_path.name}: {exc}") from exc

    if not text_all.strip():
        raise InvalidPDFError(f"PDF is empty: {pdf_path.name}")

    logger.debug("Extracted %d chars from %s", len(text_all), pdf_path.name)
    return text_all