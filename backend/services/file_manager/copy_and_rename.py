import logging
from pathlib import Path
from .build_renamed_pdf_name import build_renamed_pdf_name
from shared.exceptions import FileProcessingError

logger = logging.getLogger(__name__)


def copy_and_rename(source_path: Path, record: dict, output_dir: Path) -> Path:
    """
    Rename a PDF in-place within its folder using the standardised name.

    - The new file is written to output_dir (which may be the same as
      source_path.parent when renaming in-place).
    - The original file is deleted after the rename succeeds.
    - Collision handling: if the target name already exists AND it is a
      different file from the source, a numeric suffix is appended.

    Returns the final destination path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    new_name = build_renamed_pdf_name(record)
    dest = output_dir / new_name

    # If source and destination are already the same path, nothing to do.
    if source_path.resolve() == dest.resolve():
        logger.info("Already correctly named, skipping: %s", source_path.name)
        return dest

    # Handle collisions with files that are NOT the source itself
    counter = 1
    base = dest
    while dest.exists() and dest.resolve() != source_path.resolve():
        dest = output_dir / f"{base.stem}_{counter}{base.suffix}"
        counter += 1

    try:
        # Read source, write to destination, then delete source.
        # Using read/write (not shutil.move) so that we handle cross-device
        # renames gracefully and always clean up the original.
        dest.write_bytes(source_path.read_bytes())
        source_path.unlink()
        logger.info("Renamed %s → %s", source_path.name, dest.name)
        return dest
    except Exception as exc:
        # Clean up partial write if dest was partially written
        if dest.exists() and dest.resolve() != source_path.resolve():
            try:
                dest.unlink()
            except Exception:
                pass
        raise FileProcessingError(
            f"Failed to rename {source_path.name}: {exc}"
        ) from exc