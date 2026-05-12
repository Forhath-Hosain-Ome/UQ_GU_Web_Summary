"""
rule_extractor.py
-----------------
Drives the label-based extraction loop over a CellGrid.

For every field defined in the LABELS config it:
  1. Searches the grid for matching label cell(s).
  2. Tries to read the value inline (same cell, e.g. "Label: Value").
  3. Falls back to proximity search (adjacent cells).
  4. Uses dedicated handlers for special fields (po_wh, po_no, report_no, etc.).

BUG FIXED: Label position reuse across fields
----------------------------------------------
Previously, if two fields shared a synonym (e.g. "report no" matching both
po_no and report_no), the same cell position could be returned for both,
causing the first extracted value to be assigned to both fields.

Fix: a global `used_positions` set tracks every (row, col) already consumed.
Each field only uses positions not yet taken.
"""

import logging
import re
from typing import Any, Dict, Set, Tuple

from ..core.cell_grid import CellGrid
from .proximity import (
    find_inline_value,
    resolve_value,
    normalize_text,
    resolve_po_wh_value,
    resolve_po_or_report_number,
)


# Lenient regex for report numbers to avoid rejecting valid but non-standard IDs
LENIENT_REPORT_NO_RE = re.compile(r"[A-Z0-9]{2,}[-\s/]?\d+", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve(
    grid: CellGrid,
    label_pos: Tuple[int, int],
    direction_rule: Any,
    field_name: str,
) -> str:
    """
    Route value resolution to the correct handler for the given field.
    Wraps exceptions so one bad cell never aborts the whole file.
    """
    try:
        if field_name in ("po_wh", "exf", "po_edt", "plan_edt", "plan_wh"):
            return resolve_po_wh_value(grid, label_pos)

        if field_name in ("po_no", "report_no"):
            return resolve_po_or_report_number(grid, label_pos, field_name)

        return resolve_value(grid, label_pos, direction_rule)

    except Exception as exc:
        logging.warning(
            f"resolve error – field='{field_name}' pos={label_pos}: {exc}"
        )
        return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_fields(
    grid: CellGrid,
    label_config: Dict[str, Any],
) -> Dict[str, str]:
    """
    Extract all fields specified in *label_config* from *grid*.

    Parameters
    ----------
    grid         : CellGrid for the sheet being processed
    label_config : mapping of  field_name → synonyms  OR
                              field_name → {"synonyms": [...], "direction": ...}

    Returns
    -------
    Dict mapping each field name to the extracted string value (or "").
    """
    extracted: Dict[str, str] = {}

    # Track which label positions have already been consumed by a field.
    # This prevents two fields from reading the same cell as their label.
    used_positions: Set[Tuple[int, int]] = set()

    for field_name, label_info in label_config.items():

        # ── Parse the config entry ────────────────────────────────────────────
        if isinstance(label_info, dict):
            synonyms       = label_info.get("synonyms", [])
            direction_rule = label_info.get("direction", "right_then_down")
        else:
            synonyms       = label_info
            direction_rule = "right_then_down"

        # ── Find where this label appears in the grid ─────────────────────────
        all_positions = grid.find_label_positions(synonyms)

        # Filter out positions already consumed by a previous field
        available_positions = [
            pos for pos in all_positions
            if (pos[0], pos[1]) not in used_positions
        ]

        if not available_positions:
            logging.debug(
                f"No available label for field '{field_name}' "
                f"(synonyms: {synonyms}, already-used: {len(all_positions) - len(available_positions)})"
            )
            extracted[field_name] = ""
            continue

        # ── Try each available position until a non-empty value is found ──────
        value = ""

        for label_row, label_col, label_text in available_positions:

            # ── Label Collision Mitigation ────────────────────────────────────
            # Prevent 'audit_qty' from stealing labels meant for 'ship_qty'
            # (e.g., "Audit For Shipping Qty" starts with "Audit Qty")
            norm_found = normalize_text(label_text)
            if field_name == "audit_qty" and "shipping" in norm_found:
                continue

            # Special-case fields that bypass inline extraction entirely
            if field_name == "needle_detector":
                # Use only the configured direction; do NOT check inline
                # to avoid matching patterns like "(Level-08)" in the label.
                value = _resolve(grid, (label_row, label_col), direction_rule, field_name)

            elif field_name in ("report_no", "po_no"):
                # 1) Try Inline first: "Report No: JP..." packed into one cell.
                # This is more robust than jumping straight to the proximity scanner.
                cell_text = grid.get(label_row, label_col)
                for syn in synonyms:
                    syn_text = syn.value if hasattr(syn, "value") else str(syn)
                    candidate = find_inline_value(syn_text, cell_text)
                    if candidate:
                        # Verify the inline value actually matches a valid pattern
                        # so we don't 'steal' a label for the wrong field.
                        from .proximity import is_valid_po_no, is_valid_report_no
                        is_report = field_name == "report_no" and (is_valid_report_no(candidate) or LENIENT_REPORT_NO_RE.search(candidate))
                        is_po     = field_name == "po_no" and is_valid_po_no(candidate)
                        
                        if is_report or is_po:
                            value = candidate
                            break
                if not value:
                    value = resolve_po_or_report_number(grid, (label_row, label_col), field_name)

            elif field_name == "po_wh":
                value = resolve_po_wh_value(grid, (label_row, label_col))

            elif field_name == "exf":
                value = resolve_po_wh_value(grid, (label_row, label_col))

            else:
                # 1) Inline: "LABEL: value" packed into the same cell?
                cell_text = grid.get(label_row, label_col)
                for syn in synonyms:
                    syn_text = syn.value if hasattr(syn, "value") else str(syn)
                    value = find_inline_value(syn_text, cell_text)
                    if value:
                        break

                # 2) Proximity: look in adjacent cells
                if not value:
                    value = _resolve(
                        grid, (label_row, label_col), direction_rule, field_name
                    )

            if value:
                # Mark this position as consumed so other fields won't reuse it
                used_positions.add((label_row, label_col))
                break

        extracted[field_name] = value

    return extracted
