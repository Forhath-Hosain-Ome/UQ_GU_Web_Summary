# Factory code → full name mapping (originally the `enum` dict in the script)
FACTORY_ENUM = {
    "TBDYF": "VIYELLATEX LTD",
    "TBDEK": "EKL",
    "ABDPA": "ABDPA",
    "TBDSH": "DEWHIRST GROUP",
    "TBDSJ": "SQUARE FASHION LTD",
    "TBDSG": "SQUARE FASHION LTD",
    "TBDJK": "DBL GROUP",
    "TBDJJ": "DBL GROUP",
    "TBDAG": "ABL",
    "TBDFT": "FAKHRUDDIN TEXTILE MILLS LTD",
}

# Regex patterns (centralised so they're easy to update)
REGEX_INSPECTION_DATE = r"Inspection Date\s+(\d{2}\s\w{3}\s\d{4})"
REGEX_TOTAL_ROW = r"Total\s+.*"
REGEX_WORKMANSHIP = r"Workmanship\s+Pass\s+(\d+\s*/\s*\d+)\s+(\d+\s*/\s*\d+)"
REGEX_STYLE_LINE = r"1\.\s+(.+?)\s+(\d{6})\s+\d+"
REGEX_PO_NUMBER = r"\b460\d{7,}\b"
REGEX_FACTORY = (
    r"^Factory\s+([A-Z0-9&._()\- ]+?)"
    r"(?:\s{2,}|Sample Size|QC Stage|Inspection Date|$)"
)
REGEX_FINAL_CUSTOMER = r"Inspected\s+\d+\.\s+\d+\s+\d{2}\s\w{3}\s\d{4}\s+(\w+)"
REGEX_TRAILING_COUNTER = r"_\d+(?=\.pdf$)"

# Celery task states (extra granularity beyond PENDING/SUCCESS/FAILURE)
TASK_STATE_EXTRACTING = "EXTRACTING"
TASK_STATE_SAVING = "SAVING"
TASK_STATE_BUILDING_EXCEL = "BUILDING_EXCEL"
TASK_STATE_GENERATING_CERTS = "GENERATING_CERTS"
TASK_STATE_RENAMING = "RENAMING_PDFS"