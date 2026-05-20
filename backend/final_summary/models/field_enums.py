"""
field_enums.py
--------------
All Enum definitions for the audit extraction system.

To add a new field:
  1. Add the field name to FieldName.
  2. Add synonyms to LabelSynonym.
  3. Wire them together in label_config.py → LABELS.

To add a new country prefix:
  - Add to StyleCountryPrefix and update STYLE_COUNTRY_MAP in label_config.py.
"""

from enum import Enum


# ---------------------------------------------------------------------------
# Field Names  (must match AuditRecord attribute names exactly)
# ---------------------------------------------------------------------------

class FieldName(str, Enum):
    """Internal names for every field extracted from Excel audit reports."""

    # Identity / header
    FACTORY           = "factory"
    DATE_OF_ISSUE     = "date_of_issue"
    INSPECTION_TYPE   = "inspection_type"
    REPORT_NO         = "report_no"
    AUDIT_REPORT      = "audit_report"
    ITEM_NAME         = "item_name"
    STYLE_NO          = "style_no"
    PO_NO             = "po_no"
    COUNTRY           = "country"

    # Time fields
    FACTORY_IN_TIME     = "factory_in_time"
    FACTORY_OUT_TIME    = "factory_out_time"
    FACTORY_TOTAL_HOURS = "factory_total_hours"
    AUDIT_START_TIME    = "audit_start_time"
    AUDIT_END_TIME      = "audit_end_time"
    AUDIT_TOTAL_HOURS   = "audit_total_hours"

    # Audit outcome
    AUDIT_RESULT = "audit_result"

    # Quantity fields
    PO_QTY    = "po_qty"
    DO_QTY    = "do_qty"
    SHIP_QTY  = "ship_qty"
    AUDIT_QTY = "audit_qty"

    # Details of shipment dates
    EXF      = "exf"
    PO_EDT   = "po_edt"
    PO_WH    = "po_wh"
    PLAN_EDT = "plan_edt"
    PLAN_WH  = "plan_wh"

    # Defect summary
    DEFECT_QTY            = "defect_qty"
    ACCEPTABLE_DEFECT_QTY = "acceptable_defect_qty"
    DEFECT_PERCENTAGE     = "defect_percentage"

    # Personnel
    PERSON    = "person"
    INSPECTOR = "inspector"

    # Additional checks
    CARTON           = "carton"
    NEEDLE_DETECTOR  = "needle_detector"
    REMARKS          = "remarks"
    DO_SET_COL_SIZE  = "do_set_col_size"
    CARTON_NUMBER    = "carton_number"

    DETAILS_OF_SHIPMENT = "details_of_shipment"

    # Client / buyer (extracted from Excel label "client")
    CLIENT = "client"


# ---------------------------------------------------------------------------
# Label Synonyms  (all text variants that appear in Excel headers)
# ---------------------------------------------------------------------------

class LabelSynonym(str, Enum):
    """
    Synonyms for column/row labels found in Excel audit sheets.
    Add new spellings here when a new sheet format is encountered.
    """

    # Factory
    FACTORY      = "factory"
    FACTORY_NAME = "factory name"

    # Date of Issue
    DATE_OF_ISSUE   = "date of issue"
    ISSUE_DATE      = "issue date"
    REPORT_DATE     = "report date"
    INSPECTION_DATE = "inspection date"

    # Inspection Type
    INSPECTION_TYPE = "inspection type"
    AUDIT_TYPE      = "audit type"

    # Factory Times
    FACTORY_IN_TIME  = "factory in time"
    FACTORY_INTIME   = "factory in-time"
    FACTORY_INTIME2  = "factory intime"
    IN_TIME          = "in time"
    FACTORY_OUT_TIME = "factory out time"
    FACTORY_OUTTIME  = "factory out-time"
    FACTORY_OUTTIME2 = "factory outtime"
    OUT_TIME         = "out time"

    # Audit Times
    AUDIT_START_TIME = "audit start time"
    START_TIME       = "start time"
    AUDIT_END_TIME   = "audit end time"
    END_TIME         = "end time"

    # Audit Result
    AUDIT_RESULT      = "audit result"
    RESULT            = "result"
    INSPECTION_RESULT = "inspection result"

    # Report / PO numbers
    REPORT_NO            = "report no"
    REPORT_NUMBER        = "report number"
    INSPECTION_REPORT_NO = "inspection report no"
    # Local_Sample_Code    = "local sample code"

    # Item Name
    ITEM_NAME   = "item name"
    DESCRIPTION = "description"

    # Style No
    STYLE_NO          = "style no"
    STYLE_NUMBER      = "style number"
    STYLE             = "style"
    LOCAL_SAMPLE_CODE = "local sample code"

    # PO No
    PO_NO             = "po no"
    PO_NO_DASH        = "po-no"
    PURCHASE_ORDER_NO = "purchase order no"

    # PO Quantity
    PO_QTY      = "po qty"
    PO_QUANTITY = "po quantity"
    PO_QTY_CAPS = "p.o qty"

    # DO Quantity
    DO_QTY      = "do qty"
    DO_QUANTITY = "do quantity"
    DO_QTY_CAPS = "d.o qty"

    # EXF date
    EXF   = "exf"
    EXF_  = "exf:"
    EXF__ = "exf :"

    # PO EDT
    PO_EDT   = "po. etd"
    _PO_EDT  = "po etd"
    PO__EDT  = "po.  etd"
    _PO__EDT = "po  etd"

    # PO Warehouse
    PO_WH       = "po wh"
    WAREHOUSE   = "warehouse"
    POWH        = "powh"
    PO_WH_SLASH = "po w/h"

    # Plan EDT
    PLAN_ETD  = "plan etd"
    PLAN__ETD = "plan  etd"

    # Plan WH
    PLAN_WH  = "plan wh"
    PLAN__WH = "plan  wh"

    # Ship Quantity
    SHIP_QTY               = "ship qty"
    SHIPMENT_QTY           = "shipment qty"
    SHIPPING_QUANTITY      = "shipping quantity"
    SHIPPING_QTY           = "shipping qty"
    AUDIT_FOR_SHIPPING_QTY = "audit for shipping qty"
    EXF_QTY                = "exf qty"

    # Audit Quantity
    AUDIT_QTY        = "audit qty"
    AUDITED_QUANTITY = "audited quantity"
    QTY_INSPECTED    = "qty.\ninspected"

    # Personnel
    INSPECTOR = "inspector"
    PERSON    = "person"

    # Defect qty (major column header in summary section)
    MAJOR_DEFECTS = "major\ndefects"

    # Carton / inspection carton
    OUR_INSPECTION_CARTON_NUMBER = "our inspection carton number"
    CARTON_INSPECTION            = "carton inspection"
    INSPECTION_CARTON            = "inspection carton"
    INSPECTION_CTN               = "inspection ctn"
    OUR_INSPECTION_CARTON        = "our inspection carton"

    # Needle detector
    NEEDLE_DETECTOR       = "needle detector"
    NEEDLE_DETECTOR_CHECK = "needle detector check"

    # Remarks
    REMARKS = "remarks"
    REMARK  = "remark"

    # DO/Set/Col/Size
    DO_SET_COL_SIZE = "do/set/col/size"

    # Client / buyer
    CLIENT       = "client"
    CLIENT_NAME  = "client name"
    BUYER        = "buyer"
    BUYER_NAME   = "buyer name"


# ---------------------------------------------------------------------------
# Direction Rules
# ---------------------------------------------------------------------------

class DirectionRule(str, Enum):
    """
    Controls where resolve_value() looks for the field value relative to the
    label cell.

    RIGHT            → scan right across the same row
    DOWN             → scan down the same column
    DOWN_IF_INT      → scan down but only accept integer values
    RIGHT_THEN_DOWN  → try right first, fall back to down
    DOWN_THEN_RIGHT  → try down first, fall back to right
    """
    RIGHT           = "right"
    DOWN            = "down"
    DOWN_IF_INT     = "down_if_int"
    RIGHT_THEN_DOWN = "right_then_down"
    DOWN_THEN_RIGHT = "down_then_right"


# ---------------------------------------------------------------------------
# Audit Type Patterns
# ---------------------------------------------------------------------------

class AuditPattern(str, Enum):
    """Keys used in AUDIT_PATTERNS regex map (label_config.py)."""
    RE_FINAL = "RE-FINAL"
    FINAL    = "FINAL"
    INLINE   = "INLINE"
    SAMPLE   = "SAMPLE"
    CMF      = "CMF"


# ---------------------------------------------------------------------------
# Style Number Country Prefixes
# ---------------------------------------------------------------------------

class StyleCountryPrefix(str, Enum):
    """
    First two characters of a style number that encode the destination country.
    Update STYLE_COUNTRY_MAP in label_config.py if new prefixes are added.
    """
    JAPAN  = "01"
    CHINA  = "03"
    USA    = "04"
    KOREA  = "05"
    EUROPE = "07"
    TAIWAN = "10"
    AU     = "14"
    CANADA = "17"
    INDIA  = "36"


# ---------------------------------------------------------------------------
# D.O. Table Column Names
# ---------------------------------------------------------------------------

class DOFieldName(str, Enum):
    """Internal names for every column in the Delivery Order plan table."""
    DATE       = "date"
    PO_QTY     = "po_qty"
    DO_NO      = "do_no"
    DO_QTY     = "do_qty"
    SHIP_QTY   = "ship_qty"
    AUDIT_QTY  = "audit_qty"
    DO_BALANCE = "do_balance"
    PO_EXTRA   = "po_extra"
    REMARKS    = "remarks"
    PO_BALANCE = "po_balance"


# ---------------------------------------------------------------------------
# D.O. Table Label Synonyms
# ---------------------------------------------------------------------------

class DOLabelSynonym(str, Enum):
    """All header text variants that can identify a D.O. table column."""

    DATE = "date"

    PO_QTY       = "po qty"
    P_O_QTY      = "p o qty"
    PO_QUANTITY  = "po quantity"
    P_O_QUANTITY = "p o quantity"

    DO_NO             = "do no"
    D_O_NO            = "d o no"
    DO_NUMBER         = "do number"
    D_O_NUMBER        = "d o number"
    DELIVERY_ORDER_NO = "delivery order no"

    DO_QTY       = "do qty"
    D_O_QTY      = "d o qty"
    DO_QUANTITY  = "do quantity"
    D_O_QUANTITY = "d o quantity"

    SHIP_QTY          = "ship qty"
    SHIP_QUANTITY     = "ship quantity"
    SHIPMENT_QTY      = "shipment qty"
    SHIPMENT_QUANTITY = "shipment quantity"

    AUDIT_QTY      = "audit qty"
    AUDIT_QUANTITY = "audit quantity"
    AUDITED_QTY    = "audited qty"

    DO_BALANCE           = "do balance"
    D_O_BALANCE          = "d o balance"
    DO_BALANCE_EXTRA     = "do balance extra"
    DO_BALANCE_AND_EXTRA = "do balance and extra"
    BALANCE_EXTRA        = "balance extra"

    PO_EXTRA  = "po extra"
    P_O_EXTRA = "p o extra"

    REMARKS                       = "remarks"
    BALANCE_QTY_PLAN              = "balance qty plan"
    BALANCE_QTY_PLAN_DATE         = "balance qty plan date"
    BALANCE_QTY_PLAN_DATE_REMARKS = "balance qty plan date remarks"
    PLAN_DATE_REMARKS             = "plan date remarks"

    PO_BALANCE = "po balance"
    PO_BAL     = "po bal"
