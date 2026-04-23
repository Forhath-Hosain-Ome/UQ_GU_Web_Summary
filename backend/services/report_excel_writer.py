"""
/services/report_excel_writer.py
----------------------------------------------
Writes aggregated audit summary data into a pre-designed template .xlsx.

Template expectations
---------------------
The template must contain:
  - A sheet named "MASTER"  → master summary (one row per inspection type)
  - Named ranges OR a "template helper" sheet to clone per inspection type.

If no sheet named "MASTER" exists, one is created.
For each inspection_type in the data, a helper sheet is created (or
overwritten) named after the type (e.g. "FINAL", "INLINE", "RE-FINAL").

Cells written use openpyxl write_only-style placement so template
formatting/merges are preserved. Values are injected by cell address.

Template cell map (all coordinates 1-based, row, col)
------------------------------------------------------
Helper sheet expected layout (matches your pre-designed template):
  B2  : Inspection Type label
  B3  : Date Range  (e.g. "01 Jan 2025 – 31 Jan 2025")
  B4  : Total Days
  B5  : Factory
  B6  : Client / Buyer
  D2  : Total Audits
  D3  : Total Check (audit_qty)
  D4  : Total Defect
  D5  : Total Pass
  D6  : Auditor(s) comma-joined

  Date table starts at row 10, columns B-H:
    B: Date  C: Check  D: Defect  E: Pass  F: Person  G: Auditor  H: Audits

  Top-5 defect table starts at row 10 + len(date_rows) + 3, columns B-F:
    B: Rank  C: Category  D: Item  E: Qty  F: %

  Item names written as comma-joined string in B(last_row+2)

MASTER sheet layout:
  Row 1: headers
  Row 2+: one row per inspection type with all summary columns
"""

from copy import copy
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl import load_workbook
from openpyxl.styles import (
    Alignment, Border, Font, PatternFill, Side,
)
from openpyxl.utils import get_column_letter


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_THIN = Side(style="thin")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_HEADER_FILL   = PatternFill("solid", fgColor="1F3864")   # dark navy
_HEADER_FONT   = Font(bold=True, color="FFFFFF", name="Arial", size=10)
_SUBHEAD_FILL  = PatternFill("solid", fgColor="2E75B6")   # mid blue
_SUBHEAD_FONT  = Font(bold=True, color="FFFFFF", name="Arial", size=10)
_ALT_FILL      = PatternFill("solid", fgColor="DEEAF1")   # light blue alt row
_LABEL_FONT    = Font(bold=True, name="Arial", size=10)
_DATA_FONT     = Font(name="Arial", size=10)
_CENTER        = Alignment(horizontal="center", vertical="center", wrap_text=True)
_LEFT          = Alignment(horizontal="left",   vertical="center", wrap_text=True)


def _fmt_date(d) -> str:
    if isinstance(d, (date, datetime)):
        return d.strftime("%d %b %Y")
    return str(d) if d else ""


def _write(ws, row: int, col: int, value, font=None, fill=None, align=None, border=True, num_fmt=None):
    cell = ws.cell(row=row, column=col, value=value)
    if font:
        cell.font   = font
    if fill:
        cell.fill   = fill
    if align:
        cell.alignment = align
    if border:
        cell.border = _BORDER
    if num_fmt:
        cell.number_format = num_fmt
    return cell


def _header_row(ws, row: int, labels: list[str], start_col: int = 1):
    for i, lbl in enumerate(labels):
        _write(ws, row, start_col + i, lbl,
               font=_HEADER_FONT, fill=_HEADER_FILL, align=_CENTER)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry-point
# ─────────────────────────────────────────────────────────────────────────────

def generate_report_excel(
    aggregated: dict,
    template_path: str | Path | None = None,
) -> BytesIO:
    """
    Parameters
    ----------
    aggregated    : output of report_aggregator.aggregate_report()
    template_path : path to the pre-designed .xlsx template, or None to
                    generate a clean workbook from scratch.

    Returns
    -------
    BytesIO containing the finished .xlsx file.
    """
    if template_path and Path(template_path).exists():
        wb = load_workbook(template_path)
    else:
        wb = openpyxl.Workbook()
        # Remove default sheet — we'll create named sheets below
        if "Sheet" in wb.sheetnames:
            del wb["Sheet"]

    meta    = aggregated["meta"]
    by_type = aggregated["by_type"]

    # ── Master sheet ──────────────────────────────────────────────────────────
    _write_master_sheet(wb, meta, by_type)

    # ── Per-type helper sheets ────────────────────────────────────────────────
    for itype, block in by_type.items():
        sheet_name = _safe_sheet_name(itype)
        if sheet_name in wb.sheetnames:
            # Remove and recreate to avoid stale data
            del wb[sheet_name]
        ws = wb.create_sheet(title=sheet_name)
        _write_helper_sheet(ws, meta, block)

    # Ensure MASTER is first
    if "MASTER" in wb.sheetnames:
        wb.move_sheet("MASTER", offset=-len(wb.sheetnames))

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────────────────────────────────────
# Master sheet
# ─────────────────────────────────────────────────────────────────────────────

_MASTER_COLS = [
    "Inspection Type", "Date From", "Date To", "Total Days",
    "Total Audits", "Total Check", "Total Defect", "Total Pass",
    "Item Names", "Auditors",
]


def _write_master_sheet(wb, meta: dict, by_type: dict):
    if "MASTER" in wb.sheetnames:
        ws = wb["MASTER"]
        # Clear existing data rows (keep row 1 as header)
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
            for cell in row:
                cell.value = None
    else:
        ws = wb.create_sheet(title="MASTER")

    ws.sheet_view.showGridLines = False

    # Title
    ws.merge_cells("A1:J1")
    title_cell = ws["A1"]
    title_cell.value     = "Audit Summary Report"
    title_cell.font      = Font(bold=True, size=14, color="FFFFFF", name="Arial")
    title_cell.fill      = _HEADER_FILL
    title_cell.alignment = _CENTER
    ws.row_dimensions[1].height = 28

    # Meta info row
    date_range = f"{_fmt_date(meta['date_from'])} – {_fmt_date(meta['date_to'])}"
    ws.merge_cells("A2:D2")
    c = ws["A2"]
    c.value = f"Period: {date_range}"
    c.font  = _LABEL_FONT
    c.alignment = _LEFT

    if meta.get("factory"):
        ws.merge_cells("E2:G2")
        c = ws["E2"]
        c.value = f"Factory: {meta['factory']}"
        c.font  = _LABEL_FONT

    if meta.get("client"):
        ws.merge_cells("H2:J2")
        c = ws["H2"]
        c.value = f"Client: {meta['client']}"
        c.font  = _LABEL_FONT

    fmt_label = "Buyer Format" if meta.get("format") == "buyer" else "Internal Format"
    ws.merge_cells("A3:J3")
    c = ws["A3"]
    c.value = fmt_label
    c.font  = Font(italic=True, name="Arial", size=9, color="595959")
    c.alignment = _LEFT

    # Column headers row 4
    _header_row(ws, 4, _MASTER_COLS)
    ws.row_dimensions[4].height = 22

    # Data rows
    for i, (itype, block) in enumerate(by_type.items(), start=5):
        fill = _ALT_FILL if i % 2 == 0 else None
        row_data = [
            itype,
            _fmt_date(block.get("date_from")),
            _fmt_date(block.get("date_to")),
            block.get("total_days", 0),
            block.get("total_audits", 0),
            block.get("total_check", 0),
            block.get("total_defect", 0),
            block.get("total_pass", 0),
            ", ".join(block.get("item_names", [])),
            ", ".join(block.get("auditors", [])),
        ]
        for j, val in enumerate(row_data, start=1):
            _write(ws, i, j, val, font=_DATA_FONT, fill=fill,
                   align=_CENTER if j in (1, 4, 5, 6, 7, 8) else _LEFT)

    # Column widths
    widths = [22, 16, 16, 12, 14, 14, 14, 14, 45, 40]
    for col_idx, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = w


# ─────────────────────────────────────────────────────────────────────────────
# Helper sheet (per inspection type)
# ─────────────────────────────────────────────────────────────────────────────

def _write_helper_sheet(ws, meta: dict, block: dict):
    ws.sheet_view.showGridLines = False

    itype      = block.get("inspection_type", "")
    date_from  = block.get("date_from")
    date_to    = block.get("date_to")
    date_range = f"{_fmt_date(date_from)} – {_fmt_date(date_to)}"
    fmt        = meta.get("format", "buyer")

    # ── Section 1: Summary header block (rows 1-8) ───────────────────────────
    ws.merge_cells("A1:H1")
    c = ws["A1"]
    c.value     = f"Audit Summary — {itype}"
    c.font      = Font(bold=True, size=13, color="FFFFFF", name="Arial")
    c.fill      = _HEADER_FILL
    c.alignment = _CENTER
    ws.row_dimensions[1].height = 26

    summary_labels = [
        ("B2", "Inspection Type", "C2", itype),
        ("B3", "Date Range",      "C3", date_range),
        ("B4", "Total Days",      "C4", block.get("total_days", 0)),
        ("B5", "Factory",         "C5", meta.get("factory", "—")),
        ("B6", "Client / Buyer",  "C6", meta.get("client", "—")),
        ("E2", "Total Audits",    "F2", block.get("total_audits", 0)),
        ("E3", "Total Check",     "F3", block.get("total_check", 0)),
        ("E4", "Total Defect",    "F4", block.get("total_defect", 0)),
        ("E5", "Total Pass",      "F5", block.get("total_pass", 0)),
        ("E6", "Auditor(s)",      "F6", ", ".join(block.get("auditors", []))),
    ]
    for label_cell, label_val, data_cell, data_val in summary_labels:
        c = ws[label_cell]
        c.value = label_val
        c.font  = _LABEL_FONT
        c.alignment = _LEFT
        c.border = _BORDER

        c2 = ws[data_cell]
        c2.value = data_val
        c2.font  = _DATA_FONT
        c2.alignment = _LEFT
        c2.border = _BORDER

    # Item names
    ws["B7"].value = "Item Names"
    ws["B7"].font  = _LABEL_FONT
    ws["B7"].border = _BORDER
    ws.merge_cells("C7:H7")
    c = ws["C7"]
    c.value = ", ".join(block.get("item_names", []))
    c.font  = _DATA_FONT
    c.alignment = _LEFT
    c.border = _BORDER

    # Row 9: spacing / section label
    ws.merge_cells("A9:H9")
    c = ws["A9"]
    c.value = "Daily Breakdown"
    c.font  = _SUBHEAD_FONT
    c.fill  = _SUBHEAD_FILL
    c.alignment = _CENTER

    # ── Section 2: Date table ─────────────────────────────────────────────────
    date_table_start = 10
    _header_row(ws, date_table_start,
                ["Date", "Check Qty", "Defect Qty", "Pass Qty", "Person", "Auditor", "# Audits"],
                start_col=2)
    ws.row_dimensions[date_table_start].height = 20

    date_rows = block.get("date_rows", [])
    for i, dr in enumerate(date_rows):
        row  = date_table_start + 1 + i
        fill = _ALT_FILL if i % 2 == 0 else None
        _write(ws, row, 2, _fmt_date(dr["date"]),   font=_DATA_FONT, fill=fill, align=_CENTER)
        _write(ws, row, 3, dr["check"],              font=_DATA_FONT, fill=fill, align=_CENTER)
        _write(ws, row, 4, dr["defect"],             font=_DATA_FONT, fill=fill, align=_CENTER)
        _write(ws, row, 5, dr["pass"],               font=_DATA_FONT, fill=fill, align=_CENTER)
        _write(ws, row, 6, dr["person"],             font=_DATA_FONT, fill=fill, align=_CENTER)
        _write(ws, row, 7, dr["auditor"],            font=_DATA_FONT, fill=fill, align=_LEFT)
        _write(ws, row, 8, dr["audits"],             font=_DATA_FONT, fill=fill, align=_CENTER)

    # Totals row
    total_row = date_table_start + 1 + len(date_rows)
    _write(ws, total_row, 2, "TOTAL",                font=Font(bold=True, name="Arial", size=10), align=_CENTER)
    _write(ws, total_row, 3, block.get("total_check", 0),   font=Font(bold=True, name="Arial"), align=_CENTER)
    _write(ws, total_row, 4, block.get("total_defect", 0),  font=Font(bold=True, name="Arial"), align=_CENTER)
    _write(ws, total_row, 5, block.get("total_pass", 0),    font=Font(bold=True, name="Arial"), align=_CENTER)
    _write(ws, total_row, 6, "")
    _write(ws, total_row, 7, "")
    _write(ws, total_row, 8, block.get("total_audits", 0),  font=Font(bold=True, name="Arial"), align=_CENTER)

    # ── Section 3: Top-5 defects ──────────────────────────────────────────────
    top5_start = total_row + 3

    pct_label = (
        "% of Total Check" if fmt == "buyer"
        else "% of Total Defects"
    )

    ws.merge_cells(f"A{top5_start}:H{top5_start}")
    c = ws[f"A{top5_start}"]
    c.value = "Top 5 Defects"
    c.font  = _SUBHEAD_FONT
    c.fill  = _SUBHEAD_FILL
    c.alignment = _CENTER

    top5_hdr_row = top5_start + 1
    _header_row(ws, top5_hdr_row,
                ["Rank", "Category", "Defect Item", "Qty", pct_label],
                start_col=2)

    for i, d in enumerate(block.get("top5_defects", [])):
        row  = top5_hdr_row + 1 + i
        fill = _ALT_FILL if i % 2 == 0 else None
        _write(ws, row, 2, d["rank"],       font=_DATA_FONT, fill=fill, align=_CENTER)
        _write(ws, row, 3, d["category"],   font=_DATA_FONT, fill=fill, align=_LEFT)
        _write(ws, row, 4, d["item"],       font=_DATA_FONT, fill=fill, align=_LEFT)
        _write(ws, row, 5, d["qty"],        font=_DATA_FONT, fill=fill, align=_CENTER)
        _write(ws, row, 6, d["percentage"], font=_DATA_FONT, fill=fill, align=_CENTER, num_fmt="0.00%")

    # ── Column widths ─────────────────────────────────────────────────────────
    col_widths = {1: 3, 2: 16, 3: 18, 4: 18, 5: 14, 6: 14, 7: 35, 8: 12}
    for col_idx, w in col_widths.items():
        ws.column_dimensions[get_column_letter(col_idx)].width = w


# ─────────────────────────────────────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────────────────────────────────────

def _safe_sheet_name(name: str) -> str:
    """Excel sheet names max 31 chars, no special chars."""
    invalid = r'\/:*?[]'
    clean = "".join(c for c in name if c not in invalid)
    return clean[:31].strip() or "Sheet"