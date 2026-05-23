
from final_summary.extraction.core import CellGrid

# ------------------------------------------------------------------
# Override: defects — INLINE time
# ------------------------------------------------------------------
def extract_inline_times_overwrite(self, grid: CellGrid) -> dict:
    """
    Parse times from a single merged cell containing text like:

        02. Working Time of Audit:  12: 00 PM  TO  03: 30 PM
        # In Time 10: 00 AM   &  Out Time 00: 00 PM

    audit_start / audit_end  → first line  (before / after TO)
    factory_in  / factory_out → second line (In Time ... & Out Time ...)
    """
    import re
    from final_summary.extraction.core import to_hhmm, duration_hhmm

    # Patterns — tolerant of spaces inside times like "12 : 00 PM"
    _TIME_PAT = r"\d{1,2}\s*:\s*\d{2}\s*(?:AM|PM)"

    # Label synonyms to locate the merged cell
    INLINE_TIME_SYNONYMS = [
        "working time of audit",
        "working time",
        "audit working time",
        "02. working time",
    ]

    raw_block = ""
    for row, col, _ in grid.find_label_positions(INLINE_TIME_SYNONYMS):
        # The value may be in the same cell or the next cell to the right
        cell_text = grid.get(row, col) or ""
        right_text = grid.get(row, col + 1) or ""
        combined = f"{cell_text} {right_text}".strip()
        if combined:
            raw_block = combined
            break

    if not raw_block:
        # Fallback: scan all cells for the pattern
        for row in range(grid.nrows):
            for col in range(grid.ncols):
                cell = grid.get(row, col) or ""
                if "working time" in cell.lower() or "in time" in cell.lower():
                    raw_block = cell
                    break
            if raw_block:
                break

    if not raw_block:
        return {
            "factory_in_time":     "",
            "factory_out_time":    "",
            "factory_total_hours": "",
            "audit_start_time":    "",
            "audit_end_time":      "",
            "audit_total_hours":   "",
        }

    # Normalise spaces inside times: "12 : 00 PM" → "12:00 PM"
    raw_block = re.sub(r"(\d)\s*:\s*(\d)", r"\1:\2", raw_block)

    # Split into lines — first line = audit times, second = factory times
    lines = [l.strip() for l in raw_block.replace("#", "\n").splitlines() if l.strip()]

    audit_start = audit_end = factory_in = factory_out = ""

    for line in lines:
        times = re.findall(_TIME_PAT, line, re.IGNORECASE)

        if re.search(r"\bTO\b", line, re.IGNORECASE) and len(times) >= 2:
            # "12:00 PM TO 03:30 PM" → audit start / end
            audit_start = to_hhmm(times[0])
            audit_end   = to_hhmm(times[1])

        elif re.search(r"in time", line, re.IGNORECASE) and len(times) >= 1:
            # "In Time 10:00 AM & Out Time 05:00 PM"
            factory_in = to_hhmm(times[0])
            if re.search(r"out time", line, re.IGNORECASE) and len(times) >= 2:
                factory_out = to_hhmm(times[1])

    return {
        "factory_in_time":     factory_in,
        "factory_out_time":    factory_out,
        "factory_total_hours": duration_hhmm(factory_in, factory_out),
        "audit_start_time":    audit_start,
        "audit_end_time":      audit_end,
        "audit_total_hours":   duration_hhmm(audit_start, audit_end),
    }
# TODO: add INLINE-specific field corrections here
