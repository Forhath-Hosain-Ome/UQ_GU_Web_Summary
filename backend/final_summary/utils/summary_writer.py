"""
summary_writer.py
-----------------
Generates the output summary Excel workbook from queried DB records.

Layout (matches the uploaded sample exactly)
--------------------------------------------
  Row 1  : Title row  +  category group headers (merged spans)
           e.g. "A : FABRICS" spanning columns 24-36
  Row 2  : Individual column headers
  Row 3  : (skipped — no averages row)
  Row 4  : 合計  totals row
  Row 5+ : One data row per audit record

  After the data rows:
    If ENABLE_PLACEHOLDER_ROWS = True (future feature):
      Each record block is followed by 5 stub rows:
        1. Carton
        2. Shipment dates
        3. Needle detector
        4. Remarks
        5. DO Set Col Size

Column order (fixed prefix, then dynamic defect columns)
---------------------------------------------------------
  factory, date_of_issue, inspection_type,
  factory_in_time, factory_out_time, factory_total_hours,
  audit_start_time, audit_end_time,  audit_total_hours,
  audit_result, report_no, item_name, style_no, po_no,
  country, po_qty_display, po_wh, ship_qty, audit_qty,
  acceptable_defect_qty, defect_qty, defect_percentage, person,
  [dynamic defect columns grouped by category ...]

Defect columns
--------------
Built dynamically from whatever defect types appear in the data.
Grouped by category (A:FABRICS, B:SEWING, …) in the row-1 merged header.

Called from writer_main.py as:
    write_summary(records, defect_map, output_path)
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from openpyxl.chart import PieChart, Reference, Series
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# from output.chart_generator import ChartGenerator

# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------

ENABLE_PLACEHOLDER_ROWS: bool = False   # set True when placeholder logic is ready


# ---------------------------------------------------------------------------
# Fixed prefix columns
# (column key → display header label)
# ---------------------------------------------------------------------------

PREFIX_COLUMNS: List[Tuple[str, str]] = [
    ("factory",            "Factory"),
    ("date_of_issue",      "Date of issue"),
    ("inspection_type",    "Inspection Type"),
    ("factory_in",         "Factory In Time"),
    ("factory_out",        "Factory Out Time"),
    ("factory_total_hours","Total Hours"),
    ("audit_start",        "Audit Start Time"),
    ("audit_end",          "Audit End Time"),
    ("audit_total_hours",  "Total Hours"),
    ("audit_result",       "Audit Result"),
    ("report_no",          "Report Number"),
    ("item_name",          "Item Name"),
    ("style_no",           "Style NO."),
    ("po_no",              "POーNO"),
    ("country",            "Country"),
    ("po_qty_pcs",         "PO Qty.(PCS)"),
    ("po_qty_pack",        "PO Qty.(PACK)"),
    ("po_qty_set",         "PO Qty.(SET)"),
    ("po_wh",              "PO  WH"),
    ("ship_qty",           "Shipping Qty"),
    ("audit_qty",          "Audit Qty."),
    ("acceptable_defect_qty", "Acceptable Defect Qty"),
    ("defect_qty",         "Defect Qty."),
    ("defect_percentage",  "Defect %"),
    ("person",             "Person"),
]

PREFIX_KEY_SET = {k for k, _ in PREFIX_COLUMNS}

# ---------------------------------------------------------------------------
# Placeholder row labels (used when ENABLE_PLACEHOLDER_ROWS = True)
# ---------------------------------------------------------------------------

_PLACEHOLDER_LABELS = [
    ("carton",          "carton"),
    ("shipment_dates",  "shipment_dates"),
    ("needle_detector", "needle_detector"),
    ("remarks",         "remarks"),
    ("do_set_col_size", "Do Set Col Size"),
]

# ---------------------------------------------------------------------------
# Layout defaults
# ---------------------------------------------------------------------------

# Default width units for sheet columns. These are Excel column width units,
# not pixels. Column width can be tuned by column key below.
DEFAULT_COLUMN_WIDTH = 10.0
DEFECT_COLUMN_WIDTH  = 6.0

# Default height for all rows. Special rows can override this default.
DEFAULT_ROW_HEIGHT = 16.0
ROW_HEIGHT_OVERRIDES = {
    1: 22.0,
    2: 150.0,
    3: 1.0,
    4: 16.0,
}

# Manual per-column width overrides for fixed prefix columns.
COLUMN_WIDTHS_BY_KEY: Dict[str, float] = {
    "factory": 25.29,
    "date_of_issue": 7.86,
    "inspection_type": 22.71,
    "factory_in": 10.43,
    "factory_out": 10.43,
    "factory_total_hours": 7.0,
    "audit_start": 10.43,
    "audit_end": 10.43,
    "audit_total_hours": 7.0,
    "audit_result": 3,
    "report_no": 19.71,
    "item_name": 25.71,
    "style_no": 16.14,
    "po_no": 19.43,
    "country": 10.0,
    "po_qty_pcs": 10.0,
    "po_qty_pack": 10.0,
    "po_qty_set": 10.0,
    "po_wh": 13.86,
    "ship_qty": 7.0,
    "audit_qty": 8.29,
    "acceptable_defect_qty": 3.0,
    "defect_qty": 4.0,
    "defect_percentage": 8.14,
    "person": 3.0,
}

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

_WHITE   = "FFFFFF"
_BLACK   = "000000"
_YELLOW  = "FFFF00"
_DARK_BLUE   = "2F5496"
_ORANGE      = "C65911"
_LIGHT_GRAY  = "808080"
_TOTALS_FILL = _LIGHT_GRAY   # light gray for 合計 row

_TOP_BAR_FONT  = Font(bold=True, color=_BLACK, size=9)
_TOP_BAR_FILL  = PatternFill("solid", fgColor=_WHITE)

_HEADER_FONT   = Font(bold=True, color=_BLACK, size=9)
_DATA_FONT     = Font(size=9)
_TOTALS_FONT   = Font(bold=True, color=_WHITE, size=9)
_TITLE_FONT    = Font(bold=True, color=_WHITE, size=10)

_HEADER_FILL  = PatternFill("solid", fgColor=_YELLOW)
_TOTALS_FILL_STYLE = PatternFill("solid", fgColor=_TOTALS_FILL)
_PLACEHOLDER_FILL  = PatternFill("solid", fgColor=_LIGHT_GRAY)

_CENTRE = Alignment(horizontal="center", vertical="center", wrap_text=True)
_LEFT   = Alignment(horizontal="left",   vertical="center", wrap_text=False)
_RIGHT  = Alignment(horizontal="right",  vertical="center")

_THIN = Side(style="thin", color=_BLACK)
_CELL_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_CELL_BORDER_TOP_RIGHT_LEFT = Border(left=_THIN, right=_THIN, top=_THIN)
_CELL_BORDER_BOTTOM = Border(bottom=_THIN)
_CELL_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_ROTATE_TEXT_UP_ALIGNMENT = Alignment(horizontal="center", vertical="center", textRotation=90, wrap_text=True)


# ---------------------------------------------------------------------------
# Category colour map (matches sample colouring)
# ---------------------------------------------------------------------------

_CATEGORY_FILLS = {
    "A": PatternFill("solid", fgColor=_WHITE),  # White
    "B": PatternFill("solid", fgColor=_WHITE),  # White
    "C": PatternFill("solid", fgColor=_WHITE),  # White
    "D": PatternFill("solid", fgColor=_WHITE),  # White
    "E": PatternFill("solid", fgColor=_WHITE),  # White
    "F": PatternFill("solid", fgColor=_WHITE),  # White
}


def _cat_fill(category: str) -> PatternFill:
    letter = category.strip()[:1].upper()
    return _CATEGORY_FILLS.get(letter, _TOP_BAR_FILL)

def pts_to_cm(pts):
    return pts * 0.03528
# ---------------------------------------------------------------------------
# Defect column plan builder
# ---------------------------------------------------------------------------

def build_defect_column_plan(
    defect_rows_by_report: Dict[int, List[Dict[str, Any]]],
) -> List[Tuple[str, str]]:
    """
    Build an ordered list of (category, item) pairs from all defect data.
    Sorted by category letter then item text.

    Returns [(category, item), ...]
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


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------

def _get_prefix_value(row: Dict[str, Any], key: str) -> Any:
    """Extract the display value for a prefix column from a DB row dict."""
    if key == "po_qty_display":
        # Prefer pcs, then pack, then set, then raw string
        for sub in ("po_qty_pcs", "po_qty_pack", "po_qty_set"):
            v = row.get(sub)
            if v:
                return v
        return row.get("po_qty_raw", "")
    return row.get(key, "")


def _pct_float(val: Any) -> Optional[float]:
    """Convert defect_percentage stored as float or '3.71%' to float."""
    if val is None:
        return None
    try:
        return float(str(val).replace("%", "").strip())
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Sheet writer
# ---------------------------------------------------------------------------

def _write_sheet(
    ws,
    records: List[Dict[str, Any]],
    defect_items_by_report: Dict[int, List[Dict[str, Any]]],
    defect_plan: List[Tuple[str, str]],
) -> None:
    """Write all rows to worksheet *ws*."""

    total_prefix = len(PREFIX_COLUMNS)
    total_defect = len(defect_plan)
    total_cols   = total_prefix + total_defect

    # ── Row 1: title + category group headers ────────────────────────────────
    ws.row_dimensions[1].height = 22

    # Left title span (fixed prefix area)
    ws.merge_cells(start_row=1, start_column=1,
                   end_row=1, end_column=total_prefix)
    title_cell = ws.cell(row=1, column=1, value="出荷前監査報告書")
    title_cell.font      = _TOP_BAR_FONT
    title_cell.fill      = _TOP_BAR_FILL
    title_cell.alignment = _CENTRE
    title_cell.border    = _CELL_BORDER

    # Category merged spans
    if defect_plan:
        col_idx = total_prefix + 1
        i = 0
        while i < len(defect_plan):
            cat = defect_plan[i][0]
            j = i
            while j < len(defect_plan) and defect_plan[j][0] == cat:
                j += 1
            span = j - i
            if span > 1:
                ws.merge_cells(
                    start_row=1, start_column=col_idx,
                    end_row=1,   end_column=col_idx + span - 1
                )
            cell = ws.cell(row=1, column=col_idx, value=cat)
            cell.font      = _TOP_BAR_FONT
            cell.fill      = _cat_fill(cat)
            cell.alignment = _CENTRE
            cell.border    = _CELL_BORDER
            col_idx += span
            i = j

    # ── Rows 2-3: column headers (each cell merged vertically across both rows) ─
    # Row 2 holds the value; row 3 is merged into it so headers appear taller.
    ws.row_dimensions[2].height = 150
    ws.row_dimensions[3].height = 1    # collapsed — fully absorbed by merge

    def _write_header_cell(col_idx: int, label: str, fill: PatternFill) -> None:
        """Merge rows 2-3 for this column and write the header label."""
        # Clear row 3 first (BEFORE merging — MergedCell is read-only after)
        r3 = ws.cell(row=3, column=col_idx)
        r3.value = None

        # Unmerge first (safe no-op if not already merged)
        try:
            ws.unmerge_cells(
                start_row=2, start_column=col_idx,
                end_row=3,   end_column=col_idx,
            )
        except Exception:
            pass

        ws.merge_cells(
            start_row=2, start_column=col_idx,
            end_row=3,   end_column=col_idx,
        )
        cell = ws.cell(row=2, column=col_idx, value=label)
        cell.font      = _HEADER_FONT
        cell.fill      = fill
        cell.alignment = _ROTATE_TEXT_UP_ALIGNMENT
        cell.border    = _CELL_BORDER

    for col_idx, (_, label) in enumerate(PREFIX_COLUMNS, start=1):
        _write_header_cell(col_idx, label, _HEADER_FILL)

    for k, (cat, item) in enumerate(defect_plan, start=total_prefix + 1):
        _write_header_cell(k, item, _HEADER_FILL)
        # _write_header_cell(k, item, _cat_fill(cat))

    # ── Row 4: 合計 totals ────────────────────────────────────────────────────
    totals_row = 4
    ws.row_dimensions[totals_row].height = 16

    totals_label = ws.cell(row=totals_row, column=1, value="合計")
    totals_label.font      = _TOTALS_FONT
    totals_label.fill      = _TOTALS_FILL_STYLE
    totals_label.alignment = _LEFT
    totals_label.border    = _CELL_BORDER

    # We'll fill totals after writing data rows; store column sums here
    _ship_col  = next((i+1 for i, (k, _) in enumerate(PREFIX_COLUMNS) if k == "ship_qty"),  None)
    _audit_col = next((i+1 for i, (k, _) in enumerate(PREFIX_COLUMNS) if k == "audit_qty"), None)
    _defect_col = next((i+1 for i, (k, _) in enumerate(PREFIX_COLUMNS) if k == "defect_qty"), None)

    total_ship  = 0
    total_audit = 0
    total_defect_count = 0
    defect_col_totals: Dict[int, int] = {}   # col_idx → total

    # ── Rows 5+: data rows ───────────────────────────────────────────────────
    current_row = 5

    for rec in records:
        report_id = rec.get("report_id")

        # Build defect lookup for this record: (category, item) → major_count
        defect_lookup: Dict[Tuple[str, str], int] = {}
        if report_id is not None:
            for d in defect_items_by_report.get(report_id, []):
                cat  = (d.get("category") or "").strip()
                item = (d.get("item") or "").strip()
                if cat and item:
                    defect_lookup[(cat, item)] = int(d.get("major_count", 0))

        # Write prefix columns
        for col_idx, (key, _) in enumerate(PREFIX_COLUMNS, start=1):
            val  = _get_prefix_value(rec, key)
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.font      = _DATA_FONT
            cell.alignment = _CENTRE
            cell.border    = _CELL_BORDER

        # Write defect columns
        for k, (cat, item) in enumerate(defect_plan, start=total_prefix + 1):
            count = defect_lookup.get((cat, item), "")
            cell  = ws.cell(row=current_row, column=k, value=count if count else "")
            cell.font      = _DATA_FONT
            cell.alignment = _CENTRE
            cell.border    = _CELL_BORDER
            if isinstance(count, int) and count > 0:
                defect_col_totals[k] = defect_col_totals.get(k, 0) + count

        # Accumulate totals
        try:
            total_ship  += int(rec.get("ship_qty")  or 0)
            total_audit += int(rec.get("audit_qty") or 0)
            total_defect_count += int(rec.get("defect_qty") or 0)
        except (TypeError, ValueError):
            pass

        current_row += 1

        # Placeholder rows (controlled by flag)
        if ENABLE_PLACEHOLDER_ROWS:
            _write_placeholder_rows(ws, rec, PREFIX_COLUMNS, total_cols, current_row)
            current_row += len(_PLACEHOLDER_LABELS)

    # ── Fill totals row ───────────────────────────────────────────────────────
    if _ship_col:
        cell = ws.cell(row=totals_row, column=_ship_col, value=total_ship)
        cell.font = _TOTALS_FONT; cell.fill = _TOTALS_FILL_STYLE
    if _audit_col:
        cell = ws.cell(row=totals_row, column=_audit_col, value=total_audit)
        cell.font = _TOTALS_FONT; cell.fill = _TOTALS_FILL_STYLE
    if _defect_col:
        # defect % = total_defect / total_audit
        cell = ws.cell(row=totals_row, column=_defect_col, value=total_defect_count)
        cell.font = _TOTALS_FONT; cell.fill = _TOTALS_FILL_STYLE
        pct_col = _defect_col + 1
        if total_audit > 0:
            ws.cell(row=totals_row, column=pct_col,
                    value=round(total_defect_count / total_audit, 8)).fill = _TOTALS_FILL_STYLE

    for col_idx, total in defect_col_totals.items():
        cell = ws.cell(row=totals_row, column=col_idx, value=total)
        cell.font = _TOTALS_FONT
        cell.fill = _TOTALS_FILL_STYLE
        cell.alignment = _CENTRE

    # Fill remaining totals cells with fill colour
    for col_idx in range(2, total_cols + 1):
        cell = ws.cell(row=totals_row, column=col_idx)
        if cell.fill.fgColor.rgb in ("00000000", "FFFFFFFF", "00FFFFFF"):
            cell.fill = _TOTALS_FILL_STYLE

    # ── Column widths ─────────────────────────────────────────────────────────
    _set_column_widths(ws, total_prefix, total_defect)

    # ── Apply default row heights after the sheet content exists -------
    _apply_default_row_heights(ws, DEFAULT_ROW_HEIGHT, ROW_HEIGHT_OVERRIDES)

    # ── Freeze panes: rows 1-4 (title + merged header + totals) ─────────────
    ws.freeze_panes = "A5"

    # ── Charts below the data rows ────────────────────────────────────────────
    # Leave 2 blank rows as a visual gap, then draw:
    #   Col 1 : Top-5 pie chart  +  category summary table  (stacked vertically)
    #   Col 2 : Full-defect bar chart  (right of pie, matching screenshot layout)
    chart_start_row = current_row + 1   # 1-row gap between data and charts
    _write_inline_charts(ws, chart_start_row, defect_plan, total_prefix)


def _write_inline_charts(
    ws,
    start_row: int,
    defect_plan: List[Tuple[str, str]],
    total_prefix: int,
) -> None:
    """
    Draw charts immediately below the data rows (1-row gap).

    Layout
    ------
    chart_row  : pie chart (cols A–K)  |  summary table (cols L onward)  |  bar chart (after table)

    Both charts share the same fixed height (PIE_BAR_CHART_HEIGHT_CM).
    Table row heights are distributed evenly to match that height.
    Zero-count rows are removed from the top-5 table; their percentage
    share is redistributed proportionally to the remaining rows.
    """
    if not defect_plan:
        return

    # ── Static chart size constants (cm) ─────────────────────────────────────
    PIE_CHART_WIDTH_CM  = pts_to_cm(190.15)   # pie chart width  in cm
    BAR_CHART_WIDTH_CM  = 35.34   # bar chart width  in cm
    CHART_HEIGHT_CM     = 3.0    # SHARED height for both pie and bar chart in cm

    # ── Color palettes (hex, no '#') ──────────────────────────────────────────
    # Pie chart slice colours (up to 5 slices)
    PIE_SLICE_COLORS  = ["4472C4", "ED7D31", "A9D18E", "FF0000", "FFC000"]
    # Bar chart bar colour (single series — one colour for all bars)
    BAR_COLOR         = "4472C4"
    # Table row alternating fill colours (data rows only, not header)
    TABLE_ROW_COLORS  = [
        "DCE6F1",  # row 1 — light blue
        "EBF3E8",  # row 2 — light green
        "FFF2CC",  # row 3 — light yellow
        "FCE4D6",  # row 4 — light orange
        "E2EFDA",  # row 5 — pale green
    ]

    from openpyxl.chart import BarChart, Reference, Series
    from openpyxl.chart.label import DataLabelList
    from openpyxl.chart.shapes import GraphicalProperties
    from openpyxl.styles import PatternFill as _PF

    n         = len(defect_plan)
    col_start = total_prefix + 1
    col_end   = col_start + n - 1

    # ── Read (category, defect name, total) from sheet rows 2 and 4 ──────────
    defect_totals: List[Tuple[str, str, int]] = []
    for idx, (category, name) in enumerate(defect_plan, start=col_start):
        val = ws.cell(row=4, column=idx).value
        try:
            total = int(val or 0)
        except (TypeError, ValueError):
            total = 0
        defect_totals.append((category, str(name), total))

    # Keep only non-zero entries
    nonzero = [e for e in defect_totals if e[2] > 0]
    if not nonzero:
        return

    nonzero.sort(key=lambda x: (-x[2], x[1]))
    total_defect_count = sum(c for _, _, c in nonzero)

    # ── Build top-5 table rows, removing any zero rows ───────────────────────
    def _build_top5(items: List[Tuple[str, str, int]]) -> List[Tuple[str, str, int, float]]:
        """
        Take up to 5 highest-count items, drop any whose count == 0,
        then redistribute percentages so they sum to 100 %.
        Returns [(category, name, count, pct), ...].
        """
        top = items[:5]
        top = [(cat, nm, cnt) for cat, nm, cnt in top if cnt > 0]
        subtotal = sum(c for _, _, c in top)
        rows = []
        for cat, nm, cnt in top:
            pct = (cnt / subtotal * 100) if subtotal else 0.0
            rows.append((cat, nm, cnt, pct))
        return rows

    top5_table_rows = _build_top5(nonzero)
    top5_pie_rows   = [(nm, cnt, pct) for _, nm, cnt, pct in top5_table_rows]
    n_table_rows    = len(top5_table_rows)   # may be < 5 if zeros removed

    # ── Factory name for bar chart title ─────────────────────────────────────
    try:
        factory_name = ws.cell(row=5, column=1).value or ""
    except Exception:
        factory_name = ""
    bar_title = str(factory_name).strip()

    chart_row = start_row    # no extra gap — caller already added 1-row gap

    # ── Pie chart anchor columns ──────────────────────────────────────────────
    PIE_START_COL = 1
    PIE_END_COL   = 11   # columns A–K

    # ── Table position: starts at col L (PIE_END_COL + 1) ────────────────────
    TABLE_START_COL = PIE_END_COL + 1     # col 12 = L
    TABLE_HEADERS   = ("SL", "Category", "Defect", "Count", "Percentage")
    TABLE_COLS      = len(TABLE_HEADERS)  # 5

    # ── Distribute chart height evenly across table rows ─────────────────────
    # Total rows = 1 header + n_table_rows data rows
    total_table_rows  = 1 + n_table_rows
    # Convert CHART_HEIGHT_CM to points: 1 cm = 28.3465 pt
    chart_height_pt   = CHART_HEIGHT_CM * 28.3465
    row_height_pt     = chart_height_pt / total_table_rows

    # Apply heights to table rows
    ws.row_dimensions[chart_row].height = row_height_pt          # header row
    for i in range(1, n_table_rows + 1):
        ws.row_dimensions[chart_row + i].height = row_height_pt  # data rows

    # ── Write table header ────────────────────────────────────────────────────
    _HEADER_FILL_LOCAL = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
    _HEADER_FONT_LOCAL = Font(color="FFFFFF", bold=True, size=9)
    _THIN = Side(style="thin")
    _BORDER_LOCAL = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

    for offset, hdr in enumerate(TABLE_HEADERS):
        c = ws.cell(row=chart_row, column=TABLE_START_COL + offset)
        c.value     = hdr
        c.font      = _HEADER_FONT_LOCAL
        c.fill      = _HEADER_FILL_LOCAL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border    = _BORDER_LOCAL

    # ── Write table data rows with alternating row colours ───────────────────
    for i, (category, name, count, pct) in enumerate(top5_table_rows):
        r        = chart_row + 1 + i
        row_fill = _PF(start_color=TABLE_ROW_COLORS[i % len(TABLE_ROW_COLORS)],
                       end_color  =TABLE_ROW_COLORS[i % len(TABLE_ROW_COLORS)],
                       fill_type  ="solid")
        cells_vals = [
            (TABLE_START_COL,     i + 1,       Alignment(horizontal="center", vertical="center")),
            (TABLE_START_COL + 1, category,    Alignment(horizontal="left",   vertical="center")),
            (TABLE_START_COL + 2, name,        Alignment(horizontal="left",   vertical="center", wrap_text=True)),
            (TABLE_START_COL + 3, count,       Alignment(horizontal="center", vertical="center")),
            (TABLE_START_COL + 4, pct / 100,   Alignment(horizontal="center", vertical="center")),
        ]
        for col, val, align in cells_vals:
            c = ws.cell(row=r, column=col, value=val)
            c.fill      = row_fill
            c.border    = _BORDER_LOCAL
            c.alignment = align
            c.font      = Font(size=9)
            if col == TABLE_START_COL + 3:
                c.number_format = "#,##0"
            elif col == TABLE_START_COL + 4:
                c.number_format = "0.00%"

    # Table ends at this column
    table_end_col = TABLE_START_COL + TABLE_COLS  # exclusive, i.e. first col after table

    # ── Write hidden data columns for pie chart (Defect name + Count) ─────────
    # We write a tiny 2-col helper table starting at table_end_col so the pie
    # chart can reference real cell data (openpyxl PieChart needs References).
    PIE_DATA_COL   = table_end_col        # "Defect" label
    PIE_COUNT_COL  = table_end_col + 1    # count value
    for i, (_, name, count, _pct) in enumerate(top5_table_rows):
        r = chart_row + 1 + i
        ws.cell(row=r, column=PIE_DATA_COL,  value=name)
        ws.cell(row=r, column=PIE_COUNT_COL, value=count)
    # Hide these helper columns
    from openpyxl.utils import get_column_letter as _gcl
    for _hc in (PIE_DATA_COL, PIE_COUNT_COL):
        ws.column_dimensions[_gcl(_hc)].hidden = True

    # ── Build pie chart ───────────────────────────────────────────────────────
    pie = PieChart()
    pie.title  = "Top 5 Defect"
    pie.style  = 10
    pie.width  = PIE_CHART_WIDTH_CM
    pie.height = CHART_HEIGHT_CM

    pie.dataLabels = DataLabelList()
    pie.dataLabels.showPercent   = True
    pie.dataLabels.showCatName   = True
    pie.dataLabels.showVal       = False
    pie.dataLabels.showSerName   = False
    pie.dataLabels.showLegendKey = False
    pie.dataLabels.dLblPos       = "bestFit"

    _lbl_ref  = Reference(ws,
                           min_col=PIE_DATA_COL,  min_row=chart_row + 1,
                           max_row=chart_row + n_table_rows)
    _data_ref = Reference(ws,
                           min_col=PIE_COUNT_COL, min_row=chart_row + 1,
                           max_row=chart_row + n_table_rows)
    _pie_series = Series(_data_ref, title="Defect Count")
    pie.append(_pie_series)
    pie.set_categories(_lbl_ref)

    # Apply explicit slice colours
    from openpyxl.chart.data_source import NumDataSource, NumRef
    from openpyxl.drawing.fill import PatternFillProperties
    try:
        from openpyxl.chart.series import DataPoint
        for i in range(n_table_rows):
            pt = DataPoint(idx=i)
            pt.graphicalProperties.solidFill = PIE_SLICE_COLORS[i % len(PIE_SLICE_COLORS)]
            _pie_series.dPt.append(pt)
    except Exception:
        pass  # colour assignment is best-effort

    ws.add_chart(pie, f"{_gcl(PIE_START_COL)}{chart_row}")

    # ── Build bar chart ───────────────────────────────────────────────────────
    BAR_COL = table_end_col + 2   # one col after hidden helper cols

    bar = BarChart()
    bar.title    = bar_title
    bar.style    = 10
    bar.type     = "col"           # vertical column chart
    bar.width    = BAR_CHART_WIDTH_CM
    bar.height   = CHART_HEIGHT_CM  # same height as pie
    bar.gapWidth = 50
    bar.legend   = None

    # Axis labels
    bar.x_axis.title       = "Defect"
    bar.y_axis.title       = "Count"
    bar.x_axis.tickLblPos  = "low"   # labels shown BELOW the bars
    bar.x_axis.delete      = False
    bar.y_axis.delete      = False

    _bar_data = Reference(ws, min_col=col_start, max_col=col_end,
                          min_row=4, max_row=4)
    _bar_cats = Reference(ws, min_col=col_start, max_col=col_end,
                          min_row=2, max_row=2)

    _bar_series = Series(_bar_data, title="Defect Count")
    # Apply a single solid fill colour to all bars
    try:
        _bar_series.graphicalProperties.solidFill = BAR_COLOR
    except Exception:
        pass
    bar.series.append(_bar_series)
    bar.set_categories(_bar_cats)

    # Value labels on top of bars
    bar.dataLabels = DataLabelList()
    bar.dataLabels.showVal     = True
    bar.dataLabels.showCatName = False
    bar.dataLabels.showSerName = False
    bar.dataLabels.dLblPos     = "outEnd"
    bar.dataLabels.numFmt      = "#,##0"

    ws.add_chart(bar, f"{_gcl(BAR_COL)}{chart_row}")

def _write_placeholder_rows(
    ws,
    rec: Dict[str, Any],
    prefix_columns: List[Tuple[str, str]],
    total_cols: int,
    start_row: int,
) -> None:
    """Write the 5 placeholder rows below a data record."""
    file_name = rec.get("file_name", "")
    factory   = rec.get("factory", "")

    for offset, (field_key, label) in enumerate(_PLACEHOLDER_LABELS):
        row = start_row + offset
        ws.row_dimensions[row].height = 13

        for col_idx, (key, _) in enumerate(prefix_columns, start=1):
            cell = ws.cell(row=row, column=col_idx)
            cell.fill = _PLACEHOLDER_FILL
            cell.font = Font(size=8, italic=True)
            cell.alignment = _LEFT

            if key == "factory":
                cell.value = label
            elif key == "date_of_issue" and field_key in rec:
                cell.value = rec.get(field_key, "")

        # merge remaining columns
        if total_cols > len(prefix_columns):
            ws.merge_cells(
                start_row=row, start_column=len(prefix_columns) + 1,
                end_row=row,   end_column=total_cols,
            )


def _apply_default_row_heights(
    ws,
    default_height: float,
    overrides: Optional[Dict[int, float]] = None,
) -> None:
    """Apply a row height default to every row, with optional overrides."""
    overrides = overrides or {}
    for row_idx in range(1, ws.max_row + 1):
        if row_idx in overrides:
            ws.row_dimensions[row_idx].height = overrides[row_idx]
        else:
            ws.row_dimensions[row_idx].height = default_height


def _get_column_width(key: str) -> float:
    """Return the configured width for a prefix column key."""
    return COLUMN_WIDTHS_BY_KEY.get(key, DEFAULT_COLUMN_WIDTH)


def _set_column_widths(ws, total_prefix: int, total_defect: int) -> None:
    """Set column widths based on configured defaults and fixed overrides."""
    for col_idx in range(1, total_prefix + 1):
        key, _ = PREFIX_COLUMNS[col_idx - 1]
        letter = get_column_letter(col_idx)
        ws.column_dimensions[letter].width = _get_column_width(key)

    for col_idx in range(total_prefix + 1, total_prefix + total_defect + 1):
        letter = get_column_letter(col_idx)
        ws.column_dimensions[letter].width = DEFECT_COLUMN_WIDTH


# ---------------------------------------------------------------------------
# Template-based sheet writer (completes the _fill_template_sheet stub)
# ---------------------------------------------------------------------------

def _fill_template_sheet(
    ws,
    records: List[Dict[str, Any]],
    defect_items_by_report: Dict[int, List[Dict[str, Any]]],
    defect_plan: List[Tuple[str, str]],
    start_row: int,
) -> None:
    """
    Fill a template sheet starting at the given start_row.
    The template already has headers - we just fill the data rows.
    """
    # Read defect column headers from row 2 to get the template's column order
    template_defect_cols: List[Tuple[str, str]] = []
    for col_idx in range(21, ws.max_column + 1):
        header = ws.cell(row=2, column=col_idx).value
        if header is not None:
            # Template doesn't include categories, just item names
            template_defect_cols.append(("", str(header).strip()))

    total_prefix = 20  # Template has 20 prefix columns
    current_row = start_row

    for rec in records:
        report_id = rec.get("report_id")

        # Build defect lookup for this record: (item) → major_count
        defect_lookup: Dict[str, int] = {}
        if report_id is not None:
            for d in defect_items_by_report.get(report_id, []):
                item = (d.get("item") or "").strip()
                if item:
                    defect_lookup[item] = int(d.get("major_count", 0))

        # Write prefix columns (template has fixed mapping)
        col_map = {
            "factory": 1, "date_of_issue": 2, "inspection_type": 3,
            "factory_in": 4, "factory_out": 5, "factory_total_hours": 6,
            "audit_start": 7, "audit_end": 8, "audit_total_hours": 9,
            "audit_result": 10, "report_no": 11, "item_name": 12,
            "style_no": 13, "po_no": 14, "country": 15,
            "audit_qty": 16, "acceptable_defect_qty": 17, "defect_qty": 18,
            "defect_percentage": 19, "person": 20,
        }
        for key, col_idx in col_map.items():
            val = _get_prefix_value(rec, key)
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.font = _DATA_FONT
            cell.alignment = _CENTRE
            cell.border = _CELL_BORDER

        # Write defect columns based on template's column order
        for idx, (_, item_name) in enumerate(template_defect_cols):
            count = defect_lookup.get(item_name, "")
            col_idx = total_prefix + 1 + idx
            cell = ws.cell(row=current_row, column=col_idx, value=count if count else "")
            cell.font = _DATA_FONT
            cell.alignment = _CENTRE
            cell.border = _CELL_BORDER

        current_row += 1


def _write_summary_from_scratch(
    records: List[Dict[str, Any]],
    defect_items_by_report: Dict[int, List[Dict[str, Any]]],
    output_path: Path,
) -> None:
    """
    Build summary from scratch (no template) - used as fallback.
    Groups records by inspection type and writes sheets using _write_sheet.
    """
    import openpyxl

    # Group records by canonical inspection type
    by_type: Dict[str, List[Dict[str, Any]]] = {}
    for rec in records:
        itype = (rec.get("inspection_type") or "").upper().strip()
        if "PRE" in itype and "FINAL" in itype:
            key = "PRE-FINAL"
        elif "RE" in itype and "FINAL" in itype:
            key = "RE-FINAL"
        elif "FINAL" in itype:
            key = "FINAL"
        elif "INLINE" in itype:
            key = "INLINE"
        elif "CMF" in itype:
            key = "CMF"
        elif "SAMPLE" in itype:
            key = "SAMPLE"
        else:
            key = "UNKNOWN"
        by_type.setdefault(key, []).append(rec)

    wb = openpyxl.Workbook()
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    # Build global defect plan
    defect_plan = build_defect_column_plan(defect_items_by_report)

    for sheet_name in ["FINAL", "RE-FINAL", "PRE-FINAL", "INLINE", "CMF", "SAMPLE", "UNKNOWN"]:
        type_records = by_type.get(sheet_name)
        if not type_records:
            continue

        ws = wb.create_sheet(title=sheet_name[:31])
        _write_sheet(ws, type_records, defect_items_by_report, defect_plan)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    logging.info(f"Summary saved (from scratch): {output_path}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_summary(
    records: List[Dict[str, Any]],
    defect_items_by_report: Dict[int, List[Dict[str, Any]]],
    output_path: Path,
) -> None:
    """
    Generate the summary Excel workbook using the SPI-Final-78.xlsx template.

    Parameters
    ----------
    records                : list of row dicts from v_audit_full (DB query)
    defect_items_by_report : {report_id: [defect_item_dict, ...]}
    output_path            : destination .xlsx path

    The template defines sheets: Final, Re-Final, INLINE (and Sample if needed).
    Data rows start at row 12 for Final/Re-Final, row 5 for INLINE/Sample.
    Prefix columns (A-W) are populated directly. Defect quantities are
    distributed across columns Z onward (78 columns total for SPI template).
    """
    import openpyxl
    from pathlib import Path
    from django.conf import settings

    # ── Select template based on defect column count ──────────────────────────
    # Build the global defect plan to count columns
    defect_plan = build_defect_column_plan(defect_items_by_report)
    num_defect_cols = len(defect_plan)

    # SPI template has 78 defect columns; other formats may use template.xlsx (Analysis)
    # For now, use SPI-Final-78.xlsx for any format with > 30 defect cols
    if num_defect_cols >= 70:
        template_name = "SPI-Final-78.xlsx"
        template_path = Path(settings.BASE_DIR) / "media" / "templates" / template_name
        start_rows = {"FINAL": 12, "RE-FINAL": 12, "PRE-FINAL": 12, "INLINE": 5, "SAMPLE": 5, "CMF": 12, "UNKNOWN": 12}
    else:
        # Fallback: use the generic Analysis template (template.xlsx) or build from scratch
        template_name = "template.xlsx"
        template_path = Path(settings.BASE_DIR) / "media" / "templates" / template_name
        if not template_path.exists():
            # No template available — build from scratch (original behavior)
            _write_summary_from_scratch(records, defect_items_by_report, output_path)
            return
        start_rows = {"FINAL": 5, "RE-FINAL": 5, "PRE-FINAL": 5, "INLINE": 5, "SAMPLE": 5, "CMF": 5, "UNKNOWN": 5}

    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    # Load template workbook (keep all sheets)
    wb = openpyxl.load_workbook(template_path, data_only=False)

    # Map records to sheets by canonical inspection type
    def _canonical(itype: str) -> str:
        import re as _re
        u = (itype or "").upper().strip()
        if _re.search(r"PRE[\s\-]?FINAL", u):
            return "PRE-FINAL"
        if _re.search(r"(?<!PRE[\-\s])RE[\s\-]?FINAL|REFINAL", u):
            return "RE-FINAL"
        if _re.search(r"\bFINAL\b|SHIPMENT\s*AUDIT|PRE[\s\-]?SHIPMENT", u):
            return "FINAL"
        if _re.search(r"IN[\s\-]?LINE", u):
            return "INLINE"
        if _re.search(r"\bCMF\b|COUNTER\s*MASTER", u):
            return "CMF"
        if _re.search(r"\bSAMPLE\b|PRE[\s\-]?PROD|PP\s*SAMPLE|\bPP\b", u):
            return "SAMPLE"
        return "UNKNOWN"

    by_type: Dict[str, List[Dict[str, Any]]] = {}
    for rec in records:
        key = _canonical(rec.get("inspection_type") or "")
        by_type.setdefault(key, []).append(rec)

    # Determine which sheets to write (only those with data AND that exist in template)
    # Sheet names in template are mixed-case (Final, Re-Final, INLINE)
    # Map our canonical names to template sheet names
    template_sheet_names = {s.lower(): s for s in wb.sheetnames}
    sheet_name_map = {
        "FINAL": "Final",
        "RE-FINAL": "Re-Final",
        "PRE-FINAL": None,  # No Pre-Final in template
        "INLINE": "INLINE",
        "CMF": None,  # No CMF in template
        "SAMPLE": None,  # No Sample in template
        "UNKNOWN": None,
    }
    display_order = [
        sheet_name_map.get(s) 
        for s in ["FINAL", "RE-FINAL", "PRE-FINAL", "INLINE", "CMF", "SAMPLE", "UNKNOWN"] 
        if sheet_name_map.get(s) and s in by_type
    ]

    for sheet_name in display_order:
        # Find the canonical key for this sheet
        reverse_map = {v: k for k, v in sheet_name_map.items() if v}
        canonical_key = reverse_map.get(sheet_name, "FINAL")
        type_records = by_type.get(canonical_key, [])
        start_row = start_rows.get(canonical_key, 12)
        ws = wb[sheet_name]
        _fill_template_sheet(ws, type_records, defect_items_by_report, defect_plan, start_row)

    # Ensure any other sheets (Helper-1, Helper-2) remain untouched — their formulas already reference data ranges

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    logging.info(f"Summary saved using template '{template_name}': {output_path}")