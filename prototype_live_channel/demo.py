"""Live-channel demo: PySide6 + QWebChannel + Plotly, no HTML files on disk.

Run:  python demo.py

The contrast with the file-based approach:

  before   DuckDB -> figure -> write_html(...) -> QWebEngineView.load(file://)
           one dead snapshot per plot, ~4.5 MB of plotly.js embedded in each

  here     DuckDB <-> Bridge (QWebChannel) <-> one live page
           plotly.js loaded once, figures pushed as JSON, Plotly.react() diffs
           them in, and the page can talk back
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QFile, QIODevice, QObject, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import plotly
import figures
from data import N_CYCLES, PARAMS, Store

WEB_DIR = Path(__file__).parent / "web"


def export_static_assets() -> None:
    """Put plotly.js and qwebchannel.js next to the page. Both ship with
    packages we already depend on, so the app never touches the network.

    plotly.py carries the exact plotly.js build its figures were written for
    (7.0.0 -> plotly.js 4.0.0). Pinning a CDN version by hand invites a
    mismatch; copying the bundled file cannot drift.
    """
    bundled = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
    if bundled.exists():
        (WEB_DIR / "plotly.min.js").write_bytes(bundled.read_bytes())

    # qwebchannel.js lives inside Qt's resource system.
    resource = QFile(":/qtwebchannel/qwebchannel.js")
    if resource.open(QIODevice.OpenModeFlag.ReadOnly):
        (WEB_DIR / "qwebchannel.js").write_bytes(bytes(resource.readAll()))
        resource.close()


class Bridge(QObject):
    """The two-way channel. JS calls the @Slot methods; Python pushes through
    the Signal. This object is the entire interface between the two worlds."""

    figuresChanged = Signal(str)  # Python -> JS

    def __init__(self, store: Store) -> None:
        super().__init__()
        self.store = store
        self.param = "r_hrs"
        self.dark = False
        self.log = True
        self.selected: set[str] = set()
        self.cycles: tuple[int, int] = (1, N_CYCLES)
        self.on_status = lambda text: None

    # ---------- called from JavaScript ----------

    @Slot(result=str)
    def bootstrap(self) -> str:
        """First call once the page is up: hand it every figure."""
        return self.payload(source=None)

    @Slot(str, result=str)
    def select(self, request_json: str) -> str:
        """A selection happened in a plot. Re-query and answer with new figures.

        This is the round trip that a static HTML file cannot make.
        """
        req = json.loads(request_json)
        kind = req.get("kind")

        if kind == "devices":
            self.selected = set(req.get("devices") or [])
        elif kind == "toggle":
            device = req["device"]
            self.selected ^= {device}
        elif kind == "cycles":
            lo, hi = req["cycles"]
            self.cycles = (max(1, int(lo)), min(N_CYCLES, int(hi)))
        elif kind == "reset":
            self.selected = set()
            self.cycles = (1, N_CYCLES)

        return self.payload(source=req.get("source"))

    # ---------- figure assembly ----------

    def payload(self, source: str | None) -> str:
        store, param, dark = self.store, self.param, self.dark
        store.begin_timing()

        spatial_rows = store.spatial(param, self.cycles)
        scatter_rows = store.scatter(self.cycles)
        all_vals = store.values(param, [], self.cycles)
        sel_vals = store.values(param, sorted(self.selected), self.cycles)
        end_rows = store.endurance(param, sorted(self.selected))

        figs = {
            "map": figures.spatial_map(spatial_rows, self.selected, param, dark),
            "scatter": figures.correlation(scatter_rows, self.selected, dark),
            "cdf": figures.cdf(all_vals, sel_vals, param, dark, log_x=self.log),
            "endurance": figures.endurance(end_rows, param, dark, log_y=self.log),
        }

        n_dev = len(self.selected) or len(store.devices)
        self.on_status(
            f"{n_dev} device(s) | cycles {self.cycles[0]}-{self.cycles[1]} | "
            f"{sel_vals.size if self.selected else all_vals.size:,} values | "
            f"DuckDB {store.last_query_ms:.1f} ms"
        )

        return json.dumps(
            {
                "source": source,
                "figures": {k: json.loads(f.to_json()) for k, f in figs.items()},
            }
        )

    def push(self) -> None:
        """Qt-side control changed something -> push new figures to the page."""
        self.figuresChanged.emit(self.payload(source=None))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Memristor Analysis - live channel demo")
        self.resize(1360, 900)

        self.bridge = Bridge(Store())
        self.bridge.on_status = self._set_status

        self.view = QWebEngineView()
        settings = self.view.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )

        channel = QWebChannel(self.view.page())
        channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(channel)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.addLayout(self._build_toolbar())
        layout.addWidget(self.view, 1)
        self.status = QLabel("loading ...")
        layout.addWidget(self.status)
        self.setCentralWidget(root)

        self.view.load(QUrl.fromLocalFile(str((WEB_DIR / "index.html").resolve())))

    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Parameter:"))

        self.param_box = QComboBox()
        for key, (label, _unit, _log) in PARAMS.items():
            self.param_box.addItem(label, key)
        self.param_box.currentIndexChanged.connect(self._on_param)
        bar.addWidget(self.param_box)

        self.log_box = QCheckBox("log scale")
        self.log_box.setChecked(True)
        self.log_box.toggled.connect(self._on_log)
        bar.addWidget(self.log_box)

        self.dark_box = QCheckBox("dark mode")
        self.dark_box.toggled.connect(self._on_dark)
        bar.addWidget(self.dark_box)

        reset = QPushButton("Reset selection")
        reset.clicked.connect(self._on_reset)
        bar.addWidget(reset)

        bar.addStretch(1)
        bar.addWidget(
            QLabel(
                "Tip: zoom into a plot, then toggle log or dark - the zoom survives."
            )
        )
        return bar

    # Every handler is the same three lines: change state, re-query, push.
    # No file is written, no page is reloaded.
    def _on_param(self, _index: int) -> None:
        self.bridge.param = self.param_box.currentData()
        self.bridge.push()

    def _on_log(self, checked: bool) -> None:
        self.bridge.log = checked
        self.bridge.push()

    def _on_dark(self, checked: bool) -> None:
        self.bridge.dark = checked
        self.bridge.push()

    def _on_reset(self) -> None:
        self.bridge.selected = set()
        self.bridge.cycles = (1, N_CYCLES)
        self.bridge.push()

    def _set_status(self, text: str) -> None:
        self.status.setText(text)


def main() -> None:
    app = QApplication(sys.argv)
    export_static_assets()
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
