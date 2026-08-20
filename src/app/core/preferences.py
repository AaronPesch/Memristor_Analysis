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
    return _load().get("scales", {}).get(_key(html_path))


def set_scale(html_path: str, scale: str) -> None:
    prefs = _load()
    prefs.setdefault("scales", {})[_key(html_path)] = scale
    _save(prefs)


# ── Theme ────────────────────────────────────────────────────────────────
def get_theme() -> str:
    return _load().get("theme", "light")


def set_theme(theme: str) -> None:
    prefs = _load()
    prefs["theme"] = theme
    _save(prefs)


# ── Window geometry ──────────────────────────────────────────────────────
def get_window() -> dict | None:
    return _load().get("window")


def set_window(x: int, y: int, width: int, height: int) -> None:
    prefs = _load()
    prefs["window"] = {"x": x, "y": y, "width": width, "height": height}
    _save(prefs)


# ── Session (last mode + tab) ────────────────────────────────────────────
def get_session() -> dict | None:
    return _load().get("session")


def set_session(mode: str | None, tab_index: int, sub_tab_index: int = 0) -> None:
    prefs = _load()
    prefs["session"] = {
        "mode": mode,
        "tab_index": tab_index,
        "sub_tab_index": sub_tab_index,
    }
    _save(prefs)
