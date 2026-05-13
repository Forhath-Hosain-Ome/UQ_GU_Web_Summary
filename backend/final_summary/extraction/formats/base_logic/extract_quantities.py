from pathlib import Path
from final_summary.extraction.core import CellGrid
# ------------------------------------------------------------------
# Override: quantities — INLINE has different ship_qty logic
# ------------------------------------------------------------------
def extract_quantities_overwrite(
    self, grid: CellGrid, path: Path, format_type: str = ""
) -> dict:
    from final_summary.extraction.fields import extract_quantities
    qtys = extract_quantities(grid, path, format_type)

    if self._is_inline(sheet_name=str(path)):
        qtys["po_qty_pcs"] = 0
        qtys["ship_qty"]   = ""
    return qtys