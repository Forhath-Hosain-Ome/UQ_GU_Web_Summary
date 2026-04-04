"""
defect_extractor.py
-------------------
Auto-discovers and extracts the structured defect table from an Excel sheet.

Structure understood from samples
----------------------------------
The defect table always follows this layout:

  Row N   : "Defects" | ... | "Major Defect" | "Minor Defect" | "Comment"
  Row N+1 : "A : Fabrics" | "1.Damage" | ...
  ...
  Row M   : "F : Others" | ... | "3.Others" | ...   ← last data row

Detection strategy
------------------
1. Find the header row containing the cell "Defects" in column A.
2. The "Major Defect", "Minor Defect", and "Comment" column indices are
   discovered from that same header row — NO hardcoded columns.
3. Scan downward, carrying the current category (A:Fabrics, B:Sewing …)
   forward across merged/blank category cells.
4. Stop when the cell in column A equals "DO/Set/Col/Size" or when an
   empty row is followed by a non-defect section (robust sentinel).

Output
------
A list of dicts, one per defect item that has at least one non-zero count:

    [
        {
            "category": "B : Sewing",
            "item":     "3.Pieces not symmetrical",
            "major":    1,
            "minor":    0,
            "comment":  "CUFF POINT UP-DOWN",
        },
        ...
    ]

Also returns the totals dict:
    {"major": 9, "minor": 0}

Both are stored on AuditRecord by the caller.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from pathlib import Path


# ---------------------------------------------------------------------------
# Sentinel – the cell value that marks the end of the defect table
# ---------------------------------------------------------------------------

_END_SENTINEL_PATTERN = re.compile(r"do\s*/\s*set\s*/\s*col\s*/\s*size", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_int(value: Any) -> int:
    """Convert a cell value to int, returning 0 on failure."""
    if value is None:
        return 0
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return 0


def _is_end_sentinel(value: Any) -> bool:
    if value is None:
        return False
    return bool(_END_SENTINEL_PATTERN.search(str(value)))


def _is_category_cell(value: Any) -> bool:
    """True for section-header cells like 'A : Fabrics', 'B : Sewing' etc."""
    if not value:
        return False
    return bool(re.match(r"^[A-F]\s*:", str(value).strip()))


# ---------------------------------------------------------------------------
# Main extractor – uses openpyxl for raw cell access (preserves merged cells)
# ---------------------------------------------------------------------------

def extract_defect_table_from_file(
    path: Path,
    sheet_name: str = "Inspection Report",
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Open *path* with openpyxl and extract the defect table from *sheet_name*.

    Returns
    -------
    (defect_rows, totals)
      defect_rows : list of dicts with keys category/item/major/minor/comment
      totals      : {"major": N, "minor": N}  (summed across all rows)

    Falls back to the first sheet if *sheet_name* is not found.
    """
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception as exc:
        logging.error(f"Cannot open '{path.name}': {exc}")
        return [], {}

    # Resolve sheet
    if sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
    else:
        # Try case-insensitive match
        match = next(
            (s for s in wb.sheetnames if s.lower() == sheet_name.lower()), None
        )
        ws = wb[match] if match else wb[wb.sheetnames[0]]

    # Load all rows into a plain list of lists for easy indexing
    rows = list(ws.iter_rows(values_only=True))

    # ── Step 1: Find the header row ─────────────────────────────────────────
    header_row_idx: Optional[int] = None
    major_col: Optional[int] = None
    minor_col: Optional[int] = None
    comment_col: Optional[int] = None

    for r_idx, row in enumerate(rows):
        if row and str(row[0] or "").strip().lower() == "defects":
            header_row_idx = r_idx
            # Discover Major / Minor / Comment column indices
            for c_idx, cell in enumerate(row):
                if cell is None:
                    continue
                normalised = str(cell).strip().lower()
                if "major" in normalised and major_col is None:
                    major_col = c_idx
                elif "minor" in normalised and minor_col is None:
                    minor_col = c_idx
                elif "comment" in normalised and comment_col is None:
                    comment_col = c_idx
            break

    if header_row_idx is None:
        logging.warning(f"[{path.name}] Defect table header ('Defects') not found")
        return [], {}

    if major_col is None:
        logging.warning(f"[{path.name}] 'Major Defect' column not found in header")
        return [], {}

    logging.info(
        f"[{path.name}] Defect table header at row {header_row_idx + 1}; "
        f"major_col={major_col}, minor_col={minor_col}, comment_col={comment_col}"
    )

    # ── Step 2: Scan data rows ───────────────────────────────────────────────
    defect_rows: List[Dict[str, Any]] = []
    current_category: str = ""

    for r_idx in range(header_row_idx + 1, len(rows)):
        row = rows[r_idx]
        col_a = row[0] if row else None

        # Stop at sentinel (DO/Set/Col/Size section)
        if _is_end_sentinel(col_a):
            break

        # Update current category if this row starts a new section
        if _is_category_cell(col_a):
            current_category = str(col_a).strip()

        # Item name is always in column B (index 1)
        item_name = str(row[1]).strip() if (row and row[1] is not None) else ""
        # if not item_name:
        #     continue  # skip blank rows

        major   = _to_int(row[major_col] if major_col < len(row) else None)
        minor   = _to_int(row[minor_col] if minor_col is not None and minor_col < len(row) else None)
        comment = ""
        if comment_col is not None and comment_col < len(row) and row[comment_col]:
            comment = str(row[comment_col]).strip()

        # Only include rows that have at least some defect data
        # if major == 0 and minor == 0 and not comment:
        #     continue

        defect_rows.append({
            "category": current_category,
            "item":     item_name,
            "major":    major,
            "minor":    minor,
            "comment":  comment,
        })

    # ── Step 3: Compute totals ────────────────────────────────────────────────
    totals = {
        "major": sum(r["major"] for r in defect_rows),
        "minor": sum(r["minor"] for r in defect_rows),
    }

    logging.info(
        f"[{path.name}] Defect table: {len(defect_rows)} item(s) with defects; "
        f"totals={totals}"
    )

    wb.close()
    return defect_rows, totals
