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

FIX APPLIED (Bug #1 — parameter mismatch)
------------------------------------------
All calls to per-field extractor functions now pass `path` as the second
positional argument and `format_type` as a keyword argument:

    extractor_fn(grid, path, format_type=self.REPORT_TYPE)   # ✅ correct



This caused:
  • Fixed-cell fallbacks (FORMAT_FIXED_CELLS) never firing → ship_qty / audit_qty
    always empty → blocking errors.
  • Filename-based inspection_type inference breaking (path.stem on a string).
  • report_no fixed-cell fallback (FORMAT_FIXED_CELLS["WOVEN_78"]) never used.

The same fix is applied in _fill_missing_from_all_sheets().

FIX APPLIED (Bug #3 — missing audit_report field)
---------------------------------------------------
Added audit_report field back to AuditRecord dataclass so the pipeline
never silently drops that piece of data.
"""

import logging
import re
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

logger = logging.getLogger(__name__)


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
    file_name:  str
    sheet_name: str = ""

    # Identity / header
    factory:         str = ""
    client:          str = ""
    date_of_issue:   str = ""   
    inspection_type: str = ""
    audit_report:    str = ""   
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
    validation_errors:    List[str] = field(default_factory=list)
    blocking_errors:      List[str] = field(default_factory=list)
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
    
    # Subclasses can override this (e.g. 31, 37, 78) 
    # Otherwise it is retrieved from the BuyerFactoryPair
    DEFECT_COUNT: Optional[int] = None

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
        # BUG FIX #1: pass `path` as the second positional argument so that
        # each extractor receives (grid, path, format_type=...) as designed.
        # Previously: extractor_fn(grid, format_type=self.REPORT_TYPE)
        #   → path received "WOVEN_78", format_type received ""
        # Now:        extractor_fn(grid, path, format_type=self.REPORT_TYPE)
        #   → path receives a real Path object, format_type receives "WOVEN_78"
        for field_name, extractor_fn in self._field_extractors().items():
            try:
                value = extractor_fn(grid, path, format_type=self.REPORT_TYPE)  # ✅ FIXED
                if value:
                    setattr(record, field_name, value)
                    logger.info(f"  [{field_name}] -> '{value}'")
                else:
                    logger.info(f"  [{field_name}] -> Not found on primary sheet")
            except Exception as exc:
                logger.error(
                    f"[{path.name}] Field '{field_name}' extraction EXCEPTION: {exc}"
                )

        # ── Step 3: style_no + country ─────────────────────────────────────
        try:
            style, country = self._extract_style_country(grid, path)
            if style:
                record.style_no = style
                record.country  = country
                logger.info(f"  [style_no] -> '{style}'")
                logger.info(f"  [country] -> '{country}'")
            else:
                logger.info(f"  [style_no] -> Not found on primary sheet")
        except Exception as exc:
            logger.error(f"[{path.name}] style/country extraction FAILED: {exc}")

        # ── Step 4: times ──────────────────────────────────────────────────
        try:
            times = self._extract_times(grid, path)
            for k, v in times.items():
                if v and str(v).strip():
                    setattr(record, k, v)
                    logger.info(f"  [{k}] -> '{v}'")
        except Exception as exc:
            logger.error(f"[{path.name}] Times extraction FAILED: {exc}")

        # ── Step 5: dates ──────────────────────────────────────────────────
        try:
            dates = self._extract_dates(grid, path)
            for k, v in dates.items():
                if v and str(v).strip():
                    setattr(record, k, v)
                    logger.info(f"  [{k}] -> '{v}'")
        except Exception as exc:
            logger.error(f"[{path.name}] Dates extraction FAILED: {exc}")

        # ── Step 6: quantities ─────────────────────────────────────────────
        try:
            qtys = self._extract_quantities(grid, path, self.REPORT_TYPE)
            for k, v in qtys.items():
                if v and str(v).strip():
                    setattr(record, k, v)
                    logger.info(f"  [{k}] -> '{v}'")
        except Exception as exc:
            logger.error(f"[{path.name}] Quantities extraction FAILED: {exc}")

        # ── Step 7: personnel ──────────────────────────────────────────────
        try:
            pers = self._extract_personnel(grid, path)
            for k, v in pers.items():
                if v and str(v).strip():
                    setattr(record, k, v)
                    logger.info(f"  [{k}] -> '{v}'")
        except Exception as exc:
            logger.error(f"[{path.name}] Personnel extraction FAILED: {exc}")

        # ── Step 7b: fill missing fields from other sheets ─────────────────
        try:
            self._fill_missing_from_all_sheets(record, path)
        except Exception as exc:
            logger.error(f"[{path.name}] Multi-sheet fill FAILED: {exc}")

        # ── Step 7c: Final Field Presence Validation ───────────────────────
        for field_name in ["factory", "client", "ship_qty", "audit_qty"]:
            val = getattr(record, field_name, "")
            if not val or not str(val).strip():
                logger.error(
                    f"  [CRITICAL ERROR] Field '{field_name}' is MISSING "
                    f"after full workbook scan"
                )

        # ── Step 8: defects ────────────────────────────────────────────────
        try:
            defect_rows, defect_totals, meta = self._extract_defects(path, sheet_name, pair=pair)
            record.defect_rows = defect_rows
            logger.info(f"  [defects] -> extracted {len(defect_rows)} rows")
            if not record.defect_qty and defect_totals.get("major"):
                record.defect_qty = str(defect_totals["major"])
                logger.info(f"  [defect_qty] -> '{record.defect_qty}' (from table)")
        except Exception as exc:
            logger.error(f"[{path.name}] Defects extraction FAILED: {exc}")

        # ── Step 9: DO table ───────────────────────────────────────────────
        try:
            do_data = self._extract_do_table(path, sheet_name)
            record.do_orders = do_data.get("do_orders", [])
            record.do_totals = do_data.get("do_totals", {})
            record.do_note   = do_data.get("do_note", "")

            # If DO totals are empty, sum up the orders manually
            if not record.do_totals.get("ship_qty") and record.do_orders:
                manual_ship = sum(int(o.get("ship_qty") or 0) for o in record.do_orders)
                if manual_ship > 0:
                    record.do_totals["ship_qty"] = manual_ship
                    logger.info(
                        f"  [do_table] -> manually summed ship_qty: {manual_ship}"
                    )

            # Fallback: use DO totals for missing ship_qty
            if (
                (not record.ship_qty or not str(record.ship_qty).strip())
                and record.do_totals.get("ship_qty")
            ):
                record.ship_qty = str(record.do_totals["ship_qty"])
                logger.info(f"  [ship_qty] -> '{record.ship_qty}' (from DO table)")

        except Exception as exc:
            logger.error(f"[{path.name}] DO table extraction FAILED: {exc}")

        # ── Step 10: inject inspection_date ───────────────────────────────
        record.date_of_issue = inspection_date.strftime("%m/%d/%Y")
        logger.info(f"  [date_of_issue] -> '{record.date_of_issue}' (injected)")

        # ── Inspection type fallback from file name ────────────────────────
        if not record.inspection_type:
            record.inspection_type = extract_type_from_filename(
                path.stem,
                audit_qty=record.audit_qty,
                ship_qty=record.ship_qty,
            )
            logger.info(
                f"  [inspection_type] -> '{record.inspection_type}' (filename fallback)"
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

    def _fill_missing_from_all_sheets(self, record: AuditRecord, path: Path) -> None:
        """
        For every field still empty after main extraction, scan ALL sheets
        and fill in any values found.

        BUG FIX #1 (same fix as in extract()):
        All per-field extractor calls now pass `path` as a positional
        argument so the function signature (grid, path, format_type) is
        satisfied correctly.
        """
        from final_summary.extraction.fields import FIELD_EXTRACTORS
        from final_summary.extraction.core import read_all_sheets, CellGrid
        from final_summary.extraction.fields.times     import extract as extract_times_fn
        from final_summary.extraction.fields.dates     import extract as extract_dates_fn
        from final_summary.extraction.fields.quantities import extract as extract_quantities_fn
        from final_summary.extraction.fields.personnel  import extract as extract_personnel_fn

        # Collect which single-value fields are still empty
        missing_single = {
            name for name in FIELD_EXTRACTORS
            if not getattr(record, name, "")
        }
        need_times = not any([
            record.factory_in_time, record.factory_out_time,
            record.audit_start_time, record.audit_end_time,
        ])
        need_dates = not any([
            record.exf, record.po_edt, record.po_wh,
            record.plan_edt, record.plan_wh,
        ])
        need_quantities = not any([
            record.po_qty, record.ship_qty, record.audit_qty,
            record.defect_qty,
        ])
        need_personnel = not any([
            record.inspector, record.person, record.carton,
            record.needle_detector, record.remarks,
            record.audit_result and record.audit_result != "-",
            record.do_set_col_size,
        ])

        if (
            not missing_single and not need_times and not need_dates
            and not need_quantities and not need_personnel
        ):
            return

        logger.info(
            f"[{path.name}] Scanning all sheets for missing fields: "
            f"single={missing_single} times={need_times} dates={need_dates} "
            f"qtys={need_quantities} personnel={need_personnel}"
        )

        all_dfs = read_all_sheets(path)

        for sheet_idx, df in enumerate(all_dfs):
            if (
                not missing_single and not need_times and not need_dates
                and not need_quantities and not need_personnel
            ):
                break

            grid = CellGrid(df)

            # ── Single-value fields ────────────────────────────────────────
            for field_name in list(missing_single):
                fn = FIELD_EXTRACTORS.get(field_name)
                if not fn:
                    continue
                try:
                    # BUG FIX #1: pass path as positional argument ✅
                    value = fn(grid, path, format_type=self.REPORT_TYPE)
                    if value:
                        setattr(record, field_name, value)
                        missing_single.discard(field_name)
                        logger.info(
                            f"  [{field_name}] found on sheet {sheet_idx + 1}: '{value}'"
                        )
                except Exception:
                    pass

            # ── Times ─────────────────────────────────────────────────────
            if need_times:
                times = extract_times_fn(grid, path)
                for k, v in times.items():
                    if v and not str(getattr(record, k, "")).strip():
                        setattr(record, k, v)
                        logger.info(
                            f"  [{k}] found on sheet {sheet_idx + 1}: '{v}'"
                        )
                need_times = not any([
                    record.factory_in_time, record.factory_out_time,
                    record.audit_start_time, record.audit_end_time,
                ])

            # ── Dates ─────────────────────────────────────────────────────
            if need_dates:
                dates = extract_dates_fn(grid, path)
                for k, v in dates.items():
                    if v and not str(getattr(record, k, "")).strip():
                        setattr(record, k, v)
                        logger.info(
                            f"  [{k}] found on sheet {sheet_idx + 1}: '{v}'"
                        )
                need_dates = not any([
                    record.exf, record.po_edt, record.po_wh,
                    record.plan_edt, record.plan_wh,
                ])

            # ── Quantities ─────────────────────────────────────────────────
            if need_quantities:
                qtys = extract_quantities_fn(
                    grid, path, format_type=self.REPORT_TYPE
                )
                for k, v in qtys.items():
                    if v and not str(getattr(record, k, "")).strip():
                        setattr(record, k, v)
                        logger.info(
                            f"  [{k}] found on sheet {sheet_idx + 1}: '{v}'"
                        )
                need_quantities = not any([
                    record.po_qty, record.ship_qty, record.audit_qty,
                    record.defect_qty,
                ])

            # ── Personnel ─────────────────────────────────────────────────
            if need_personnel:
                pers = extract_personnel_fn(grid, path)
                for k, v in pers.items():
                    if v and not str(getattr(record, k, "")).strip():
                        setattr(record, k, v)
                        logger.info(
                            f"  [{k}] found on sheet {sheet_idx + 1}: '{v}'"
                        )
                need_personnel = not any([
                    record.inspector, record.person, record.carton,
                    record.needle_detector, record.remarks,
                    record.audit_result and record.audit_result != "-",
                    record.do_set_col_size,
                ])

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

    def _extract_quantities(
        self, grid: CellGrid, path: Path, format_type: str = ""
    ) -> dict:
        return extract_quantities(grid, path, format_type)

    def _extract_personnel(self, grid: CellGrid, path: Path) -> dict:
        return extract_personnel(grid, path)

    def _extract_defects(self, path: Path, sheet_name: str, pair: Any = None):
        """
        Extract defect rows using the defects field extractor.
        
        Note: This implementation is now a shell. Subclasses (Knit35, Woven78, etc.) 
        should override this to pass their specific defect_column_count 
        to ensure accurate positional ID/Serial mapping.
        """
        count = self.DEFECT_COUNT
        if count is None and pair:
            count = getattr(pair, "defect_column_count", 37)
            
        return extract_defects(
            path=path, 
            sheet_name=sheet_name, 
            defect_column_count=count, 
            pair=pair
        )

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
        Default implementation applies the remarks fallback parser.
        """
        self._parse_remarks_fallback(record)
        return record

    def _parse_remarks_fallback(self, record: AuditRecord) -> None:
        """Scrape missing values from record.remarks using regex."""
        if not record.remarks:
            return

        text = record.remarks.upper()

        if not record.factory_in_time:
            m = re.search(
                r"FACTORY IN TIME:?-?\s*(\d{1,2}[:.]\d{2}\s*(?:AM|PM)?)", text
            )
            if m:
                record.factory_in_time = m.group(1).replace(".", ":")

        if not record.factory_out_time:
            m = re.search(
                r"OUT TIME-?\s*(\d{1,2}[:.]\d{2}\s*(?:AM|PM)?)", text
            )
            if m:
                record.factory_out_time = m.group(1).replace(".", ":")

        if not record.audit_start_time:
            m = re.search(
                r"AUDIT START TIME:?-?\s*(\d{1,2}[:.]\d{2}\s*(?:AM|PM)?)", text
            )
            if m:
                record.audit_start_time = m.group(1).replace(".", ":")

        if not record.audit_end_time:
            m = re.search(
                r"(?:FINISHED|END) TIME-?\s*(\d{1,2}[:.]\d{2}\s*(?:AM|PM)?)", text
            )
            if m:
                record.audit_end_time = m.group(1).replace(".", ":")

        if not record.audit_qty or record.audit_qty == "0":
            m = re.search(r"TOTAL\s*=\s*(\d+)\s*PCS", text)
            if m:
                record.audit_qty = m.group(1)

        if not record.report_no:
            m = re.search(r"RE-FINAL AUDIT\s*-\s*(\d+)", text)
            if m:
                record.report_no = m.group(1)
            else:
                m = re.search(r"AUDIT\s*-\s*(\d+)", record.file_name.upper())
                if m:
                    record.report_no = m.group(1)

        if not record.person:
            m = re.search(r"(\d+)\s*PERSON", text)
            if m:
                record.person = m.group(1)

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
            logger.error(f"[{record.file_name}] {warn}")

        if extracted_client and extracted_client != registered_buyer:
            warn = (
                f"CLIENT_MISMATCH | "
                f"extracted='{record.client}' "
                f"registered='{pair.buyer.name}'"
            )
            record.cross_check_warnings.append(warn)
            logger.error(f"[{record.file_name}] {warn}")

        logger.info(f"  [factory_extracted] -> '{record.factory_extracted}'")
        logger.info(f"  [client_extracted] -> '{record.client_extracted}'")
        logger.info(f"  [factory] -> '{pair.factory.name}' (canonical)")
        logger.info(f"  [client] -> '{pair.buyer.name}' (canonical)")

        # Use registered names as the canonical values
        record.factory = pair.factory.name
        record.client  = pair.buyer.name

        return record