"""
--------------------
Serialises blocked AuditRecord objects to a structured JSON payload and
deserialises user-fixed JSON back into AuditRecord objects for the retry flow.

JSON shape
----------
{
  "version":       "2.0",
  "batch_id":      42,
  "generated_at":  "2026-01-05T10:30:00",
  "total_blocked": 3,
  "instructions":  "...",
  "records": [
    {
      "file_name":         "DH26-01ABC-001.xlsx (Final)",
      "blocking_errors":   ["REQUIRED_FIELD | factory | ..."],
      "validation_errors": [...],
      "cross_check_warnings": [...],
      <all other AuditRecord fields>
    }
  ]
}

Round-trip guarantee
--------------------
write_error_json() → user edits JSON → read_error_json() → validate_blocking()
Records that still fail after re-upload appear in a new error JSON.
"""

import dataclasses
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from final_summary.extraction.formats.base import AuditRecord

_VERSION = "2.0"

_INSTRUCTIONS = (
    "Fix the fields listed in 'blocking_errors' for each record. "
    "Then POST this JSON (with batch_id) to /api/final-summary/retry/. "
    "Do NOT change 'file_name' — it is the unique identifier. "
    "Records that still fail after retry will appear in a new error file."
)

_VALID_FIELDS = {f.name for f in dataclasses.fields(AuditRecord)}


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def build_error_payload(
    records: List[AuditRecord],
    batch_id: int,
) -> Dict[str, Any]:
    """
    Build the error JSON payload dict from a list of blocked AuditRecords.
    Returns the dict (caller decides whether to write to file or return as API response).
    """

    def _serialise(r: AuditRecord) -> Dict[str, Any]:
        d = dataclasses.asdict(r)
        # Surface error lists at the top for visibility
        return {
            "file_name":            d.pop("file_name", r.file_name),
            "blocking_errors":      d.pop("blocking_errors", []),
            "validation_errors":    d.pop("validation_errors", []),
            "cross_check_warnings": d.pop("cross_check_warnings", []),
            **d,
        }

    return {
        "version":       _VERSION,
        "batch_id":      batch_id,
        "generated_at":  datetime.now().isoformat(timespec="seconds"),
        "total_blocked": len(records),
        "instructions":  _INSTRUCTIONS,
        "records":       [_serialise(r) for r in records],
    }


def write_error_json(
    records: List[AuditRecord],
    batch_id: int,
    path: Path,
) -> int:
    """
    Write blocked records to *path* as formatted JSON.
    Returns the number of records written.
    """
    if not records:
        logging.info("write_error_json: no blocked records — file not written")
        return 0

    payload = build_error_payload(records, batch_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    logging.info(
        "Error JSON written: %s  (%d blocked record(s))", path, len(records)
    )
    return len(records)


# ---------------------------------------------------------------------------
# Read (re-import after user edits)
# ---------------------------------------------------------------------------

def read_error_json(path: Optional[Path] = None, raw: Optional[str] = None) -> List[AuditRecord]:
    """
    Load a previously written error JSON file (or raw JSON string) and return
    a list of AuditRecord objects with the user's fixes applied.

    Accepts either a file path or a raw JSON string (for API upload).
    Fields not on AuditRecord are silently ignored.

    Parameters
    ----------
    path : Path to the JSON file, or None
    raw  : JSON string, or None

    Returns
    -------
    List of AuditRecord objects with blocking/validation errors cleared.
    """
    if path is not None:
        if not path.exists():
            raise FileNotFoundError(f"Error JSON not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
    elif raw is not None:
        data = json.loads(raw)
    else:
        raise ValueError("Provide either path or raw JSON string.")

    # Support both wrapped {records: [...]} and bare list
    if isinstance(data, list):
        items = data
    else:
        items = data.get("records", [])

    records: List[AuditRecord] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        kwargs = {k: v for k, v in item.items() if k in _VALID_FIELDS}
        try:
            record = AuditRecord(**kwargs)
            # Clear old errors — they will be re-evaluated by the retry pipeline
            record.blocking_errors    = []
            record.validation_errors  = []
            records.append(record)
        except Exception as exc:
            fname = item.get("file_name", "?")
            logging.warning(
                "read_error_json: could not load record '%s': %s", fname, exc
            )

    logging.info(
        "read_error_json: loaded %d record(s) from %s",
        len(records), path or "raw string",
    )
    return records