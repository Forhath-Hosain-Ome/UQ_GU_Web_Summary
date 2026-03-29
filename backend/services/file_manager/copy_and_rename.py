import logging
import shutil
from pathlib import Path
from .build_renamed_pdf_name import build_renamed_pdf_name
from shared.exceptions import FileProcessingError

logger = logging.getLogger(__name__)

def copy_and_rename(
    source_path: Path, record: dict, output_dir: Path
) -> Path:
    """
    Copy a source PDF to output_dir with the standardised name.
    Returns the final destination path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    new_name = build_renamed_pdf_name(record)
    dest = output_dir / new_name

    # Handle collisions
    counter = 1
    base = dest
    while dest.exists():
        dest = output_dir / f"{base.stem}_{counter}{base.suffix}"
        counter += 1

    try:
        shutil.copy2(source_path, dest)
        logger.info("Copied %s → %s", source_path.name, dest.name)
        return dest
    except Exception as exc:
        raise FileProcessingError(
            f"Failed to copy {source_path.name}: {exc}"
        ) from exc