import logging
from pathlib import Path

from ..helpers.core.cell_grid import CellGrid
from ..helpers.core.sheet_reader import read_sheet
from ..helpers.extraction.defect_extractor import extract_defect_table_from_file
from ..helpers.extraction.do_table_extractor import extract_do_table_to_record
from ..helpers.extraction.label_config import LABELS
from ..helpers.extraction.post_processor import post_process_record, refine_record
from ..helpers.extraction.rule_extractor import extract_fields
from ..models.audit_record import AuditRecord

logger = logging.getLogger(__name__)


def extract_record(path: Path, sheet_name: str = None) -> AuditRecord:
    """
    Extract and normalise one audit record from an Excel file.

    Parameters
    ----------
    path : Path
        Path to the Excel file.
    sheet_name : str, optional
        Name of the sheet to process. If None or not found, the first sheet is used.
    """
    # Read the specified sheet (or the first sheet if None)
    df = read_sheet(path, sheet_name=sheet_name)
    grid = CellGrid(df)
    extracted_data = extract_fields(grid, LABELS)

    known = set(AuditRecord.__dataclass_fields__.keys())  # type: ignore[attr-defined]
    safe_data = {k: v for k, v in extracted_data.items() if k in known and k != "file_name"}
    record = AuditRecord(file_name=path.name, **safe_data)

    # Extract defect table from the same sheet (or fallback to first sheet)
    defect_rows, defect_totals = extract_defect_table_from_file(path, sheet_name=sheet_name)
    record.defect_rows = defect_rows
    if not record.defect_qty and defect_totals.get("major") is not None:
        record.defect_qty = str(defect_totals["major"])

    record = post_process_record(record, path)
    extract_do_table_to_record(record, path)  # scans all sheets for DO table
    record = refine_record(record)

    logger.info(
        "Processed Excel file %s | sheet=%s | type=%s | client=%s",
        path.name,
        sheet_name if sheet_name else "first",
        record.inspection_type,
        record.client,
    )
    return record
