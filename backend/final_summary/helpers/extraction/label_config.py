"""
label_config.py
---------------
Central configuration for the extraction system.

This is the PRIMARY place to make changes when:
  - A new Excel format uses different label text  →  add to a LabelSynonym list
  - A label value lives in a different direction →  change DirectionRule
  - A new country code appears                  →  add to STYLE_COUNTRY_MAP
  - A new audit type keyword appears             →  update AUDIT_PATTERNS

Structure of LABELS dict
------------------------
Simple form (default direction = right_then_down):
    FieldName.FOO: [LabelSynonym.A, LabelSynonym.B]

Extended form (custom direction):
    FieldName.FOO: {
        "synonyms":  [LabelSynonym.A, LabelSynonym.B],
        "direction": DirectionRule.RIGHT,          # or a list of rules
    }
"""

from ...models.field_enums import (
    FieldName,
    LabelSynonym,
    DirectionRule,
    AuditPattern,
    StyleCountryPrefix,
)


# ---------------------------------------------------------------------------
# LABELS – field → (synonyms + optional direction rule)
# ---------------------------------------------------------------------------

LABELS: dict = {

    # ── Identity / header ──────────────────────────────────────────────────
    FieldName.FACTORY: [
        LabelSynonym.FACTORY_NAME,
        LabelSynonym.FACTORY,
    ],

    FieldName.DATE_OF_ISSUE: [
        LabelSynonym.DATE_OF_ISSUE,
        LabelSynonym.ISSUE_DATE,
        LabelSynonym.REPORT_DATE,
        LabelSynonym.INSPECTION_DATE,
    ],

    FieldName.INSPECTION_TYPE: [
        LabelSynonym.INSPECTION_TYPE,
        LabelSynonym.AUDIT_TYPE,
    ],

    FieldName.REPORT_NO: [
        LabelSynonym.REPORT_NO,
        LabelSynonym.REPORT_NUMBER,
        LabelSynonym.INSPECTION_REPORT_NO,
    ],

    FieldName.ITEM_NAME: [
        LabelSynonym.ITEM_NAME,
        LabelSynonym.DESCRIPTION,
    ],

    FieldName.STYLE_NO: [
        LabelSynonym.STYLE_NO,
        LabelSynonym.STYLE_NUMBER,
        LabelSynonym.STYLE,
        LabelSynonym.LOCAL_SAMPLE_CODE,
    ],

    FieldName.PO_NO: [
        LabelSynonym.PO_NO,
        LabelSynonym.PO_NO_DASH,
        LabelSynonym.PURCHASE_ORDER_NO,
        LabelSynonym.INSPECTION_REPORT_NO,
    ],

    FieldName.AUDIT_REPORT: [
        LabelSynonym.REPORT_NUMBER,
        LabelSynonym.REPORT_NO,
        LabelSynonym.INSPECTION_REPORT_NO,
    ],

    # ── Time fields ────────────────────────────────────────────────────────
    FieldName.FACTORY_IN_TIME: [
        LabelSynonym.FACTORY_IN_TIME,
        LabelSynonym.FACTORY_INTIME2,
        LabelSynonym.FACTORY_INTIME,
        LabelSynonym.IN_TIME,
    ],

    FieldName.FACTORY_OUT_TIME: [
        LabelSynonym.FACTORY_OUT_TIME,
        LabelSynonym.FACTORY_OUTTIME,
        LabelSynonym.FACTORY_OUTTIME2,
        LabelSynonym.OUT_TIME,
    ],

    FieldName.AUDIT_START_TIME: [
        LabelSynonym.AUDIT_START_TIME,
        LabelSynonym.START_TIME,
    ],

    FieldName.AUDIT_END_TIME: [
        LabelSynonym.AUDIT_END_TIME,
        LabelSynonym.END_TIME,
    ],

    # ── Audit outcome ──────────────────────────────────────────────────────
    FieldName.AUDIT_RESULT: [
        LabelSynonym.AUDIT_RESULT,
        LabelSynonym.RESULT,
        LabelSynonym.INSPECTION_RESULT,
    ],

    # ── Quantity fields ────────────────────────────────────────────────────

    # PO Qty: prefer integer value found below the label; fall back to right
    FieldName.PO_QTY: {
        "synonyms": [
            LabelSynonym.PO_QTY,
            LabelSynonym.PO_QUANTITY,
            LabelSynonym.PO_QTY_CAPS,
        ],
        "direction": [DirectionRule.DOWN_IF_INT, DirectionRule.RIGHT],
    },
    FieldName.DO_QTY: {
        "synonyms": [
            LabelSynonym.DO_QTY,
            LabelSynonym.DO_QUANTITY,
            LabelSynonym.DO_QTY_CAPS,
        ],
        "direction": [DirectionRule.DOWN_IF_INT, DirectionRule.RIGHT],
    },

    # --- Details OF Shipment ---
    # EXF: always to the right
    FieldName.EXF: {
        "synonyms": [
            LabelSynonym.EXF,
            LabelSynonym.EXF_,
            LabelSynonym.EXF__,
        ],
        "direction": DirectionRule.RIGHT,
    },

    # PO EDT: always to the right
    FieldName.PO_EDT: {
        "synonyms": [
            LabelSynonym.PO_EDT,
            LabelSynonym._PO_EDT,
            LabelSynonym.PO__EDT,
            LabelSynonym._PO__EDT,
        ],
        "direction": DirectionRule.RIGHT,
    },

    # PO W/H (warehouse / ship date): always to the right
    FieldName.PO_WH: {
        "synonyms": [
            LabelSynonym.PO_WH,
            LabelSynonym.WAREHOUSE,
            LabelSynonym.POWH,
            LabelSynonym.PO_WH_SLASH,
        ],
        "direction": DirectionRule.RIGHT,
    },

    # PLAN EDT: always to the right
    FieldName.PLAN_EDT: {
        "synonyms": [
            LabelSynonym.PLAN_ETD,
            LabelSynonym.PLAN__ETD,
        ],
        "direction": DirectionRule.RIGHT,
    },

    # PLAN WH: always to the right
    FieldName.PLAN_WH: {
        "synonyms": [
            LabelSynonym.PLAN_WH,
            LabelSynonym.PLAN__WH,
        ],
        "direction": DirectionRule.RIGHT,
    },

    FieldName.SHIP_QTY: [
        LabelSynonym.SHIP_QTY,
        LabelSynonym.SHIPMENT_QTY,
        LabelSynonym.SHIPPING_QUANTITY,
        LabelSynonym.SHIPPING_QTY,
        LabelSynonym.AUDIT_FOR_SHIPPING_QTY,
        LabelSynonym.EXF_QTY,
    ],

    FieldName.AUDIT_QTY: [
        LabelSynonym.AUDIT_QTY,
        LabelSynonym.AUDITED_QUANTITY,
        LabelSynonym.QTY_INSPECTED,
    ],

    # Defect qty from the "Major Defects" column header → value is to the right
    FieldName.DEFECT_QTY: {
        "synonyms": [
            LabelSynonym.MAJOR_DEFECTS,
        ],
        "direction": DirectionRule.RIGHT,
    },

    # ── Personnel ──────────────────────────────────────────────────────────
    FieldName.INSPECTOR: [
        LabelSynonym.INSPECTOR,
    ],


    FieldName.PERSON: [
        LabelSynonym.PERSON,
    ],

    FieldName.CARTON: [
        LabelSynonym.CARTON_INSPECTION,
        LabelSynonym.INSPECTION_CTN,
        LabelSynonym.INSPECTION_CARTON,
        LabelSynonym.OUR_INSPECTION_CARTON,
        LabelSynonym.OUR_INSPECTION_CARTON_NUMBER,
    ],

    FieldName.NEEDLE_DETECTOR: {
        "synonyms": [
            LabelSynonym.NEEDLE_DETECTOR,
            LabelSynonym.NEEDLE_DETECTOR_CHECK,
        ],
        "direction": DirectionRule.DOWN,
    },

    FieldName.REMARKS: {
        "synonyms": [
            LabelSynonym.REMARKS,
            LabelSynonym.REMARK,
        ],
        "direction": DirectionRule.DOWN,
    },
    FieldName.DO_SET_COL_SIZE: {
        "synonyms": [
            LabelSynonym.DO_SET_COL_SIZE,
        ],
        "direction": DirectionRule.DOWN,
    },

    FieldName.CLIENT: [
        LabelSynonym.CLIENT,
        LabelSynonym.CLIENT_NAME,
        LabelSynonym.BUYER,
        LabelSynonym.BUYER_NAME,
    ],
}

# ---------------------------------------------------------------------------
# Style number prefix → destination country
# Update here when new country codes are discovered.
# ---------------------------------------------------------------------------

STYLE_COUNTRY_MAP: dict = {
    StyleCountryPrefix.JAPAN:  "JAPAN",
    StyleCountryPrefix.CHINA:  "CHINA",
    StyleCountryPrefix.USA:    "USA",
    StyleCountryPrefix.KOREA:  "KOREA",
    StyleCountryPrefix.EUROPE: "EUROPE",
    StyleCountryPrefix.TAIWAN: "TAIWAN",
    StyleCountryPrefix.AU:     "AU",
    StyleCountryPrefix.CANADA: "CANADA",
    StyleCountryPrefix.INDIA:  "INDIA",
}


# ---------------------------------------------------------------------------
# Fields that must hold a pure integer after extraction
# (non-numeric text will be stripped by post_processor.clean_numeric_fields)
# ---------------------------------------------------------------------------

NUMERIC_FIELDS: set = {
    FieldName.PO_QTY,
    FieldName.DO_QTY,
    FieldName.SHIP_QTY,
    FieldName.AUDIT_QTY,
}


# ---------------------------------------------------------------------------
# Regex patterns used to infer the audit type from the file name
# ---------------------------------------------------------------------------

AUDIT_PATTERNS: dict = {
    AuditPattern.RE_FINAL: r"re[-\s]?final",
    AuditPattern.FINAL:    r"\bfinal\b",
    AuditPattern.INLINE:   r"inline",
    AuditPattern.SAMPLE:   r"sample",
    AuditPattern.CMF:      r"cmf",
}


# ---------------------------------------------------------------------------
# DO_TABLE_LABELS – column header → synonyms for the D.O. plan table
# ---------------------------------------------------------------------------
# This is the ONLY place you need to change when:
#   - A new Excel format spells a header differently
#     → add the new DOLabelSynonym value and list it here
#   - A new column is added to the D.O. table
#     → add DOFieldName + DOLabelSynonym entries, then add a row below
#
# The engine reads these exactly like LABELS above:
#   key   = DOFieldName  (internal name used in the output JSON)
#   value = list of DOLabelSynonym  (all known text variants for that header)
# ---------------------------------------------------------------------------

from ...models.field_enums import DOFieldName, DOLabelSynonym

DO_TABLE_LABELS: dict = {

    DOFieldName.DATE: [
        DOLabelSynonym.DATE,
    ],

    DOFieldName.PO_QTY: [
        DOLabelSynonym.PO_QTY,
        DOLabelSynonym.P_O_QTY,
        DOLabelSynonym.PO_QUANTITY,
        DOLabelSynonym.P_O_QUANTITY,
    ],

    DOFieldName.DO_NO: [
        DOLabelSynonym.DO_NO,
        DOLabelSynonym.D_O_NO,
        DOLabelSynonym.DO_NUMBER,
        DOLabelSynonym.D_O_NUMBER,
        DOLabelSynonym.DELIVERY_ORDER_NO,
    ],

    DOFieldName.DO_QTY: [
        DOLabelSynonym.DO_QTY,
        DOLabelSynonym.D_O_QTY,
        DOLabelSynonym.DO_QUANTITY,
        DOLabelSynonym.D_O_QUANTITY,
    ],

    DOFieldName.SHIP_QTY: [
        DOLabelSynonym.SHIP_QTY,
        DOLabelSynonym.SHIP_QUANTITY,
        DOLabelSynonym.SHIPMENT_QTY,
        DOLabelSynonym.SHIPMENT_QUANTITY,
    ],

    DOFieldName.AUDIT_QTY: [
        DOLabelSynonym.AUDIT_QTY,
        DOLabelSynonym.AUDIT_QUANTITY,
        DOLabelSynonym.AUDITED_QTY,
    ],

    DOFieldName.DO_BALANCE: [
        DOLabelSynonym.DO_BALANCE,
        DOLabelSynonym.D_O_BALANCE,
        DOLabelSynonym.DO_BALANCE_EXTRA,
        DOLabelSynonym.DO_BALANCE_AND_EXTRA,
        DOLabelSynonym.BALANCE_EXTRA,
    ],

    DOFieldName.PO_EXTRA: [
        DOLabelSynonym.PO_EXTRA,
        DOLabelSynonym.P_O_EXTRA,
    ],

    DOFieldName.REMARKS: [
        DOLabelSynonym.REMARKS,
        DOLabelSynonym.BALANCE_QTY_PLAN,
        DOLabelSynonym.BALANCE_QTY_PLAN_DATE,
        DOLabelSynonym.BALANCE_QTY_PLAN_DATE_REMARKS,
        DOLabelSynonym.PLAN_DATE_REMARKS,
    ],

    DOFieldName.PO_BALANCE: [
        DOLabelSynonym.PO_BALANCE,
        DOLabelSynonym.PO_BAL,
    ],
}

# Columns whose values should be carried forward across merged/empty rows.
# e.g. DATE and PO_QTY span multiple D.O. rows in the same Excel table.
DO_FILL_DOWN_FIELDS: set = {
    DOFieldName.DATE,
    DOFieldName.PO_QTY,
    DOFieldName.PO_EXTRA,
}
