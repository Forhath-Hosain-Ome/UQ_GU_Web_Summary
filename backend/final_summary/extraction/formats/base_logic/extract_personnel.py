from pathlib import Path
from final_summary.extraction.core import CellGrid

# ------------------------------------------------------------------
# Override: personnel — Based on Type
# ------------------------------------------------------------------

def extract_personnel_overwrite(self, grid: CellGrid, path: Path) -> dict:
    from final_summary.extraction.fields import extract_personnel
    pers = extract_personnel(grid, path)

    if self._is_inline(sheet_name=str(path)):
        pers["carton"]          = ""
        pers["needle_detector"] = ""
    return pers
