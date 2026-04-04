"""
text_number_extractor.py
------------------------
Utility functions for pulling numeric values out of messy strings.

Common use-case: Excel cells that mix quantity and unit,
e.g. "1,200 PCS" → "1200" or  "3,500 SET" → "3500".
"""

import re
import logging


# ---------------------------------------------------------------------------
# Extraction functions
# ---------------------------------------------------------------------------

def extract_numbers_only(value: str) -> str:
    """
    Extract ALL numbers from *value* and return them space-joined.

    "1,200 PCS + 300 SET" → "1200 300"
    """
    if not value:
        return ""

    value = value.strip()
    matches = re.findall(r"[\d,]+\.?\d*", value)

    if not matches:
        logging.debug(f"No numbers found in: '{value}'")
        return ""

    cleaned = [m.replace(",", "") for m in matches]
    return " ".join(cleaned) if len(cleaned) > 1 else cleaned[0]


def extract_first_number_only(value: str) -> str:
    """
    Extract only the FIRST number from *value*.

    "1,200 PCS" → "1200"
    "PO: 3500"  → "3500"
    """
    if not value:
        return ""

    value = value.strip()
    match = re.search(r"[\d,]+\.?\d*", value)

    if not match:
        logging.debug(f"No number found in: '{value}'")
        return ""

    return match.group().replace(",", "")


def extract_integer_only(value: str) -> str:
    """
    Extract the first contiguous run of *digits* (no decimal point).

    "12.5 hours" → "12"
    "3,500 SET"  → "3"   (use extract_first_number_only if commas matter)
    """
    if not value:
        return ""

    match = re.search(r"\d+", value)
    return match.group() if match else ""


def is_mostly_numeric(value: str) -> bool:
    """Return True if *value* contains at least one digit."""
    return bool(re.search(r"\d", value))
