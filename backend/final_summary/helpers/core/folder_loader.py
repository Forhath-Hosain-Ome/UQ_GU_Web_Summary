"""
folder_loader.py
----------------
Recursively discovers Excel files starting from a root directory.

Strategy
--------
- Walk the directory tree recursively.
- At each level, if Excel files (.xlsx / .xls) are found, yield them.
- Skips temporary Office lock files (those beginning with "~$").
- Skips the "Summary" output folder to avoid re-processing outputs.

This handles any nesting depth:
  Mother / file.xlsx                         (flat)
  Mother / Month / file.xlsx                 (one level)
  Mother / Month / Date / file.xlsx          (two levels)
  Mother / Factory / Month / Date / file.xlsx (three levels)
"""

from pathlib import Path
from typing import Iterator


# Folder names to always skip during traversal
_SKIP_DIRS = {"summary", "Summary", "__pycache__", ".git"}


def find_xlsx_files(root: Path) -> Iterator[Path]:
    """
    Recursively yield all .xlsx and .xls files under *root*.

    Files are yielded in sorted order per directory for reproducibility.
    Temporary Office lock files (~$...) are silently skipped.
    The "Summary" output folder is excluded from traversal.
    """
    if not root.is_dir():
        return

    for item in sorted(root.iterdir()):
        if item.is_dir():
            if item.name in _SKIP_DIRS:
                continue
            yield from find_xlsx_files(item)

        elif item.is_file():
            if item.name.startswith("~$"):
                continue
            if item.suffix.lower() in (".xlsx", ".xls"):
                yield item


def find_xlsx_files_with_stats(root: Path) -> dict:
    """
    Scan *root* recursively and return a summary dict:
        {
            "files": [Path, ...],
            "total": int,
            "by_folder": {str: [Path, ...]}  # relative folder → files
        }
    """
    files = list(find_xlsx_files(root))
    by_folder: dict = {}

    for f in files:
        rel = str(f.parent.relative_to(root))
        by_folder.setdefault(rel, []).append(f)

    return {
        "files": files,
        "total": len(files),
        "by_folder": by_folder,
    }
