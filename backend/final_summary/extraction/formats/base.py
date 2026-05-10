"""
---------------------------
BaseExtractor — shared extraction pipeline used by all format extractors.

Every format extractor (Knit35, Woven37, Woven78, Sweater37) inherits this
class and calls super().extract().  Format-specific extractors only override
what is different for their Excel layout.

Pipeline (in order)
-------------------
1.  Load the target sheet into a CellGrid.
2.  Run FIELD_EXTRACTORS (single-value fields: factory, client, style, etc.)
3.  Run extract_with_country() → style_no + country
4.  Run extract_times()        → factory/audit in/out + derived totals
5.  Run extract_dates()        → exf, po_edt, po_wh, plan_edt, plan_wh
6.  Run extract_quantities()   → po_qty, ship_qty, audit_qty, defect_qty, etc.
7.  Run extract_personnel()    → inspector, person, carton, remarks, etc.
8.  Run extract_defects()      → defect_rows + update defect_qty if missing
9.  Run extract_do_table()     → do_orders, do_totals, do_note
10. Inject inspection_date     → from batch (user-selected, not from sheet)
11. Run post_process()         → hook for format-specific overrides
12. Crosscheck factory/client  → compare extracted vs registered pair names

date_of_issue is NEVER extracted from the sheet.
It is injected from batch.inspection_date in step 10.

Usage
-----
    from extraction.formats import get_extractor
    extractor = get_extractor(pair)        # returns the right subclass instance
    record    = extractor.extract(path, sheet_name, inspection_date, pair)
"""

import logging
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from final_summary.extraction.core import (
    CellGrid,
    read_sheet,
)
from final_summary.extraction.fields import (
    FIELD_EXTRACTORS,
    extract_with_country,
    extract_times,
    extract_dates,
    extract_quantities,
    extract_personnel,
    extract_defects,
    extract_do_table,
    extract_type_from_filename,
)


# ---------------------------------------------------------------------------
# AuditRecord dataclass — the extraction result
# ---------------------------------------------------------------------------

@dataclass
class AuditRecord:
    """
    All data extracted from one Excel audit file.
    Populated by BaseExtractor.extract() and persisted by the task layer.
    """

    # Source
    file_name: str
    sheet_name: str = ""

    # Identity / header
    factory:         str = ""
    client:          str = ""
    date_of_issue:   str = ""   # always injected from batch — never extracted
    inspection_type: str = ""
    report_no:       str = ""
    item_name:       str = ""
    style_no:        str = ""
    po_no:           str = ""
    country:         str = ""

    # Time fields
    factory_in_time:     str = ""
    factory_out_time:    str = ""
    factory_total_hours: str = ""
    audit_start_time:    str = ""
    audit_end_time:      str = ""
    audit_total_hours:   str = ""

    # Audit outcome
    audit_result: str = "-"

    # Quantity fields
    po_qty:      str = ""
    po_qty_pcs:  int = 0
    po_qty_pack: int = 0
    po_qty_set:  int = 0
    do_qty:      int = 0
    ship_qty:    str = ""
    audit_qty:   str = ""

    # Shipment dates
    exf:      str = ""
    po_edt:   str = ""
    po_wh:    str = ""
    plan_edt: str = ""
    plan_wh:  str = ""

    # Defect summary
    defect_qty:            str = ""
    acceptable_defect_qty: str = "-"
    defect_percentage:     str = ""

    # Personnel
    person:    str = ""
    inspector: str = ""

    # Additional checks
    carton:          str = ""
    needle_detector: str = ""
    remarks:         str = ""
    do_set_col_size: str = ""

    # Extracted names (for cross-check against pair registration)
    factory_extracted: str = ""
    client_extracted:  str = ""

    # Structured data
    defect_rows: List[Dict[str, Any]] = field(default_factory=list)
    do_orders:   List[Dict[str, Any]] = field(default_factory=list)
    do_totals:   Dict[str, Any]       = field(default_factory=dict)
    do_note:     str                  = ""

    # Validation
    validation_errors:  List[str] = field(default_factory=list)
    blocking_errors:    List[str] = field(default_factory=list)
    cross_check_warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# BaseExtractor
# ---------------------------------------------------------------------------

class BaseExtractor:
    """
    Shared extraction pipeline.  Subclasses override SYNONYMS or individual
    extract_* methods when the format differs from the base layout.

    Class attributes (overridable by subclasses)
    --------------------------------------------
    REPORT_TYPE : str — e.g. "KNIT_35"
    """

    REPORT_TYPE: str = "BASE"

    def extract(
        self,
        path: Path,
        sheet_name: str,
        inspection_date: date,
        pair=None,          # BuyerFactoryPair instance — used for cross-check
    ) -> AuditRecord:
        """
        Run the full extraction pipeline and return an AuditRecord.

        Parameters
        ----------
        path            : Path to the Excel file
        sheet_name      : Which sheet to read (resolved upstream)
        inspection_date : User-selected date; stored as date_of_issue
        pair            : BuyerFactoryPair — for registered name cross-check
        """
        record = AuditRecord(
            file_name=path.name,
            sheet_name=sheet_name,
        )

        # ── Load sheet ─────────────────────────────────────────────────────
        try:
            df   = self._read_sheet(path, sheet_name)
            grid = CellGrid(df)
        except Exception as exc:
            record.blocking_errors.append(
                f"SHEET_READ_ERROR | Cannot read sheet '{sheet_name}': {exc}"
            )
            return record

        # ── Step 2: single-value fields ────────────────────────────────────
        for field_name, extractor_fn in self._field_extractors().items():
            try:
                value = extractor_fn(grid, path)
                if value:
                    setattr(record, field_name, value)
            except Exception as exc:
                logging.warning(
                    f"[{path.name}] Field '{field_name}' extraction failed: {exc}"
                )

        # ── Step 3: style_no + country ─────────────────────────────────────
        try:
            style, country = self._extract_style_country(grid, path)
            if style:
                record.style_no = style
                record.country  = country
        except Exception as exc:
            logging.warning(f"[{path.name}] style/country extraction failed: {exc}")

        # ── Step 4: times ──────────────────────────────────────────────────
        try:
            times = self._extract_times(grid, path)
            for k, v in times.items():
                if v:
                    setattr(record, k, v)
        except Exception as exc:
            logging.warning(f"[{path.name}] Times extraction failed: {exc}")

        # ── Step 5: dates ──────────────────────────────────────────────────
        try:
            dates = self._extract_dates(grid, path)
            for k, v in dates.items():
                if v:
                    setattr(record, k, v)
        except Exception as exc:
            logging.warning(f"[{path.name}] Dates extraction failed: {exc}")

        # ── Step 6: quantities ─────────────────────────────────────────────
        try:
            qtys = self._extract_quantities(grid, path)
            for k, v in qtys.items():
                if v:
                    setattr(record, k, v)
        except Exception as exc:
            logging.warning(f"[{path.name}] Quantities extraction failed: {exc}")

        # ── Step 7: personnel ──────────────────────────────────────────────
        try:
            pers = self._extract_personnel(grid, path)
            for k, v in pers.items():
                if v:
                    setattr(record, k, v)
        except Exception as exc:
            logging.warning(f"[{path.name}] Personnel extraction failed: {exc}")

        # ── Step 8: defects ────────────────────────────────────────────────
        try:
            defect_rows, defect_totals = self._extract_defects(path, sheet_name)
            record.defect_rows = defect_rows
            # Use defect table major total if header extraction missed it
            if not record.defect_qty and defect_totals.get("major"):
                record.defect_qty = str(defect_totals["major"])
        except Exception as exc:
            logging.warning(f"[{path.name}] Defects extraction failed: {exc}")

        # ── Step 9: DO table ───────────────────────────────────────────────
        try:
            do_data = self._extract_do_table(path, sheet_name)
            record.do_orders = do_data.get("do_orders", [])
            record.do_totals = do_data.get("do_totals", {})
            record.do_note   = do_data.get("do_note", "")
        except Exception as exc:
            logging.warning(f"[{path.name}] DO table extraction failed: {exc}")

        # ── Step 10: inject inspection_date ───────────────────────────────
        record.date_of_issue = inspection_date.strftime("%m/%d/%Y")

        # ── Inspection type fallback from file name ─────────────────────────
        if not record.inspection_type:
            record.inspection_type = extract_type_from_filename(
                path.stem,
                audit_qty=record.audit_qty,
                ship_qty=record.ship_qty,
            )

        # ── Step 11: format-specific post-processing ───────────────────────
        record = self.post_process(record, grid, path)

        # ── Step 12: cross-check vs pair registration ──────────────────────
        if pair:
            record = self._crosscheck(record, pair)

        return record

    # ------------------------------------------------------------------
    # Overridable extraction methods
    # ------------------------------------------------------------------

    def _read_sheet(self, path: Path, sheet_name: str):
        """Load the sheet DataFrame. Override to apply skiprows etc."""
        return read_sheet(path, sheet_name=sheet_name)

    def _field_extractors(self) -> dict:
        """
        Return the field extractor registry.
        Subclasses can override to add/remove/replace individual fields.
        """
        return FIELD_EXTRACTORS.copy()

    def _extract_style_country(self, grid: CellGrid, path: Path) -> Tuple[str, str]:
        return extract_with_country(grid, path)

    def _extract_times(self, grid: CellGrid, path: Path) -> dict:
        return extract_times(grid, path)

    def _extract_dates(self, grid: CellGrid, path: Path) -> dict:
        return extract_dates(grid, path)

    def _extract_quantities(self, grid: CellGrid, path: Path) -> dict:
        return extract_quantities(grid, path)

    def _extract_personnel(self, grid: CellGrid, path: Path) -> dict:
        return extract_personnel(grid, path)

    def _extract_defects(self, path: Path, sheet_name: str):
        return extract_defects(path=path, sheet_name=sheet_name)

    def _extract_do_table(self, path: Path, sheet_name: str) -> dict:
        return extract_do_table(path=path, sheet_name=sheet_name)

    def post_process(
        self,
        record: AuditRecord,
        grid: CellGrid,
        path: Path,
    ) -> AuditRecord:
        """
        Format-specific post-processing hook.
        Override in subclasses to apply layout-specific corrections.
        Default implementation returns the record unchanged.
        """
        return record

    # ------------------------------------------------------------------
    # Cross-check
    # ------------------------------------------------------------------

    def _crosscheck(self, record: AuditRecord, pair) -> AuditRecord:
        """
        Compare extracted factory/client names against the registered pair.
        Mismatches are non-blocking — they go to cross_check_warnings.
        """
        record.factory_extracted = record.factory
        record.client_extracted  = record.client

        registered_factory = pair.factory.name.strip().lower()
        registered_buyer   = pair.buyer.name.strip().lower()

        extracted_factory = record.factory.strip().lower()
        extracted_client  = record.client.strip().lower()

        if extracted_factory and extracted_factory != registered_factory:
            warn = (
                f"FACTORY_MISMATCH | "
                f"extracted='{record.factory}' "
                f"registered='{pair.factory.name}'"
            )
            record.cross_check_warnings.append(warn)
            logging.warning(f"[{record.file_name}] {warn}")

        if extracted_client and extracted_client != registered_buyer:
            warn = (
                f"CLIENT_MISMATCH | "
                f"extracted='{record.client}' "
                f"registered='{pair.buyer.name}'"
            )
            record.cross_check_warnings.append(warn)
            logging.warning(f"[{record.file_name}] {warn}")

        # Use registered names as the canonical values
        record.factory = pair.factory.name
        record.client  = pair.buyer.name

        return record