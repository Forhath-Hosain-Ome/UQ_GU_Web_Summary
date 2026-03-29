import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

def clean_output_directory(output_dir: Path) -> None:
    """Remove all files and subdirectories inside output_dir (cache reset)."""
    if not output_dir.exists():
        return
    for item in output_dir.iterdir():
        if item.is_file():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)
    logger.info("Cleaned output directory: %s", output_dir)