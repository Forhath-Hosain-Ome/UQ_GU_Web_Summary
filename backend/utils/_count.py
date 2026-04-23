import openpyxl

def _count(ws, column_letter, min_row):
    """Count non-empty cells in a column from min_row downward."""
    col_idx = openpyxl.utils.column_index_from_string(column_letter)
    total = 0
    for (cell,) in ws.iter_rows(min_row=min_row, min_col=col_idx, max_col=col_idx):
        if cell.value is not None:
            total += 1
    return total