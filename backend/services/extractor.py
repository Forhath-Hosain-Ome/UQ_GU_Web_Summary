"""
PDF extraction service – pure domain logic, no Django ORM, no file I/O.
Mirrors extract_reports() from the original script but returns typed dicts.
"""
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from utils.constants import (
    FACTORY_ENUM,
    REGEX_INSPECTION_DATE,
    REGEX_TOTAL_ROW,
    REGEX_WORKMANSHIP,
    REGEX_STYLE_LINE,
    REGEX_PO_NUMBER,
    REGEX_FACTORY,
    REGEX_FINAL_CUSTOMER,
)
from utils.pdf_parser import extract_text_from_pdf
from shared.exceptions import ExtractionError, InvalidPDFError

logger = logging.getLogger(__name__)


def _parse_inspection_date(text: str) -> str:
    m = re.search(REGEX_INSPECTION_DATE, text)
    if not m:
        return ""
    try:
        return datetime.strptime(m.group(1), "%d %b %Y").strftime("%Y-%m-%d")
    except ValueError:
        return m.group(1)


def _parse_quantities(text: str) -> tuple[int, int, int]:
    total_line = re.search(REGEX_TOTAL_ROW, text, re.IGNORECASE)
    if not total_line:
        raise ExtractionError("TOTAL row not found in PDF text")
    nums = list(map(int, re.findall(r"\d+", total_line.group(0))))
    return nums[0], nums[1], nums[-1]   # po_qty, actual_qty, inspected_qty


def _parse_defects(text: str) -> tuple[str, str]:
    m = re.search(REGEX_WORKMANSHIP, text)
    if not m:
        return "", ""
    return m.group(1).replace(" ", ""), m.group(2).replace(" ", "")


def _parse_style_description(text: str) -> tuple[str, str]:
    m = re.search(REGEX_STYLE_LINE, text)
    if not m:
        raise ExtractionError("Style line not found in PDF text")

    style = m.group(2)
    description = m.group(1).strip()

    # Check if next line continues description
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if "1. " in line and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if next_line and all(c.isalpha() or c.isspace() for c in next_line):
                description += " " + next_line
            break

    return style, description


def _parse_factory(text: str) -> tuple[str, str]:
    m = re.search(REGEX_FACTORY, text, re.IGNORECASE | re.MULTILINE)
    if not m:
        return "", ""
    code = m.group(1).strip().upper()
    return code, FACTORY_ENUM.get(code, code)


def _parse_pos(text: str) -> list[str]:
    pos = re.findall(REGEX_PO_NUMBER, text)
    if not pos:
        raise ExtractionError("No PO numbers found in PDF text")
    return sorted(pos)


def _parse_final_customer(text: str) -> str:
    m = re.search(REGEX_FINAL_CUSTOMER, text)
    return m.group(1) if m else ""


def extract_single_pdf(pdf_path: Path) -> dict:
    """
    Extract all inspection data from one PDF.
    Returns a dict ready to be saved to the DB.
    Raises ExtractionError or InvalidPDFError on failure.
    """
    text = extract_text_from_pdf(pdf_path)

    inspection_date = _parse_inspection_date(text)
    po_qty, actual_qty, inspected_qty = _parse_quantities(text)
    major_defect, minor_defect = _parse_defects(text)
    style, description = _parse_style_description(text)
    factory_code, factory_name = _parse_factory(text)
    pos = _parse_pos(text)
    final_customer = _parse_final_customer(text)

    return {
        "pdf_filename": pdf_path.name,
        "inspection_date": inspection_date,
        "style": style,
        "description": description,
        "sample_size": inspected_qty,
        "po_qty": po_qty,
        "actual_qty": actual_qty,
        "inspected_qty": inspected_qty,
        "major_defect": major_defect,
        "minor_defect": minor_defect,
        "factory_code": factory_code,
        "factory_name": factory_name,
        "final_customer": final_customer,
        "po_numbers": pos,
    }


def extract_folder(folder: Path) -> tuple[list[dict], list[str]]:
    """
    Extract data from all PDFs in folder.
    Returns (successful_records, failed_filenames).
    """
    records, failures = [], []

    for pdf_file in sorted(folder.glob("*.pdf")):
        try:
            record = extract_single_pdf(pdf_file)
            records.append(record)
            logger.info("OK | %s | Style=%s | POs=%s",
                        pdf_file.name, record["style"], ",".join(record["po_numbers"]))
        except (ExtractionError, InvalidPDFError) as exc:
            logger.error("FAILED | %s | %s", pdf_file.name, exc)
            failures.append(pdf_file.name)

    return records, failures