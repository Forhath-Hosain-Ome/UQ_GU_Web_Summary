"""
final_summary/helpers/summary_writer.py
----------------------------------------
Generates the output Excel workbook by filling a pre-built template.

Templates
---------
  SPI-Final-78.xlsx      → 78 defect columns  (format_type="SPI")
  General-Final-37.xlsx  → 37 defect columns  (format_type="REGULAR" / "SWEATER")

Both templates share identical sheet names and prefix column layout.
Only the number of defect columns differs.

Sheet names
-----------
  "Final"    → inspection_type canonical == FINAL
  "Re-Final" → inspection_type canonical == RE-FINAL
  "INLINE"   → inspection_type canonical == INLINE
  (Sample, CMF, etc. → written to the nearest applicable sheet or skipped)

Column layout
-------------
Prefix columns (A–Y, cols 1–25) are identical in every sheet of every template.
Defect columns start at:
  Final / Re-Final  → column Z   (col index FINAL_DEFECT_START_COL)
  INLINE            → column U   (col index INLINE_DEFECT_START_COL)

Data rows start at:
  Final / Re-Final  → row FINAL_DATA_START_ROW   (12)
  INLINE            → row INLINE_DATA_START_ROW  (5)

Totals / summary rows are formula-driven in the template — we do NOT write them.

Called from export_view.py as:
    write_summary(records, defect_items_by_report, output_path,
                  template_path, format_type)
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)


# =============================================================================
# ── LAYOUT CONSTANTS  (edit here to adjust template positions) ──────────────
# =============================================================================

# Row at which data rows begin (1-based, inclusive)
FINAL_DATA_START_ROW:  int = 12   # Final and Re-Final sheets
INLINE_DATA_START_ROW: int = 5    # INLINE sheet (and future SAMPLE)

# Column index (1-based) where defect columns begin
FINAL_DEFECT_START_COL:  int = 26   # col Z
INLINE_DEFECT_START_COL: int = 21   # col U

# Number of defect columns per format/sheet type
DEFECT_COL_COUNT: Dict[str, int] = {
    "SPI":     78,   # SPI-Final-78.xlsx
    "REGULAR": 37,   # General-Final-37.xlsx
    "SWEATER": 37,   # uses General-Final-37.xlsx
    "INLINE":  35,   # INLINE sheet in both templates
}

# =============================================================================
# ── PREFIX COLUMNS  (cols 1–25, A–Y, same in all sheets / templates) ────────
# Each entry: (column_index_1based, record_dict_key)
# =============================================================================

PREFIX_COLUMNS: List[Tuple[int, str]] = [
    (1,  "factory"),
    (2,  "date_of_issue"),
    (3,  "inspection_type"),
    (4,  "factory_in"),
    (5,  "factory_out"),
    (6,  "factory_total_hours"),
    (7,  "audit_start"),
    (8,  "audit_end"),
    (9,  "audit_total_hours"),
    (10, "audit_result"),
    (11, "report_no"),
    (12, "item_name"),
    (13, "style_no"),
    (14, "po_no"),
    (15, "country"),
    (16, "po_qty_pcs"),
    (17, "po_qty_pack"),
    (18, "po_qty_set"),
    (19, "po_wh"),
    (20, "ship_qty"),
    (21, "audit_qty"),
    (22, "acceptable_defect_qty"),
    (23, "defect_qty"),
    (24, "defect_percentage"),
    (25, "person"),
]

# =============================================================================
# ── INLINE PREFIX COLUMNS  (skeleton — fill in when INLINE template is ready)
# INLINE starts defects at col U (21), so its prefix fits in cols A–T (1–20).
# Adjust the list below to match the actual INLINE template column order.
# =============================================================================

INLINE_PREFIX_COLUMNS: List[Tuple[int, str]] = [
    # TODO: confirm exact INLINE prefix column order with template owner
    (1,  "factory"),
    (2,  "date_of_issue"),
    (3,  "inspection_type"),
    (4,  "factory_in"),
    (5,  "factory_out"),
    (6,  "factory_total_hours"),
    (7,  "audit_start"),
    (8,  "audit_end"),
    (9,  "audit_total_hours"),
    (10, "audit_result"),
    (11, "report_no"),
    (12, "item_name"),
    (13, "style_no"),
    (14, "po_no"),
    (15, "country"),
    (16, "audit_qty"),
    (17, "acceptable_defect_qty"),
    (18, "defect_qty"),
    (19, "defect_percentage"),
    (20, "person"),
]

# =============================================================================
# ── INSPECTION-TYPE → SHEET NAME MAP ────────────────────────────────────────
# =============================================================================

# Map canonical type → template sheet name
SHEET_NAME_MAP: Dict[str, str] = {
    "FINAL":    "Final",
    "RE-FINAL": "Re-Final",
    "INLINE":   "INLINE",
    # extend here for SAMPLE, CMF, etc. when sheets are added to the template
}

# Canonical types that use INLINE layout (defect start col, data start row)
INLINE_CANONICAL_TYPES: set = {"INLINE"}

# =============================================================================
# ── CELL STYLE ───────────────────────────────────────────────────────────────
# =============================================================================

_THIN        = Side(style="thin", color="000000")
_BORDER      = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_CENTRE      = Alignment(horizontal="center", vertical="center", wrap_text=True)
_DATA_FONT   = Font(size=9)


# =============================================================================
# ── HELPERS ──────────────────────────────────────────────────────────────────
# =============================================================================

def _canonical_type(itype: str) -> str:
    """Normalise an inspection_type string to one of the canonical keys."""
    u = (itype or "").upper().strip()
    if re.search(r"PRE[\s\-]?FINAL", u):
        return "PRE-FINAL"
    if re.search(r"(?<![A-Z])RE[\s\-]?FINAL|REFINAL", u):
        return "RE-FINAL"
    if re.search(r"\bFINAL\b|SHIPMENT\s*AUDIT|PRE[\s\-]?SHIP", u):
        return "FINAL"
    if re.search(r"IN[\s\-]?LINE", u):
        return "INLINE"
    if re.search(r"\bCMF\b|COUNTER\s*MASTER", u):
        return "CMF"
    if re.search(r"\bSAMPLE\b|PRE[\s\-]?PROD|\bPP\b", u):
        return "SAMPLE"
    return "UNKNOWN"


def _is_inline_sheet(canonical: str) -> bool:
    return canonical in INLINE_CANONICAL_TYPES


def _defect_start_col(canonical: str) -> int:
    return INLINE_DEFECT_START_COL if _is_inline_sheet(canonical) else FINAL_DEFECT_START_COL


def _data_start_row(canonical: str) -> int:
    return INLINE_DATA_START_ROW if _is_inline_sheet(canonical) else FINAL_DATA_START_ROW


def _prefix_columns(canonical: str) -> List[Tuple[int, str]]:
    return INLINE_PREFIX_COLUMNS if _is_inline_sheet(canonical) else PREFIX_COLUMNS


def _cell_val(value: Any) -> Any:
    """Return None for empty/dash values so template cells stay clean."""
    if value is None or value == "" or value == "-":
        return None
    return value


def _safe_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return None


# =============================================================================
# ── DEFECT COLUMN PLAN ───────────────────────────────────────────────────────
# =============================================================================

def _build_defect_plan(
    defect_items_by_report: Dict[int, List[Dict[str, Any]]],
    report_ids: List[int],
) -> List[Tuple[str, str]]:
    """
    Return sorted [(category, item), ...] for the given report subset.
    Used to map each defect type to a column offset within the template.
    """
    seen: Dict[Tuple[str, str], None] = {}
    for rid in report_ids:
        for d in defect_items_by_report.get(rid, []):
            cat  = (d.get("category") or "").strip()
            item = (d.get("item") or "").strip()
            if cat and item:
                seen[(cat, item)] = None
    return sorted(seen.keys())


# =============================================================================
# ── SHEET WRITER ─────────────────────────────────────────────────────────────
# =============================================================================

def _write_sheet(
    ws,
    records: List[Dict[str, Any]],
    defect_items_by_report: Dict[int, List[Dict[str, Any]]],
    defect_plan: List[Tuple[str, str]],
    canonical: str,
) -> int:
    """
    Fill one template sheet with data rows.

    Parameters
    ----------
    ws                     : openpyxl Worksheet (already open from template)
    records                : list of record dicts for this sheet
    defect_items_by_report : {report_id: [defect rows]}
    defect_plan            : ordered [(category, item)] for defect column mapping
    canonical              : canonical inspection type ("FINAL", "RE-FINAL", "INLINE" …)

    Returns the number of rows written.
    """
    start_row    = _data_start_row(canonical)
    defect_start = _defect_start_col(canonical)
    prefix_cols  = _prefix_columns(canonical)

    # Build (category, item) → column_index mapping
    defect_col_map: Dict[Tuple[str, str], int] = {
        key: defect_start + offset
        for offset, key in enumerate(defect_plan)
    }

    current_row = start_row
    for rec in records:
        rid = rec.get("report_id")

        # ── Prefix columns ────────────────────────────────────────────────────
        for col_idx, key in prefix_cols:
            val  = _cell_val(rec.get(key))
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.font      = _DATA_FONT
            cell.alignment = _CENTRE
            cell.border    = _BORDER

        # ── Defect columns ────────────────────────────────────────────────────
        defect_lookup: Dict[Tuple[str, str], int] = {
            (d["category"].strip(), d["item"].strip()): int(d.get("major_count", 0) or 0)
            for d in defect_items_by_report.get(rid, [])
            if d.get("category") and d.get("item")
        }

        for (cat, item), col_idx in defect_col_map.items():
            count = defect_lookup.get((cat, item))
            cell  = ws.cell(
                row=current_row,
                column=col_idx,
                value=count if count else None,
            )
            cell.font      = _DATA_FONT
            cell.alignment = _CENTRE
            cell.border    = _BORDER

        current_row += 1

    rows_written = current_row - start_row
    logger.info(
        "Sheet '%s': wrote %d data row(s) starting at row %d, "
        "defects from col %s (%d columns)",
        ws.title, rows_written, start_row,
        get_column_letter(defect_start), len(defect_plan),
    )
    return rows_written


# =============================================================================
# ── PUBLIC API ────────────────────────────────────────────────────────────────
# =============================================================================

def write_summary(
    records: List[Dict[str, Any]],
    defect_items_by_report: Dict[int, List[Dict[str, Any]]],
    output_path: Path,
    template_path: Path,
    format_type: str = "SPI",
) -> None:
    """
    Fill the pre-built Excel template and save to output_path.

    Parameters
    ----------
    records                : list of record dicts (one per AuditReport row)
    defect_items_by_report : {report_id: [{category, item, major_count, …}]}
    output_path            : destination .xlsx path (parent dir created if needed)
    template_path          : absolute path to the template .xlsx file
    format_type            : "SPI" | "REGULAR" | "SWEATER"
                             controls which template to use (caller selects path)
    """
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    # ── Load template (keep formulas intact) ──────────────────────────────────
    wb = openpyxl.load_workbook(str(template_path), data_only=False)

    # ── Group records by canonical inspection type ─────────────────────────────
    by_canonical: Dict[str, List[Dict[str, Any]]] = {}
    for rec in records:
        key = _canonical_type(rec.get("inspection_type") or "")
        by_canonical.setdefault(key, []).append(rec)

    # Process order: FINAL first, then RE-FINAL, then INLINE, then others
    process_order = ["FINAL", "RE-FINAL", "INLINE"] + [
        k for k in by_canonical if k not in ("FINAL", "RE-FINAL", "INLINE")
    ]

    sheets_written = 0
    skipped_types: List[str] = []

    for canonical in process_order:
        type_records = by_canonical.get(canonical)
        if not type_records:
            continue

        sheet_name = SHEET_NAME_MAP.get(canonical)
        if not sheet_name:
            skipped_types.append(canonical)
            logger.warning(
                "No template sheet mapped for canonical type '%s' "
                "(%d record(s) skipped). Add an entry to SHEET_NAME_MAP "
                "and create the sheet in the template to include these.",
                canonical, len(type_records),
            )
            continue

        if sheet_name not in wb.sheetnames:
            skipped_types.append(canonical)
            logger.warning(
                "Sheet '%s' not found in template '%s'. "
                "Skipping %d record(s) with type '%s'.",
                sheet_name, template_path.name, len(type_records), canonical,
            )
            continue

        ws = wb[sheet_name]

        # Build defect plan for this sheet's records only
        report_ids  = [r["report_id"] for r in type_records]
        defect_plan = _build_defect_plan(defect_items_by_report, report_ids)

        _write_sheet(
            ws=ws,
            records=type_records,
            defect_items_by_report=defect_items_by_report,
            defect_plan=defect_plan,
            canonical=canonical,
        )
        sheets_written += 1

    if not sheets_written:
        raise ValueError(
            "No records could be written — none of the canonical inspection "
            "types matched a sheet in the template."
        )

    if skipped_types:
        logger.warning(
            "The following inspection types had no matching template sheet "
            "and were skipped: %s", skipped_types,
        )

    # ── Save ──────────────────────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(output_path))
    logger.info(
        "Summary saved → %s  (template=%s, sheets_written=%d)",
        output_path, template_path.name, sheets_written,
    )


# =============================================================================
# ── LEGACY HELPERS  (kept for backward compatibility with other callers) ─────
# =============================================================================

def build_defect_column_plan(
    defect_rows_by_report: Dict[int, List[Dict[str, Any]]],
) -> List[Tuple[str, str]]:
    """
    Build a global sorted [(category, item)] plan across all reports.
    Used by any caller that needs the full plan before splitting by sheet.
    """
    seen: Dict[Tuple[str, str], None] = {}
    for rows in defect_rows_by_report.values():
        for d in rows:
            if isinstance(d, dict):
                cat  = (d.get("category") or "").strip()
                item = (d.get("item") or "").strip()
                if cat and item:
                    seen[(cat, item)] = None
    return sorted(seen.keys(), key=lambda x: (x[0], x[1]))