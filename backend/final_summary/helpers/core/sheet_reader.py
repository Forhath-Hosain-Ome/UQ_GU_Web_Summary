"""
sheet_reader.py
---------------
Thin wrappers around pandas.read_excel for consistent sheet loading.

All sheets are loaded with:
  - header=None  (no automatic header detection; row 0 is data row 0)
  - dtype=str    (everything comes in as strings; no type guessing)
  - fillna("")   (NaN replaced with empty string for safe .strip() calls)
"""

import logging
from pathlib import Path
from typing import List

import pandas as pd


def read_first_sheet(path: Path) -> pd.DataFrame:
    """
    Load only the first worksheet from *path*.
    Raises on file-read errors (caller is responsible for handling).
    """
    return pd.read_excel(path, sheet_name=0, header=None, dtype=str).fillna("")


def read_all_sheets(path: Path) -> List[pd.DataFrame]:
    """
    Load every worksheet from *path* and return them as a list of DataFrames.

    Falls back to reading just the first sheet if multi-sheet loading fails
    (e.g. corrupt or password-protected files).
    """
    try:
        xls = pd.read_excel(path, sheet_name=None, header=None, dtype=str)
        sheets = [df.fillna("") for df in xls.values()]
        logging.info(f"Loaded {len(sheets)} sheet(s) from '{path.name}'")
        return sheets
    except Exception as exc:  # BUG FIX: was 'except Exception:' — exc was unbound
        logging.warning(
            f"Multi-sheet read failed for '{path.name}' ({exc}); "
            "falling back to first sheet only."
        )
        return [read_first_sheet(path)]
