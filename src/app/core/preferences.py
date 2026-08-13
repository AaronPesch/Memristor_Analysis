from __future__ import annotations
import json
from pathlib import Path
from .paths import PREFS_FILE


def _load() -> dict:
    if PREFS_FILE.exists():
        try:
            return json.loads(PREFS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"scales": {}}


def _save(prefs: dict) -> None:
    PREFS_FILE.write_text(json.dumps(prefs, indent=2), encoding="utf-8")


def _key(html_path: str) -> str:
    p = Path(html_path)
    return f"{p.parent.name}/{p.stem}"


def get_scale(html_path: str) -> str | None:
    return _load()["scales"].get(_key(html_path))


def set_scale(html_path: str, scale: str) -> None:
    prefs = _load()
    prefs["scales"][_key(html_path)] = scale
    _save(prefs)
