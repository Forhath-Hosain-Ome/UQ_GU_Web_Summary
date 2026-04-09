"""
final_summary/helpers/summary_writer.py
----------------------------------------
Generates the output Excel workbook from queried DB records.

Called from export_view.py:
    write_summary(records, defect_map, output_path)

Arguments
---------
records     : list of dicts produced by _build_records_for_writer()
              Keys match the PREFIX_COLUMNS field names below.
defect_map  : {report_id: [{"category", "item", "major_count", "minor_count"}, ...]}
output_path : pathlib.Path — where to write the .xlsx file

Output structure
----------------
- One sheet per inspection_type (FINAL, RE-FINAL, PRE-FINAL, INLINE, CMF, SAMPLE, UNKNOWN)
- Row 1 : title block + defect-category group headers (merged)
- Row 2-3 : rotated column headers (merged, yellow)
- Row 4 : totals row (grey)
- Row 5+ : data rows
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)


# ── Fixed prefix columns ──────────────────────────────────────────────────────
# (dict_key, column_header_label)
PREFIX_COLUMNS: List[Tuple[str, str]] = [
    ("factory",               "Factory"),
    ("date_of_issue",         "Date of Issue"),
    ("inspection_type",       "Inspection Type"),
    ("factory_in",            "Factory In"),
    ("factory_out",           "Factory Out"),
    ("factory_total_hours",   "Factory Hours"),
    ("audit_start",           "Audit Start"),
    ("audit_end",             "Audit End"),
    ("audit_total_hours",     "Audit Hours"),
    ("audit_result",          "Result"),
    ("report_no",             "Report No"),
    ("item_name",             "Item Name"),
    ("style_no",              "Style NO."),
    ("po_no",                 "PO-NO"),
    ("country",               "Country"),
    ("po_qty_pcs",            "PO Qty (PCS)"),
    ("po_qty_pack",           "PO Qty (PACK)"),
    ("po_qty_set",            "PO Qty (SET)"),
    ("po_wh",                 "PO WH"),
    ("ship_qty",              "Ship Qty"),
    ("audit_qty",             "Audit Qty"),
    ("acceptable_defect_qty", "Accept. Defect"),
    ("defect_qty",            "Defect Qty"),
    ("defect_percentage",     "Defect %"),
    ("person",                "Person"),
]

# ── Cell styles ───────────────────────────────────────────────────────────────
_THIN        = Side(style="thin", color="000000")
_BORDER      = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_CENTRE      = Alignment(horizontal="center", vertical="center", wrap_text=True)
_LEFT        = Alignment(horizontal="left",   vertical="center")
_ROTATE_UP   = Alignment(horizontal="center", vertical="center", textRotation=90, wrap_text=True)

_FONT_HDR    = Font(bold=True, size=9, color="000000")
_FONT_DATA   = Font(size=9)
_FONT_TOTAL  = Font(bold=True, size=9, color="FFFFFF")
_FONT_TITLE  = Font(bold=True, size=9, color="000000")

_FILL_HEADER = PatternFill("solid", fgColor="FFFF00")   # yellow
_FILL_TOTALS = PatternFill("solid", fgColor="808080")   # grey
_FILL_TITLE  = PatternFill("solid", fgColor="FFFFFF")   # white

# ── Column widths ─────────────────────────────────────────────────────────────
_DEFECT_COL_WIDTH   = 6.0
_DEFAULT_COL_WIDTH  = 10.0
_COL_WIDTHS: Dict[str, float] = {
    "factory": 26.0, "date_of_issue": 10.0, "inspection_type": 22.0,
    "factory_in": 10.0, "factory_out": 10.0, "factory_total_hours": 7.0,
    "audit_start": 10.0, "audit_end": 10.0, "audit_total_hours": 7.0,
    "audit_result": 6.0, "report_no": 18.0, "item_name": 26.0,
    "style_no": 15.0, "po_no": 18.0, "country": 9.0,
    "po_qty_pcs": 9.0, "po_qty_pack": 9.0, "po_qty_set": 9.0,
    "po_wh": 12.0, "ship_qty": 8.0, "audit_qty": 8.0,
    "acceptable_defect_qty": 5.0, "defect_qty": 6.0,
    "defect_percentage": 9.0, "person": 5.0,
}

# ── Inspection-type normalisation ─────────────────────────────────────────────
_DISPLAY_ORDER = ["FINAL", "RE-FINAL", "PRE-FINAL", "INLINE", "CMF", "SAMPLE", "UNKNOWN"]


def _canonical_type(itype: str) -> str:
    u = (itype or "").upper().strip()
    if re.search(r"PRE[\s\-]?FINAL",                          u): return "PRE-FINAL"
    if re.search(r"(?<![A-Z])RE[\s\-]?FINAL|REFINAL",         u): return "RE-FINAL"
    if re.search(r"\bFINAL\b|SHIPMENT\s*AUDIT|PRE[\s\-]?SHIP", u): return "FINAL"
    if re.search(r"IN[\s\-]?LINE",                             u): return "INLINE"
    if re.search(r"\bCMF\b|COUNTER\s*MASTER",                  u): return "CMF"
    if re.search(r"\bSAMPLE\b|PRE[\s\-]?PROD|\bPP\b",         u): return "SAMPLE"
    return "UNKNOWN"


# ── Defect column plan ────────────────────────────────────────────────────────

def _build_defect_plan(
    defect_map: Dict[int, List[Dict]],
    report_ids: List[int],
) -> List[Tuple[str, str]]:
    """Return sorted [(category, item), ...] pairs for the given report subset."""
    seen: Dict[Tuple[str, str], None] = {}
    for rid in report_ids:
        for d in defect_map.get(rid, []):
            cat  = (d.get("category") or "").strip()
            item = (d.get("item") or "").strip()
            if cat and item:
                seen[(cat, item)] = None
    return sorted(seen.keys())


# ── Per-sheet writer ──────────────────────────────────────────────────────────

def _write_sheet(
    ws,
    records: List[Dict[str, Any]],
    defect_map: Dict[int, List[Dict]],
    defect_plan: List[Tuple[str, str]],
) -> None:
    n_prefix = len(PREFIX_COLUMNS)
    n_defect = len(defect_plan)
    n_total  = n_prefix + n_defect

    # ── Row 1: title + defect category group headers ──────────────────────────
    ws.row_dimensions[1].height = 22

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_prefix)
    c = ws.cell(row=1, column=1, value="出荷前監査報告書")
    c.font = _FONT_TITLE; c.fill = _FILL_TITLE; c.alignment = _CENTRE; c.border = _BORDER

    if defect_plan:
        col = n_prefix + 1
        i   = 0
        while i < len(defect_plan):
            cat = defect_plan[i][0]
            j   = i
            while j < len(defect_plan) and defect_plan[j][0] == cat:
                j += 1
            span = j - i
            if span > 1:
                ws.merge_cells(start_row=1, start_column=col,
                               end_row=1,   end_column=col + span - 1)
            c = ws.cell(row=1, column=col, value=cat)
            c.font = _FONT_TITLE; c.fill = _FILL_TITLE
            c.alignment = _CENTRE; c.border = _BORDER
            col += span
            i    = j

    # ── Rows 2-3: rotated column headers (merged vertically) ─────────────────
    ws.row_dimensions[2].height = 150
    ws.row_dimensions[3].height = 1

    def _header(col_idx: int, label: str) -> None:
        try:
            ws.unmerge_cells(start_row=2, start_column=col_idx,
                             end_row=3,   end_column=col_idx)
        except Exception:
            pass
        ws.merge_cells(start_row=2, start_column=col_idx,
                       end_row=3,   end_column=col_idx)
        c = ws.cell(row=2, column=col_idx, value=label)
        c.font = _FONT_HDR; c.fill = _FILL_HEADER
        c.alignment = _ROTATE_UP; c.border = _BORDER

    for col_idx, (_, label) in enumerate(PREFIX_COLUMNS, start=1):
        _header(col_idx, label)
    for col_idx, (_, item) in enumerate(defect_plan, start=n_prefix + 1):
        _header(col_idx, item)

    # ── Row 4: totals placeholder (filled after data rows) ───────────────────
    ws.row_dimensions[4].height = 16
    c = ws.cell(row=4, column=1, value="合計")
    c.font = _FONT_TOTAL; c.fill = _FILL_TOTALS; c.alignment = _LEFT; c.border = _BORDER
    for col_idx in range(2, n_total + 1):
        c = ws.cell(row=4, column=col_idx)
        c.fill = _FILL_TOTALS; c.border = _BORDER

    # Column indices for summed fields
    _col_of = {key: i + 1 for i, (key, _) in enumerate(PREFIX_COLUMNS)}
    ship_col   = _col_of.get("ship_qty")
    audit_col  = _col_of.get("audit_qty")
    defect_col = _col_of.get("defect_qty")

    total_ship   = 0
    total_audit  = 0
    total_defect = 0
    defect_col_totals: Dict[int, int] = {}

    # ── Rows 5+: data ─────────────────────────────────────────────────────────
    row = 5
    for rec in records:
        rid = rec.get("report_id")

        # Build (cat, item) → major_count lookup for this report
        defect_lookup: Dict[Tuple[str, str], int] = {
            (d["category"].strip(), d["item"].strip()): int(d.get("major_count", 0) or 0)
            for d in defect_map.get(rid, [])
            if d.get("category") and d.get("item")
        }

        # Prefix columns
        for col_idx, (key, _) in enumerate(PREFIX_COLUMNS, start=1):
            val = rec.get(key)
            c   = ws.cell(row=row, column=col_idx, value=val if val not in (None, "") else None)
            c.font = _FONT_DATA; c.alignment = _CENTRE; c.border = _BORDER

        # Defect columns
        for col_idx, (cat, item) in enumerate(defect_plan, start=n_prefix + 1):
            count = defect_lookup.get((cat, item))
            c = ws.cell(row=row, column=col_idx, value=count if count else None)
            c.font = _FONT_DATA; c.alignment = _CENTRE; c.border = _BORDER
            if count:
                defect_col_totals[col_idx] = defect_col_totals.get(col_idx, 0) + count

        # Accumulate numeric totals
        for field, acc_ref in [("ship_qty", "ship"), ("audit_qty", "audit"), ("defect_qty", "defect")]:
            try:
                v = int(rec.get(field) or 0)
                if field == "ship_qty":   total_ship   += v
                if field == "audit_qty":  total_audit  += v
                if field == "defect_qty": total_defect += v
            except (TypeError, ValueError):
                pass

        ws.row_dimensions[row].height = 16
        row += 1

    # Fill totals row
    def _total_cell(col_idx: int, value: int) -> None:
        c = ws.cell(row=4, column=col_idx, value=value)
        c.font = _FONT_TOTAL; c.fill = _FILL_TOTALS
        c.alignment = _CENTRE; c.border = _BORDER

    if ship_col:   _total_cell(ship_col,   total_ship)
    if audit_col:  _total_cell(audit_col,  total_audit)
    if defect_col: _total_cell(defect_col, total_defect)
    for col_idx, total in defect_col_totals.items():
        _total_cell(col_idx, total)

    # ── Column widths ─────────────────────────────────────────────────────────
    for col_idx, (key, _) in enumerate(PREFIX_COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = _COL_WIDTHS.get(key, _DEFAULT_COL_WIDTH)
    for col_idx in range(n_prefix + 1, n_prefix + n_defect + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = _DEFECT_COL_WIDTH

    ws.freeze_panes = "A5"


# ── Public API ────────────────────────────────────────────────────────────────

def write_summary(
    records: List[Dict[str, Any]],
    defect_map: Dict[int, List[Dict[str, Any]]],
    output_path: Path,
) -> None:
    """
    Build the multi-sheet Excel summary and save to output_path.

    Parameters
    ----------
    records     : list of dicts, one per AuditReport row
    defect_map  : {report_id: [{category, item, major_count, minor_count}, ...]}
    output_path : destination .xlsx path (parent dir created automatically)
    """
    # Group records by canonical inspection type
    by_type: Dict[str, List[Dict]] = {}
    for rec in records:
        key = _canonical_type(rec.get("inspection_type") or "")
        by_type.setdefault(key, []).append(rec)

    wb = openpyxl.Workbook()
    # Remove default blank sheet
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    sheets_written = 0
    for sheet_name in _DISPLAY_ORDER:
        type_records = by_type.get(sheet_name)
        if not type_records:
            continue

        report_ids  = [r["report_id"] for r in type_records]
        defect_plan = _build_defect_plan(defect_map, report_ids)

        ws = wb.create_sheet(title=sheet_name[:31])
        _write_sheet(ws, type_records, defect_map, defect_plan)
        sheets_written += 1
        logger.info("Sheet '%s': %d records, %d defect columns",
                    sheet_name, len(type_records), len(defect_plan))

    if not wb.sheetnames:
        wb.create_sheet("No Data")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    logger.info("Summary workbook saved → %s (%d sheet(s))", output_path, sheets_written)