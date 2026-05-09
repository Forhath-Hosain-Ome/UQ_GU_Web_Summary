"""
------------------------
Resolves which sheet to extract the audit record from for a given Excel file.

Priority
--------
1. First sheet whose name contains a preferred keyword (case-insensitive).
   Keywords: "audit report", "inspection report", "final audit"
2. Active sheet (the sheet open when the file was last saved).
3. First sheet (guaranteed fallback).

Rationale
---------
The active sheet is unreliable — some files are saved with a summary or
photo sheet active. Keyword matching finds the data sheet regardless of
what was last active when the file was saved.

To add a new preferred keyword → add to PREFERRED_KEYWORDS below.
"""

import logging
from pathlib import Path
from typing import Optional, Tuple

# Sheet name substrings that identify the main audit data sheet.
# Checked in order — first match wins.
PREFERRED_KEYWORDS: list[str] = [
    "audit report",
    "inspection report",
    "final audit",
]


def resolve_sheet_name(excel_path: Path) -> Tuple[Optional[str], str]:
    """
    Determine which sheet to extract audit data from.

    Parameters
    ----------
    excel_path : Path to the Excel file

    Returns
    -------
    (sheet_name, reason)
      sheet_name : the resolved sheet name, or None if the file can't be read
      reason     : human-readable explanation (for logging)
    """
    try:
        import openpyxl
        wb         = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
        sheet_names = wb.sheetnames

        if not sheet_names:
            wb.close()
            return None, "no sheets found in workbook"

        # 1. Keyword match
        for sheet in sheet_names:
            lower = sheet.lower().strip()
            for kw in PREFERRED_KEYWORDS:
                if kw in lower:
                    wb.close()
                    return sheet, f"keyword match '{kw}' → sheet '{sheet}'"

        # 2. Active sheet
        active = wb.active
        if active is not None:
            name = active.title
            wb.close()
            return name, f"active sheet '{name}'"

        # 3. First sheet
        first = sheet_names[0]
        wb.close()
        return first, f"first sheet '{first}' (fallback)"

    except Exception as exc:
        logging.warning(
            "sheet_resolver: could not read '%s': %s", excel_path.name, exc
        )
        return None, f"error reading workbook: {exc}"