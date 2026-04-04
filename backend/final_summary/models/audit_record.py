"""
audit_record.py
---------------
Data model for a single audit report.

All fields default to sensible empty values so the object can be created
immediately after extraction without every value being present.

Notes
-----
- `po_qty` holds the *raw* extracted string (e.g. "1,200 PCS").
  Processed integers live in po_qty_pcs / po_qty_pack / po_qty_set.

- `client` is extracted from the Excel using the label "client".  It maps
  to the buyers/clients table in the DB and the factory+client combination
  determines the output Excel filename.

- `defect_rows` is the structured defect list (auto-discovered from sheet).
  Each element is:
      {"category": "B : Sewing", "item": "3.Pieces not symmetrical",
       "major": 1, "minor": 0, "comment": "CUFF POINT UP-DOWN"}

- `validation_errors` is serialised as a comma-joined string in to_dict().
"""

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List


@dataclass
class AuditRecord:
    """Represents one audit report extracted from an Excel file."""

    # Source
    file_name: str

    # Identity / header
    factory:         str = ""
    client :         str = ""
    date_of_issue:   str = ""   # normalised to MM/DD/YYYY by validator
    inspection_type: str = ""
    report_no:       str = ""
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
    po_qty:      str = ""  # raw extracted string e.g. "1200 PCS"
    po_qty_pcs:  int = 0   # populated by post_processor
    po_qty_pack: int = 0
    po_qty_set:  int = 0
    do_qty:      int = 0

    # Shipment date fields
    exf:      str = ""
    po_edt:   str = ""
    po_wh:    str = ""
    plan_edt: str = ""
    plan_wh:  str = ""

    shipment_dates: str = ""

    ship_qty:  str = ""
    audit_qty: str = ""

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

    # Structured defect data (auto-discovered from the defect table)
    defect_rows: List[Dict[str, Any]] = field(default_factory=list)

    # D.O. plan table
    do_orders: List[Dict[str, Any]] = field(default_factory=list)
    do_totals: Dict[str, Any]       = field(default_factory=dict)
    do_note:   str                  = ""

    # Validation
    validation_errors: List[str] = field(default_factory=list)

    # Blocking errors — records with these are NEVER inserted into the DB.
    # Populated by validate_blocking() in validator.py.
    # Examples: required field empty, defect sum ≠ header defect_qty.
    blocking_errors: List[str] = field(default_factory=list)

    # Which static defect template was matched (28 / 35 / 78 item list).
    # Set by db_manager when saving; None until then.
    defect_template_id: int = 0

    # -------------------------------------------------------------------------
    # Serialisation
    # -------------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """
        Flat dict suitable for DataFrame / Excel row creation.

        `defect_rows` is excluded from the flat dict (handled separately
        by summary_writer). `validation_errors` is joined into a single
        comma-separated string.
        """
        data = asdict(self)
        data.pop("defect_rows", None)
        data["validation_errors"] = ", ".join(self.validation_errors)
        return data

    def to_json_dict(self) -> Dict[str, Any]:
        """
        Full dict for JSON serialisation — includes defect_rows, do_orders,
        do_totals, and validation_errors as a list (not joined string).
        Used by json_writer for export and round-trip import.
        """
        return asdict(self)
