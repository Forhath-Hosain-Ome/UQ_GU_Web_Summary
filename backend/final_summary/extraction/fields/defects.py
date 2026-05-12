"""
defects.py
----------
Extracts the defect table from an audit report Excel sheet and maps every
row to its canonical defect_master entry so data is saved consistently.

────────────────────────────────────────────────────────────────────────────
COLUMN LAYOUT VARIANTS
────────────────────────────────────────────────────────────────────────────

The defect table header can appear in two layouts:

  Layout 5-col:   Category | Item | Major | Minor | Comment
  Layout 4-col:             Item | Major | Minor | Comment
                  (no Category column — item col contains both category
                   separator rows and defect item rows mixed together)

REQUIRED columns (hard stop if any are missing):
  Major, Minor, Comment  — all three must be found via synonym matching.

OPTIONAL columns:
  Category  — used only to detect category separator rows more reliably.
  Item      — used only to COUNT item rows for validation against
              defect_column_count. The actual defect name always comes
              from defect_master.py by position, never from Excel text.

────────────────────────────────────────────────────────────────────────────
HEADER VALIDITY RULE
────────────────────────────────────────────────────────────────────────────

  Major + Minor + Comment must ALL be found in the header row.
  If any one of these three is missing → table is invalid → abort.

────────────────────────────────────────────────────────────────────────────
CATEGORY / ITEM ROW DETECTION
────────────────────────────────────────────────────────────────────────────

A data row is a CATEGORY SEPARATOR (skip, don't count as item) when ANY of:

  1. The category column (if present) has a non-None/non-empty value.
  2. The item column cell is None — a vertical merge shadow, which means
     the cell above spanned multiple rows (how category headers are
     structured in some templates).
  3. The relevant cell (category col if present, else item col, else col A)
     matches a known category text pattern:
       Format A (SPI):  "A : Fabrics", "B : Sewing", …
       Format B (PQC):  "A素材不良\n Material Defects", …

Category separator rows do NOT consume an item_no slot.
All other rows are item rows, counted positionally → item_no 1, 2, 3 …

────────────────────────────────────────────────────────────────────────────
COUNT VALIDATION
────────────────────────────────────────────────────────────────────────────

  expected_count = defect_column_count  (from BuyerFactoryPair)
  actual_count   = number of item rows collected

  A warning is logged if they differ; extraction still returns what was
  found so the caller can decide how to handle partial results.

────────────────────────────────────────────────────────────────────────────
CONFIGURATION  (edit at the top of this file)
────────────────────────────────────────────────────────────────────────────
  _COL_SYNONYMS          add/remove synonyms per column role
  _CATEGORY_FORMAT_A/B   regex patterns for category separator rows
  defect_master.py       canonical names / add new templates there

────────────────────────────────────────────────────────────────────────────
RETURNS
────────────────────────────────────────────────────────────────────────────
  (defect_rows, totals, meta)

  defect_rows : List[dict]  — one entry per item row
    {
        "item_no":       int,   # 1-based position within this template
        "category_code": str,   # from defect_master (e.g. "A")
        "category":      str,   # canonical category label
        "item":          str,   # canonical item name from defect_master
        "major":         int,
        "minor":         int,
        "comment":       str,
    }

  totals : dict  {"major": int, "minor": int}

  meta : dict
    {
        "template_key":      str | None,  # e.g. "TEMPLATE_37"
        "expected_count":    int,
        "actual_count":      int,
        "count_ok":          bool,
        "has_category_col":  bool,   # True if a Category column was found
        "has_item_col":      bool,   # True if an Item column was found
    }
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openpyxl

from final_summary.extraction.core import get_template_key, get_items, get_categories

# ---------------------------------------------------------------------------
# Synonym configuration — edit here to support new column label variants
# ---------------------------------------------------------------------------

# All synonyms are matched case-insensitively after stripping whitespace.
_COL_SYNONYMS: dict[str, list[str]] = {
    "category": [
        "category",
        "cat",
        "cat.",
        "defect category",
        "defect type",
        "type",
        "classification",
        "カテゴリ",
        "分類",
    ],
    "item": [
        "defects",
        "defect",
        "defect name",
        "defect item",
        "defect description",
        "item",
        "items",
        "description",
        "不良項目",
        "不良内容",
        "不良名",
    ],
    "major": [
        "major",
        "maj",
        "critical",
        "cr",
        "major defect",
        "major defects",
        "重大",
        "重欠点",
    ],
    "minor": [
        "minor",
        "min",
        "minor defect",
        "minor defects",
        "軽微",
        "軽欠点",
    ],
    "comment": [
        "comment",
        "comments",
        "remark",
        "remarks",
        "note",
        "notes",
        "observation",
        "備考",
        "コメント",
    ],
}

# Regex patterns for category separator row detection
_CATEGORY_FORMAT_A = re.compile(r"^[A-F]\s*:", re.IGNORECASE)  # "A : Fabrics"
_CATEGORY_FORMAT_B = re.compile(r"^[A-F][^\x00-\x7F]")         # "A素材不良…"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _norm(value: Any) -> str:
    """Lowercase, strip, collapse internal whitespace."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _to_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return 0


def _matches_synonym(cell_value: Any, synonyms: list[str]) -> bool:
    """True if the normalised cell text exactly equals any synonym."""
    return _norm(cell_value) in synonyms


def _looks_like_category(value: Any) -> bool:
    """True when the cell value matches a known category separator pattern."""
    if not value:
        return False
    s = str(value).strip()
    return bool(_CATEGORY_FORMAT_A.match(s) or _CATEGORY_FORMAT_B.match(s))


def _cell(row: tuple, col: Optional[int]) -> Any:
    """Safe row[col] — returns None when col is None or out of range."""
    if col is None or col >= len(row):
        return None
    return row[col]


# ---------------------------------------------------------------------------
# Step 1 — Header discovery
# ---------------------------------------------------------------------------

def _find_header(
    rows: list[tuple],
) -> Tuple[Optional[int], dict[str, Optional[int]]]:
    """
    Scan every row for the defect table header via synonym matching.

    Validity rule
    -------------
    Major + Minor + Comment must ALL be found.
    Category and Item are optional.

    Returns
    -------
    (header_row_idx, col_map)
      col_map keys: "category", "item", "major", "minor", "comment"
      Values are 0-based column indices or None if not found.
      header_row_idx is None when no valid header row exists.
    """
    for r_idx, row in enumerate(rows):
        if not row:
            continue

        col_map: dict[str, Optional[int]] = {
            "category": None,
            "item":     None,
            "major":    None,
            "minor":    None,
            "comment":  None,
        }

        for c_idx, cell in enumerate(row):
            if cell is None:
                continue
            for role, synonyms in _COL_SYNONYMS.items():
                # First match wins for each role
                if col_map[role] is None and _matches_synonym(cell, synonyms):
                    col_map[role] = c_idx

        # Hard requirement: major AND minor AND comment must all be present
        if all(col_map[r] is not None for r in ("major", "minor", "comment")):
            # Rule: The cell left to the 'Major' column is typically the 'Item' column
            # if not explicitly found via synonym matching.
            if col_map["item"] is None and col_map["major"] is not None and col_map["major"] > 0:
                col_map["item"] = col_map["major"] - 1

            found_roles = [r for r, v in col_map.items() if v is not None]
            logging.info(
                f"Defect header found at row {r_idx + 1}: "
                f"roles={found_roles}  "
                f"cat={col_map.get('category')} item={col_map.get('item')} "
                f"major={col_map.get('major')} minor={col_map.get('minor')} "
                f"comment={col_map['comment']}"
            )
            return r_idx, col_map

    return None, {
        "category": None, "item": None,
        "major": None, "minor": None, "comment": None,
    }


# ---------------------------------------------------------------------------
# Step 2 — Category / item row classification
# ---------------------------------------------------------------------------

def _is_category_row(
    row: tuple,
    category_col: Optional[int],
    item_col: Optional[int],
) -> bool:
    """
    Return True if this data row is a category separator to be skipped.

    Rules (any one is sufficient):
      1. Category column present and its cell is non-None / non-empty.
      2. Item column present and its cell is None
         → vertical merge shadow of a category header spanning rows above.
      3. The most relevant cell (category col → item col → col A) matches
         a known category text pattern.
    """
    cat_val  = _cell(row, category_col)
    item_val = _cell(row, item_col)

    # Rule 1 — explicit category column has a value in this row
    if category_col is not None and cat_val not in (None, ""):
        return True

    # Rule 2 — item cell is None: vertical merge shadow of a category header
    if item_col is not None and item_val is None:
        return True

    # Rule 3 — pattern match on the most informative available cell
    check_val = (
        cat_val  if category_col is not None else
        item_val if item_col     is not None else
        _cell(row, 0)
    )
    return _looks_like_category(check_val)


# ---------------------------------------------------------------------------
# Step 3 — Data extraction with positional mapping
# ---------------------------------------------------------------------------

def _extract_rows(
    rows: list[tuple],
    header_idx: int,
    col_map: dict[str, Optional[int]],
    defect_column_count: int,
    template_key: str | None,
) -> Tuple[List[Dict[str, Any]], Dict[str, int], Dict[str, Any]]:
    """
    Iterate data rows after the header:
      - Skip category separator rows (no item_no consumed).
      - Map each remaining row positionally to defect_master by item_no.
      - Stop after collecting exactly defect_column_count item rows.

    Returns (defect_rows, totals, meta).
    """
    master_items = get_items(template_key)    if template_key else []
    master_cats  = get_categories(template_key) if template_key else {}

    # Ensure items are ordered by sort_order for positional mapping.
    # We map the Excel row position to the sort_order because item_no may 
    # restart per category in some templates (e.g. TEMPLATE_78).
    sorted_master = sorted(master_items, key=lambda x: x.get("sort_order", 0))

    category_col = col_map["category"]
    item_col     = col_map["item"]
    major_col    = col_map["major"]
    minor_col    = col_map["minor"]
    comment_col  = col_map["comment"]

    defect_rows:  List[Dict[str, Any]] = []
    item_position = 0   # 1-based; only incremented for real item rows

    for r_idx in range(header_idx + 1, len(rows)):
        # Stop once we have exactly defect_column_count items
        if item_position >= defect_column_count:
            break

        row = rows[r_idx]
        if not row:
            continue

        if _is_category_row(row, category_col, item_col):
            logging.debug(f"  Row {r_idx + 1}: category separator → skipped")
            continue

        item_position += 1  # positional item_no (1-based)

        # Canonical names always from defect_master — never from Excel text
        master_entry = sorted_master[item_position - 1] if item_position <= len(sorted_master) else None
        
        # Use item_no from master if available (id and serial)
        item_id_serial = master_entry["item_no"] if (master_entry and "item_no" in master_entry) else item_position

        category_code  = master_entry["category_code"] if master_entry else ""
        category_label = (
            master_cats.get(category_code, {}).get("label", "")
            if category_code else ""
        )
        canonical_name = (
            master_entry["name"] if master_entry
            else f"Item {item_position}"   # fallback when template unknown
        )

        major   = _to_int(_cell(row, major_col))
        minor   = _to_int(_cell(row, minor_col))
        comment = str(_cell(row, comment_col) or "").strip()

        defect_rows.append({
            "item_no":       item_id_serial,
            "category_code": category_code,
            "category":      category_label,
            "item":          canonical_name,
            "major":         major,
            "minor":         minor,
            "comment":       comment,
        })

    totals = {
        "major": sum(r["major"] for r in defect_rows),
        "minor": sum(r["minor"] for r in defect_rows),
    }

    actual_count = len(defect_rows)
    count_ok     = actual_count == defect_column_count
    if not count_ok:
        logging.warning(
            f"Defect count mismatch: expected {defect_column_count}, "
            f"got {actual_count}."
        )

    meta: Dict[str, Any] = {
        "template_key":     template_key,
        "expected_count":   defect_column_count,
        "actual_count":     actual_count,
        "count_ok":         count_ok,
        "has_category_col": category_col is not None,
        "has_item_col":     item_col     is not None,
    }

    return defect_rows, totals, meta


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract(
    path: Path,
    sheet_name: Optional[str] = None,
    grid=None,                    # unused — kept for uniform extractor signature
    defect_column_count: int = 37,
) -> Tuple[List[Dict[str, Any]], Dict[str, int], Dict[str, Any]]:
    """
    Extract the defect table from *path* / *sheet_name* and map every row
    to its canonical defect_master entry.

    Parameters
    ----------
    path                : Path to the Excel file
    sheet_name          : Preferred sheet; falls back to scanning all sheets
    grid                : Ignored — openpyxl is used directly for raw access
    defect_column_count : From BuyerFactoryPair.defect_column_count.
                          Controls how many item rows to read and selects
                          the correct template from defect_master.py.

    Returns
    -------
    (defect_rows, totals, meta)  — see module docstring for field details.
    """
    def _empty_meta(tkey: str | None) -> Dict[str, Any]:
        return {
            "template_key":     tkey,
            "expected_count":   defect_column_count,
            "actual_count":     0,
            "count_ok":         False,
            "has_category_col": False,
            "has_item_col":     False,
        }

    # Resolve template key (tolerance ±4 applied inside get_template_key)
    template_key = get_template_key(defect_column_count)
    if template_key is None:
        logging.warning(
            f"[{path.name}] No defect_master template for "
            f"defect_column_count={defect_column_count}. "
            f"Items will use positional fallback names."
        )
    else:
        logging.info(
            f"[{path.name}] defect_column_count={defect_column_count} "
            f"→ template '{template_key}'"
        )

    # Open workbook in read_only mode so that vertical merge shadows
    # correctly return None (used by _is_category_row Rule 2).
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception as exc:
        logging.error(f"defects.extract: cannot open '{path.name}': {exc}")
        return [], {}, _empty_meta(template_key)

    # Sheet search order: preferred first, then all others
    sheet_names  = wb.sheetnames
    search_order: list[str] = []
    if sheet_name and sheet_name in sheet_names:
        search_order.append(sheet_name)
    search_order.extend(s for s in sheet_names if s not in search_order)

    rows:       list[tuple]              = []
    header_idx: Optional[int]            = None
    col_map:    dict[str, Optional[int]] = {
        "category": None, "item": None,
        "major": None, "minor": None, "comment": None,
    }

    for s_name in search_order:
        ws        = wb[s_name]
        temp_rows = list(ws.iter_rows(values_only=True))
        h_idx, c_map = _find_header(temp_rows)
        if h_idx is not None:
            rows       = temp_rows
            header_idx = h_idx
            col_map    = c_map
            logging.info(
                f"[{path.name}] Defect table on sheet '{s_name}' "
                f"(header row {h_idx + 1})"
            )
            break

    wb.close()

    if header_idx is None:
        logging.warning(
            f"[{path.name}] Defect header not found — "
            f"major + minor + comment columns not all present in any row "
            f"via synonym matching."
        )
        return [], {}, _empty_meta(template_key)

    defect_rows, totals, meta = _extract_rows(
        rows, header_idx, col_map, defect_column_count, template_key
    )

    logging.info(
        f"[{path.name}] Defects: "
        f"{meta['actual_count']}/{meta['expected_count']} rows  "
        f"count_ok={meta['count_ok']}  totals={totals}  "
        f"layout={'5-col (cat+item)' if meta['has_category_col'] else '4-col (item only)'}"
    )

    return defect_rows, totals, meta