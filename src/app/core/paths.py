import os
import sys
from pathlib import Path


def get_app_data_dir() -> Path:
    """Detect OS and return a writable folder in AppData."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".local" / "share"

    data_dir = base / "MemristorAnalysisTool"
    return data_dir


# Global Constants
APP_DATA_PATH = get_app_data_dir()
DB_FILE = APP_DATA_PATH / "output.duckdb"
TEMP_DIR = APP_DATA_PATH / "temp"
PREFS_FILE = APP_DATA_PATH / "preferences.json"

# INITIALIZATION: Re-create folders every time the app starts
APP_DATA_PATH.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)
