import openpyxl

def _unique(ws, column_letter, min_row):
    """Return unique non-empty values from a column starting at min_row."""
    col_idx = openpyxl.utils.column_index_from_string(column_letter)
    seen = set()
    for (cell,) in ws.iter_rows(min_row=min_row, min_col=col_idx, max_col=col_idx):
        if cell.value is not None:
            seen.add(cell.value)
    return list(seen)