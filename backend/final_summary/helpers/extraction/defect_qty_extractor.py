"""
defect_qty_extractor.py
-----------------------
Fallback extraction strategy for the defect quantity field.

Primary extraction (via rule_extractor) matches the "Major Defects" header.
If that fails, this module's custom logic scans for the *second* occurrence of
any cell containing the word "major" and reads the integer to its right.

Why second?  Audit sheets typically have:
  Row N   – "Major" as a column *header* in the defect table
  Row M   – "Major" as a *sub-total* row  ← we want this one
"""

import logging
import re
from typing import Tuple, List
from ..core.cell_grid import CellGrid

# ---------------------------------------------------------------------------
# Text helper (local, keeps the module self-contained)
# ---------------------------------------------------------------------------

def _normalize(value: str) -> str:
    text = value.lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()

# ---------------------------------------------------------------------------
# Label finder
# ---------------------------------------------------------------------------

def _find_major_labels(grid: CellGrid) -> list[Tuple[int, int, str]]:
    """
    Return all (row, col, raw_value) tuples where the cell contains the
    word "major", sorted top-to-bottom.
    """
    major_labels = []
    
    for row in range(grid.nrows):
        for col in range(grid.ncols):
            cell_val = grid.get(row, col)
            if cell_val and "major" in _normalize(cell_val):
                major_labels.append((row, col, cell_val))
    
    major_labels.sort(key=lambda x: x[0])
    logging.info(f"Found {len(major_labels)} 'Major' labels: {[(r, c, v) for r, c, v in major_labels]}")
    return major_labels

# ---------------------------------------------------------------------------
# Custom (fallback) extractor
# ---------------------------------------------------------------------------

def _extract_defect_qty_custom(grid: CellGrid, known_audit_qty: str = "") -> str:
    """
    Scan for the second "major" occurrence and return the integer value
    found to its right.  Returns "" if not found.
    """
    major_labels = _find_major_labels(grid)
    
    if len(major_labels) < 2:
        logging.warning(f"Found only {len(major_labels)} 'Major' label(s), need at least 2 for fallback")
        return ""

    _, second_major_col, _ = major_labels[1]
    second_row = major_labels[1][0]
    
    # Scan up to 5 cells to the right of the second "Major" cell
    for c in range(second_major_col + 1, min(second_major_col + 6, grid.ncols)):
        raw = grid.get(second_row, c).strip()
        if not raw:
            continue
        try:
            # Accept integers only (defect count should be a whole number)
            int(float(raw))
            return raw
        except (ValueError, TypeError):
            continue
    return ""

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_defect_qty_with_fallback(grid: CellGrid, primary_value: str, audit_qty: str = "") -> str:
    """
    Return *primary_value* if it is non-empty; otherwise run the custom
    fallback search and return its result (or "").

    Parameters
    ----------
    grid          : CellGrid for the first sheet
    primary_value : value already found by the standard rule extractor
    """
    if primary_value and primary_value.strip():
        return primary_value
    
    logging.info("defect_qty primary extraction empty – running fallback")
    return _extract_defect_qty_custom(grid, audit_qty)