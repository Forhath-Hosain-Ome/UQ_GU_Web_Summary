"""
--------------------------------
Thin wrappers around pandas.read_excel for consistent sheet loading.

Moved from helpers/core/sheet_reader.py — no logic changes.
All imports across the codebase should be updated to:
    from extraction.core.sheet_reader import read_sheet, read_all_sheets

All sheets are loaded with:
  - header=None  (no automatic header detection; row 0 is data row 0)
  - dtype=str    (everything comes in as strings; no type guessing)
  - fillna("")   (NaN replaced with empty string for safe .strip() calls)
"""

import logging
from pathlib import Path
from typing import List, Optional

import pandas as pd


def read_first_sheet(path: Path) -> pd.DataFrame:
    """
    Load only the first worksheet from *path*.
    Raises on file-read errors (caller is responsible for handling).
    """
    return pd.read_excel(path, sheet_name=0, header=None, dtype=str).fillna("")


def read_sheet(
    path: Path,
    sheet_name: Optional[str] = None,
    skip_rows: int = 0,
) -> pd.DataFrame:
    """
    Load a specific worksheet from *path*.

    Parameters
    ----------
    path : Path
        Excel file path.
    sheet_name : str, optional
        Name of the sheet to load. If None, loads the first sheet.
    skip_rows : int, optional
        Number of rows to skip from the top before reading data.

    Returns
    -------
    pd.DataFrame
    """
    if sheet_name is None:
        return read_first_sheet(path)
    return pd.read_excel(
        path,
        sheet_name=sheet_name,
        header=None,
        dtype=str,
        skiprows=skip_rows if skip_rows > 0 else None,
    ).fillna("")


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
    except Exception as exc:
        logging.warning(
            f"Multi-sheet read failed for '{path.name}' ({exc}); "
            "falling back to first sheet only."
        )
        return [read_first_sheet(path)]


def get_sheet_names(path: Path) -> List[str]:
    """
    Return all sheet names in the workbook without loading any data.
    Useful for checking which sheets exist before deciding what to extract.
    """
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        names = wb.sheetnames
        wb.close()
        return names
    except Exception as exc:
        logging.warning(f"Could not read sheet names from '{path.name}': {exc}")
        return []