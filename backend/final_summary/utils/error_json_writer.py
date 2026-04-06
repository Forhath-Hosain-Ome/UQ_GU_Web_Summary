"""
error_json_writer.py
--------------------
Writes audit records that failed BLOCKING validation to a JSON file so
the user can manually fix them and re-upload via the Extractor GUI.

File format
-----------
{
  "version": "1.0",
  "generated_at": "2026-01-05T10:30:00",
  "total_blocked": 3,
  "instructions": "Fix the fields listed in 'blocking_errors' for each record,
                   then upload this file via the Extractor's 'Upload Error JSON'
                   button.  Do NOT change the 'file_name' field.",
  "records": [
    {
      "file_name":       "DH26-01ABC-001.xlsx",
      "blocking_errors": ["REQUIRED_FIELD | factory | Factory name is missing"],
      "validation_errors": [...],
      -- all other AuditRecord fields --
      "defect_rows": [...],
      "do_orders":   [...]
    }
  ]
}

Re-import rules
---------------
- All fields in the JSON are editable EXCEPT 'file_name'.
- A record is only inserted if it passes blocking validation after the fix.
- Records that still fail after the upload remain in a new error JSON.
"""

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models.audit_record import AuditRecord


_VERSION = "1.0"

_INSTRUCTIONS = (
    "Fix the fields listed in 'blocking_errors' for each record, "
    "then upload this file via the Extractor → 'Upload & Fix Error JSON' button. "
    "Do NOT change the 'file_name' field. "
    "Records that still fail after upload will produce a new error file."
)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def write_error_json(records: List[AuditRecord], path: Path) -> int:
    """
    Write *records* (all of which should have blocking_errors) to *path*.
    Returns the number of records written.
    """
    if not records:
        logging.info("write_error_json: no blocked records — file not written")
        return 0

    def _serialise(r: AuditRecord) -> Dict[str, Any]:
        d = asdict(r)
        # Put blocking/validation errors at the top for visibility
        return {
            "file_name":         d.pop("file_name", r.file_name),
            "blocking_errors":   d.pop("blocking_errors", []),
            "validation_errors": d.pop("validation_errors", []),
            **d,
        }

    payload = {
        "version":       _VERSION,
        "generated_at":  datetime.now().isoformat(timespec="seconds"),
        "total_blocked": len(records),
        "instructions":  _INSTRUCTIONS,
        "records":       [_serialise(r) for r in records],
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logging.info(f"Error JSON written: {path}  ({len(records)} blocked record(s))")
    return len(records)


# ---------------------------------------------------------------------------
# Read (re-import after user edits)
# ---------------------------------------------------------------------------

def read_error_json(path: Path) -> List[AuditRecord]:
    """
    Load a previously written error JSON file and return a list of
    AuditRecord objects with the user's fixes applied.

    Fields that don't map to AuditRecord attributes are silently ignored.
    """
    if not path.exists():
        raise FileNotFoundError(f"Error JSON not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))

    # Support both wrapped {records: [...]} and bare list
    if isinstance(raw, list):
        items = raw
    else:
        items = raw.get("records", [])

    records: List[AuditRecord] = []
    import dataclasses

    valid_fields = {f.name for f in dataclasses.fields(AuditRecord)}

    for item in items:
        if not isinstance(item, dict):
            continue
        # Only keep keys that are valid AuditRecord fields
        kwargs = {k: v for k, v in item.items() if k in valid_fields}
        try:
            record = AuditRecord(**kwargs)
            # Clear blocking/validation errors — they will be re-evaluated
            record.blocking_errors    = []
            record.validation_errors  = []
            records.append(record)
        except Exception as exc:
            fname = item.get("file_name", "?")
            logging.warning(f"  Could not load record '{fname}' from error JSON: {exc}")

    logging.info(f"read_error_json: loaded {len(records)} record(s) from {path}")
    return records
