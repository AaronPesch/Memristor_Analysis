"""The live channel: figure serialization, the Qt<->page bridge, the import worker.

Everything that replaces `write_html` + `QWebEngineView.load(file://)` lives here.
"""

from __future__ import annotations

import json
import traceback
from pathlib import Path

import plotly
from PySide6.QtCore import QFile, QIODevice, QObject, Signal, Slot

from app.converter.batch import BatchConverter
from app.converter.convert_path_to_glob import path_to_glob
from app.core.modes import Mode
from app.core.paths import DB_FILE
from app.core.theme import DARK, LIGHT, PLOT_COLORS
from app.plotting.config import Config

import live_pipeline

HERE = Path(__file__).parent
WEB_DIR = HERE / "web"


def export_static_assets() -> None:
    """plotly.js and qwebchannel.js come out of the installed packages.

    The app is therefore fully offline, and the plotly.js version always matches
    the plotly.py that built the figures -- a CDN pin cannot drift out of sync.
    """
    bundled = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
    if bundled.exists():
        (WEB_DIR / "plotly.min.js").write_bytes(bundled.read_bytes())
    resource = QFile(":/qtwebchannel/qwebchannel.js")
    if resource.open(QIODevice.OpenModeFlag.ReadOnly):
        (WEB_DIR / "qwebchannel.js").write_bytes(bytes(resource.readAll()))
        resource.close()


def figure_payload(fig, key: str, dark: bool, scale: str | None) -> dict:
    """Serialize a figure and apply the current view options.

    Applied to the JSON rather than the Figure, so the stored figure stays
    exactly as the builder produced it and the exporters are unaffected.
    """
    payload = json.loads(fig.to_json())
    layout = payload.setdefault("layout", {})

    # uirevision keyed per plot: re-pushing the same plot preserves the user's
    # zoom and pan; a scale change resets only the axis it applies to.
    layout["uirevision"] = key
    layout.pop("template", None)

    colors = PLOT_COLORS[DARK if dark else LIGHT]
    layout["paper_bgcolor"] = colors["paper_bgcolor"]
    layout["plot_bgcolor"] = colors["plot_bgcolor"]
    layout.setdefault("font", {})["color"] = colors["font_color"]
    for axis in ("xaxis", "yaxis"):
        cfg = layout.setdefault(axis, {})
        cfg["gridcolor"] = colors["grid_color"]
        cfg["zerolinecolor"] = colors["grid_color"]

    if scale in ("log", "linear"):
        yaxis = layout.setdefault("yaxis", {})
        yaxis["type"] = scale
        yaxis["autorange"] = True
        yaxis["uirevision"] = key + "-" + scale

    # The builders set pixel sizes meant for file export; on screen the pane decides.
    layout.pop("width", None)
    layout.pop("height", None)
    layout["autosize"] = True
    return payload


class Bridge(QObject):
    """The entire Python<->page interface: slots inbound, one signal outbound."""

    figureChanged = Signal(str)

    def __init__(self, window) -> None:
        super().__init__()
        self.window = window

    @Slot(result=str)
    def bootstrap(self) -> str:
        return json.dumps(self.window.current_payload())

    @Slot(str, result=str)
    def event(self, request_json: str) -> str:
        """A selection happened in the page. Update state, answer with a figure.

        This round trip is what a written-out HTML file cannot do.
        """
        request = json.loads(request_json)
        kind = request.get("kind")
        if kind == "select_devices":
            self.window.selection = set(request.get("devices") or [])
        elif kind == "toggle_device":
            self.window.selection ^= {request["device"]}
        elif kind == "clear_selection":
            self.window.selection = set()
        self.window.refresh_selection_ui()
        return json.dumps(self.window.current_payload())

    def push(self) -> None:
        self.figureChanged.emit(json.dumps(self.window.current_payload()))


class ImportWorker(QObject):
    """Import and figure build on a worker thread, so the UI stays responsive.

    The shipping worker also had to clear a temp folder full of generated HTML
    and fight Chromium's file locks for it. There are no files here, so that
    entire failure mode -- and its retry logic -- is gone.
    """

    progress = Signal(int)
    status = Signal(str)
    finished = Signal(object, object)  # LoadedData, list[Category]
    failed = Signal(str)

    def __init__(self, path: Path, mode: Mode) -> None:
        super().__init__()
        self.path = path
        self.mode = mode

    @Slot()
    def run(self) -> None:
        try:
            self.status.emit("Phase 1/2: importing Excel files into DuckDB...")
            self.progress.emit(5)
            BatchConverter(DB_FILE).convert(path_to_glob(self.path, self.mode))

            self.progress.emit(55)
            self.status.emit("Phase 2/2: building figures...")
            cfg = Config(db_file=DB_FILE, output_dir=HERE, mode=self.mode)
            data, categories = live_pipeline.load_and_build(cfg)

            self.progress.emit(100)
            self.finished.emit(data, categories)
        except Exception as exc:
            self.failed.emit(f"{exc}\n\n{traceback.format_exc()}")
