from pathlib import Path


def is_valid_folder(folder_path: str) -> bool:
    """Return True if folder exists and contains at least one File."""
    p = Path(folder_path)
    return p.is_dir() and (any(p.glob("*.pdf")) or any(p.glob("*.xls")) or any(p.glob("*.xlxs")))