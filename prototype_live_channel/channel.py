"""The live channel: figure serialization, the Qt<->page bridge, the import worker.

Everything that replaces `write_html` + `QWebEngineView.load(file://)` lives here.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import sys
import traceback
from pathlib import Path

import plotly
from PySide6.QtCore import QFile, QIODevice, QObject, Signal, Slot

from app.converter.batch import BatchConverter
from app.converter.convert_path_to_glob import path_to_glob
from app.core.modes import Mode
from app.core.paths import APP_DATA_PATH, DB_FILE
from app.core.theme import DARK, LIGHT, PLOT_COLORS
from app.plotting.config import Config

import dashboard_data
import live_pipeline

HERE = Path(__file__).parent
PAGE_FILES = ("analysis.html", "analysis.js")


def bundle_web() -> Path:
    """Where PyInstaller put the page files, or the source folder."""
    return Path(getattr(sys, "_MEIPASS", HERE)) / "web"


def web_root() -> Path:
    """The directory the page is actually served from.

    Running from a checkout this is the source folder, so an edit to the page
    takes effect on the next start. Frozen, the bundle is the wrong place to
    write into -- plotly.js and qwebchannel.js have to land somewhere -- so the
    page is assembled in the app-data folder instead.
    """
    if getattr(sys, "frozen", False):
        return APP_DATA_PATH / "web"
    return HERE / "web"


# Kept as a module attribute for callers that read it directly.
WEB_DIR = web_root()


def export_static_assets() -> None:
    """Assemble the page: plotly.js and qwebchannel.js out of the installed
    packages, plus the page files themselves when running frozen.

    The app is therefore fully offline, and the plotly.js version always matches
    the plotly.py that built the figures -- a CDN pin cannot drift out of sync.
    """
    target = web_root()
    target.mkdir(parents=True, exist_ok=True)

    if getattr(sys, "frozen", False):
        for name in PAGE_FILES:
            source = bundle_web() / name
            if source.exists():
                (target / name).write_bytes(source.read_bytes())

    bundled = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
    if bundled.exists():
        (target / "plotly.min.js").write_bytes(bundled.read_bytes())
    resource = QFile(":/qtwebchannel/qwebchannel.js")
    if resource.open(QIODevice.OpenModeFlag.ReadOnly):
        (target / "qwebchannel.js").write_bytes(bytes(resource.readAll()))
        resource.close()


def view_colors(dark: bool) -> dict:
    """The palette the page itself is painted with.

    The figures carry their own colors, but the area around them -- and the
    placeholder shown before any import -- is the page's own background. Without
    this it stays Chromium white inside a dark window.
    """
    return PLOT_COLORS[DARK if dark else LIGHT]


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
            devices = self.window.resolve_devices(request.get("points") or [])
            if devices:
                self.window.selection = set(devices)
        elif kind == "toggle_device":
            device = self.window.resolve_device(request.get("point") or {})
            if device:
                self.window.selection ^= {device}
        elif kind == "clear_selection":
            self.window.selection = set()
        elif kind == "overview_metric":
            self.window.set_overview_metric(request.get("metric"))
        elif kind == "goto":
            # Overview acts as a hub: jump straight to the matching plot tab.
            self.window.goto_category(request.get("category"))
        elif kind == "drill":
            # Aggregate point -> the raw sweep behind it.
            device = self.window.resolve_device(request.get("point") or {})
            cycle = request.get("cycle")
            if device:
                self.window.drill_to(device, int(cycle) if cycle is not None else None)

        self.window.refresh_selection_ui()
        return json.dumps(self.window.current_payload())

    def push(self) -> None:
        self.figureChanged.emit(json.dumps(self.window.current_payload()))


_UNOPENABLE = re.compile(r"Could not open workbook at (.+)$", re.MULTILINE)
_OUTCOME = re.compile(
    r"^\[\d+/\d+\]\s+(?P<name>.+?):\s+(?P<outcome>.+?)(?:\s+\([\d.]+s\))?$"
)


def diagnose_import(log: str) -> str:
    """Turn the converter's per-file output into something actionable.

    `BatchConverter` prints one line per file -- so many rows, `metadata only`,
    or `ERROR`. Which of the two usual causes of an empty database applies is
    visible only there, so the distinction has to reach the user.
    """
    # A file that cannot be opened is not reported as an error on its own line.
    # ExcelFileProcessor catches the exception, so the converter sees zero rows
    # and prints "metadata only"; the real cause only appears in the warnings
    # block at the end. Without reading that, an unreadable file is
    # indistinguishable from a spreadsheet that simply has no Run sheets -- and
    # the advice for the two is opposite.
    unreadable = {
        Path(match.group(1).strip()).name for match in _UNOPENABLE.finditer(log)
    }

    rows = metadata = 0
    failures: list[str] = []
    for line in log.splitlines():
        match = _OUTCOME.match(line.strip())
        if not match:
            continue
        name, outcome = match.group("name"), match.group("outcome")
        if name in unreadable or outcome.startswith("ERROR"):
            failures.append(
                f"{name}: {'could not be opened' if name in unreadable else outcome}"
            )
        elif "metadata only" in outcome:
            metadata += 1
        else:
            rows += 1
    errors = len(failures)

    total = rows + metadata + errors
    if total == 0:
        return ""

    lines = [
        f"{total} file(s) read: {rows} with cycle data, "
        f"{metadata} metadata only, {errors} unreadable."
    ]
    if rows == 0 and metadata:
        lines.append(
            "No file contained sheets named Run1, Run2, ... Those hold the cycle "
            "data; everything else becomes a metadata table. This usually means "
            "the selected folder is not the one holding the measurements - for a "
            "device import, pick the folder with the .xlsx files in it."
        )
    if errors:
        lines.append(
            "Files that could not be read at all are often present but not "
            "actually downloaded - OneDrive and similar keep placeholders that "
            "look like normal files. Right-click the folder and choose "
            "'Always keep on this device', then import again."
        )
        lines.extend("  " + failure for failure in failures[:5])
        if len(failures) > 5:
            lines.append(f"  ... and {len(failures) - 5} more")
    return "\n".join(lines)


def diagnose_selection(path: Path, mode: Mode) -> str:
    """Explain a folder that yielded no files at all.

    `BatchConverter` reports the glob it tried and nothing else, so a folder
    holding the device folders one level down looks the same as a folder holding
    a holiday calendar. What is actually in there is the useful part.
    """
    if not path.exists():
        return f"{path} does not exist any more."
    if not path.is_dir():
        return f"{path} is a file, not a folder."

    direct = [p for p in path.glob("*.xlsx") if not p.name.startswith("~$")]
    nested = [
        p
        for p in path.rglob("*.xlsx")
        if not p.name.startswith("~$") and p.parent != path
    ]
    folders = [p for p in path.iterdir() if p.is_dir()]
    others = [p for p in path.iterdir() if p.is_file() and p.suffix.lower() != ".xlsx"]

    lines = [
        f"'{path.name}' holds {len(direct)} .xlsx file(s) directly, "
        f"{len(nested)} in subfolders, {len(folders)} subfolder(s) "
        f"and {len(others)} other file(s)."
    ]

    if nested and mode is Mode.DEVICE:
        # By far the most common mistake: the stack folder picked for a device
        # import, which only ever looks at the top level.
        example = sorted({p.parent.name for p in nested})[:4]
        lines.append(
            f"The .xlsx files sit one level down, in {', '.join(example)}"
            f"{' and others' if len(example) < len({p.parent.name for p in nested}) else ''}. "
            "That is the layout a Stack import expects - use Ctrl+Shift+O, or "
            "pick one of those folders for a device import."
        )
    elif not direct and not nested:
        lines.append(
            "There are no Excel files anywhere below this folder. A device "
            "import expects the folder holding the .xlsx files; a stack import "
            "expects the folder holding the device folders."
        )
        if others:
            lines.extend("  " + p.name for p in others[:5])
    return "\n".join(lines)


class ImportWorker(QObject):
    """Import and figure build on a worker thread, so the UI stays responsive.

    The shipping worker also had to clear a temp folder full of generated HTML
    and fight Chromium's file locks for it. There are no files here, so that
    entire failure mode -- and its retry logic -- is gone.
    """

    progress = Signal(int)
    status = Signal(str)
    finished = Signal(object, object, object)  # LoadedData, Categories, Overview
    failed = Signal(str)

    def __init__(self, path: Path, mode: Mode) -> None:
        super().__init__()
        self.path = path
        self.mode = mode

    @Slot()
    def run(self) -> None:
        # Declared before the try so the failure path can still report it.
        log = io.StringIO()
        try:
            self.status.emit("Phase 1/3: importing Excel files into DuckDB...")
            self.progress.emit(5)
            # BatchConverter collects per-file warnings and prints them; convert()
            # returns only the database path, so capturing stdout is the only way
            # to get them in front of the user without changing the converter.
            with contextlib.redirect_stdout(log):
                BatchConverter(DB_FILE).convert(path_to_glob(self.path, self.mode))

            self.progress.emit(50)
            self.status.emit("Phase 2/3: building figures...")
            cfg = Config(db_file=DB_FILE, output_dir=HERE, mode=self.mode)
            data, categories = live_pipeline.load_and_build(cfg)

            self.progress.emit(85)
            self.status.emit("Phase 3/3: checking the data...")
            # Hashing every source file belongs on this thread, not the UI one.
            overview = dashboard_data.collect(
                data, DB_FILE, self.path, self.mode.value, import_log=log.getvalue()
            )

            self.progress.emit(100)
            self.finished.emit(data, categories, overview)
        except Exception as exc:
            # The per-file outcomes are what actually explains an empty
            # database; the traceback only says that it was empty. A packaged
            # build has no console, so this dialog is the only place they show.
            report = [str(exc)]
            # If files were read, explain what they produced; if none were, the
            # folder itself is what needs explaining.
            diagnosis = diagnose_import(log.getvalue())
            heading = "What the import produced:"
            if not diagnosis:
                diagnosis = diagnose_selection(self.path, self.mode)
                heading = "What the selected folder contains:"
            if diagnosis:
                report += ["", heading, diagnosis]
            if log.getvalue().strip():
                report += ["", "Import log:", log.getvalue().rstrip()]
            report += ["", traceback.format_exc()]
            self.failed.emit("\n".join(report))
        finally:
            # Echo the converter output either way, for anyone with a console.
            if log.getvalue():
                print(log.getvalue(), end="")
