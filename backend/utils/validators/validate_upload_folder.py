from pathlib import Path


def validate_upload_folder(folder_path: str) -> Path:
    """Return a resolved Path or raise ValueError."""
    p = Path(folder_path).resolve()
    if not p.exists():
        raise ValueError(f"Folder does not exist: {folder_path}")
    if not p.is_dir():
        raise ValueError(f"Path is not a directory: {folder_path}")
    pdfs = list(p.glob("*.pdf"))
    if not pdfs:
        raise ValueError(f"No PDF files found in: {folder_path}")
    return p