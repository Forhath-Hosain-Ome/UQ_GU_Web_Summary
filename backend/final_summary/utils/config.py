"""
config.py
---------
Central application configuration.

DB_PATH is the single fixed location of the SQLite database.
It is created once on first run and reused on every subsequent run,
enabling duplicate detection across all extraction sessions.

When packaged with PyInstaller the exe sits next to the repository root
and the DB lives next to it at backend/audit.db.
"""

from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = WORKSPACE_ROOT / "backend"
APP_DIR = BACKEND_DIR
DB_PATH = APP_DIR / "audit.db"


def ensure_app_dir() -> None:
    """
    Create the backend directory if it does not exist.
    Called once at startup by both scripts.
    Raises PermissionError if the directory cannot be created.
    """
    APP_DIR.mkdir(parents=True, exist_ok=True)