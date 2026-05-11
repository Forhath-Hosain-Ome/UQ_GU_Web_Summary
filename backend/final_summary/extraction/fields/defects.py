"""
-----------------------------
Extracts the structured defect table from an audit report sheet.

Supports two layout formats automatically:

  Format A (SPI / Standard):
    - "Defects" header is in col A (index 0)
    - Category rows: "A : Fabrics", "B : Sewing", ...

  Format B (PQC / Japanese):
    - "Defects" header is in a non-A column (e.g. col 7)
    - Category rows: "A素材不良\n Material Defects", "B縫製不良\nSewing Defects"
    - Col A contains the Japanese category label

Detection strategy
------------------
1. Scan all rows for ANY cell whose text == "defects" (case-insensitive).
2. The row containing that cell is the header row.
3. Discover Major / Minor / Comment column indices from the same header row.
4. Item names come from the "Defects" column (same column as the header cell).
5. Categories come from col A (index 0) — works for both formats.
6. Stop scanning at a "Total" row or end-of-table sentinel.

Returns
-------
(defect_rows, totals)
  defect_rows : List[dict] — each dict has: category, item, major, minor, comment
  totals      : dict       — {"major": N, "minor": N}

To add new sentinel text  → edit _END_SENTINELS / _TOTAL_PATTERN
To change category logic  → edit _is_category_cell / _extract_category_label
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openpyxl

# ---------------------------------------------------------------------------
# Sentinel patterns
# ---------------------------------------------------------------------------

_END_SENTINELS = re.compile(
    r"do\s*/\s*set\s*/\s*col\s*/\s*size",
    re.IGNORECASE,
)
_TOTAL_PATTERN = re.compile(
    r"^\s*total(\s+(no\.?\s*of\s*)?defect)?\s*$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Category detection — supports both SPI and PQC formats
# ---------------------------------------------------------------------------

def _is_category_cell(value: Any) -> bool:
    """
    True for category header cells in either format:
      Format A: "A : Fabrics", "B : Sewing"
      Format B: "A素材不良\n Material Defects", "B縫製不良\nSewing Defects"
    """
    if not value:
        return False
    s = str(value).strip()
    if not s:
        return False
    # Format A — letter + optional space + colon
    if re.match(r"^[A-F]\s*:", s):
        return True
    # Format B — letter immediately followed by non-ASCII character
    if len(s) >= 2 and s[0] in "ABCDEF" and ord(s[1]) > 127:
        return True
    return False


def _extract_category_label(value: Any) -> str:
    """
    Return a clean English category label from either format.
      "A : Fabrics"                   → "A : Fabrics"
      "A素材不良\n Material Defects"  → "Material Defects"
    """
    s = str(value).strip()
    # If there is a newline, take the first all-ASCII part after it
    if "\n" in s:
        for part in s.split("\n"):
            part = part.strip()
            if part and all(ord(c) < 128 for c in part):
                return part
    # Already ASCII (Format A)
    if all(ord(c) < 128 for c in s):
        return s
    # Mixed — extract first run of ASCII words
    m = re.search(r"([A-Z][a-zA-Z][\w\s,/()&-]*)", s)
    return m.group(1).strip() if m else s[:30]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return 0


def _is_end(value: Any) -> bool:
    if not value:
        return False
    s = str(value).strip()
    return bool(_END_SENTINELS.search(s))


def _is_total(value: Any) -> bool:
    if not value:
        return False
    return bool(_TOTAL_PATTERN.match(str(value).strip()))


# ---------------------------------------------------------------------------
# Header discovery
# ---------------------------------------------------------------------------

def _find_header(
    rows: list,
) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int], Optional[int]]:
    """
    Scan rows for the defect table header (a cell whose text == "defects").

    Returns
    -------
    (header_row_idx, item_col, major_col, minor_col, comment_col)
    All indices are 0-based. Returns all None if not found.
    """
    for r_idx, row in enumerate(rows):
        if not row:
            continue

        item_col = major_col = minor_col = comment_col = None

        for c_idx, cell in enumerate(row):
            if cell is None:
                continue
            text = str(cell).strip().lower()

            if text == "defects":
                item_col = c_idx  # items are in this column

            if "major" in text and major_col is None:
                major_col = c_idx
            if "minor" in text and minor_col is None:
                minor_col = c_idx
            if "comment" in text and comment_col is None:
                comment_col = c_idx

        if item_col is not None:
            return r_idx, item_col, major_col, minor_col, comment_col

    return None, None, None, None, None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract(
    path: Path,
    sheet_name: Optional[str] = None,
    grid=None,  # unused — kept for uniform signature; openpyxl used directly
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Extract the defect table from *path* / *sheet_name*.

    Parameters
    ----------
    path       : Path to the Excel file
    sheet_name : Sheet to read. Falls back to first sheet if not found.
    grid       : Ignored — openpyxl is used directly for raw cell access.

    Returns
    -------
    (defect_rows, totals)
      defect_rows : list of dicts {category, item, major, minor, comment}
      totals      : {"major": N, "minor": N}
    """
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception as exc:
        logging.error(f"defects.extract: cannot open '{path.name}': {exc}")
        return [], {}

    # Search order: use sheet_name if provided, otherwise check all sheets
    sheet_names = wb.sheetnames
    search_order = []
    if sheet_name and sheet_name in sheet_names:
        search_order.append(sheet_name)
    search_order.extend([s for s in sheet_names if s not in search_order])

    rows = []
    header_info = (None, None, None, None, None)

    for s_name in search_order:
        ws = wb[s_name]
        temp_rows = list(ws.iter_rows(values_only=True))
        res = _find_header(temp_rows)
        if res[0] is not None:
            header_info = res
            rows = temp_rows
            logging.info(f"[{path.name}] Defect table found on sheet '{s_name}'")
            break

    wb.close()

    header_idx, item_col, major_col, minor_col, comment_col = header_info

    if header_idx is None:
        logging.warning(f"[{path.name}] Defect header row not found in any sheet.")
        return [], {}

    if major_col is None:
        logging.warning(f"[{path.name}] 'Major' column not found in defect header.")
        return [], {}

    # item_col defaults to col B (index 1) if not explicitly found
    if item_col is None:
        item_col = 1

    logging.info(
        f"[{path.name}] Defect header row={header_idx + 1} "
        f"item_col={item_col} major_col={major_col} "
        f"minor_col={minor_col} comment_col={comment_col}"
    )

    # Scan data rows
    defect_rows: List[Dict[str, Any]] = []
    current_category = ""

    for r_idx in range(header_idx + 1, len(rows)):
        row = rows[r_idx]
        if not row:
            continue

        col_a = row[0] if len(row) > 0 else None

        if _is_end(col_a):
            break
        if _is_total(col_a):
            break

        if _is_category_cell(col_a):
            current_category = _extract_category_label(col_a)

        item = (
            str(row[item_col]).strip()
            if item_col < len(row) and row[item_col] is not None
            else ""
        )
        major = _to_int(row[major_col] if major_col < len(row) else None)
        minor = _to_int(
            row[minor_col]
            if minor_col is not None and minor_col < len(row)
            else None
        )
        comment = (
            str(row[comment_col]).strip()
            if comment_col is not None
            and comment_col < len(row)
            and row[comment_col] is not None
            else ""
        )

        defect_rows.append({
            "category": current_category,
            "item":     item,
            "major":    major,
            "minor":    minor,
            "comment":  comment,
        })

    totals = {
        "major": sum(r["major"] for r in defect_rows),
        "minor": sum(r["minor"] for r in defect_rows),
    }

    logging.info(
        f"[{path.name}] Defects: {len(defect_rows)} rows, totals={totals}"
    )
    return defect_rows, totals