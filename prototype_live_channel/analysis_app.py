"""Memristor Analysis on a live channel -- the real importer, the real figures.

Run:  python analysis_app.py            (--smoke-test builds the UI and exits, for CI)

Against the shipping application exactly one thing differs: figures are never
written to disk. `live_pipeline` hands them over as objects, the bridge pushes
them into a page that stays alive for the whole session, and Plotly.react diffs
them in. Everything below that line -- the importer, the transforms, the twelve
fig_* builders, the preferences -- is the existing code, unmodified.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

from PySide6.QtCore import QThread, QUrl, Qt, Slot  # noqa: E402
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence  # noqa: E402
from PySide6.QtWebChannel import QWebChannel  # noqa: E402
from PySide6.QtWebEngineCore import QWebEngineSettings  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

import channel  # noqa: E402
import drilldown  # noqa: E402
import exporters  # noqa: E402
import fig_yield  # noqa: E402
import live_pipeline  # noqa: E402
from app.core import preferences  # noqa: E402
from app.core.modes import Mode  # noqa: E402

WEB_DIR = HERE / "web"
WIKI_URL = "https://github.com/AaronPesch/Memristor_Analysis/wiki"
WELCOME = (
    "Import data to start the analysis.\n\n"
    "Ctrl+O - device level     Ctrl+Shift+O - stack level"
)


class AnalysisWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Memristor Analysis - live channel")

        self.data = None
        self.categories: list[live_pipeline.Category] = []
        self.selection: set[str] = set()
        self.device_filter: list[str] | None = None
        self.drill: tuple | None = None
        self._owner_cache: dict[str, list] = {}
        self.mode: Mode | None = None
        self.dark = preferences.get_theme() == "dark"
        self.thread: QThread | None = None
        self.worker: channel.ImportWorker | None = None
        self._pending_mode: Mode | None = None
        self._loading = False

        self._build_menus()
        self._build_ui()
        self._restore_session()

        self.bridge = channel.Bridge(self)
        web_channel = QWebChannel(self.view.page())
        web_channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(web_channel)
        self.view.load(QUrl.fromLocalFile(str((WEB_DIR / "analysis.html").resolve())))

    # ---- construction -------------------------------------------------------

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        act_device = QAction("Import &Device Data...", self)
        act_device.setShortcut(QKeySequence("Ctrl+O"))
        act_device.triggered.connect(lambda: self.start_import(Mode.DEVICE))
        file_menu.addAction(act_device)

        act_stack = QAction("Import &Stack Data...", self)
        act_stack.setShortcut(QKeySequence("Ctrl+Shift+O"))
        act_stack.triggered.connect(lambda: self.start_import(Mode.STACK))
        file_menu.addAction(act_stack)
        file_menu.addSeparator()

        current = file_menu.addMenu("Export &current plot")
        for label, fmt in [
            ("PNG", "png"),
            ("JPEG", "jpeg"),
            ("SVG", "svg"),
            ("PDF", "pdf"),
            ("EPS", "eps"),
            ("CSV (data)", "csv"),
            ("TXT (data)", "txt"),
        ]:
            action = QAction(label, self)
            action.triggered.connect(lambda _=False, f=fmt: self.export_current(f))
            current.addAction(action)

        every = file_menu.addMenu("Export &all plots")
        for label, fmt in [
            ("PNG", "png"),
            ("JPEG", "jpeg"),
            ("SVG", "svg"),
            ("PDF", "pdf"),
        ]:
            action = QAction(label, self)
            action.triggered.connect(lambda _=False, f=fmt: self.export_all(f))
            every.addAction(action)
        every.addSeparator()
        act_pdf = QAction("Combined multi-page PDF", self)
        act_pdf.triggered.connect(self.export_combined_pdf)
        every.addAction(act_pdf)
        act_pptx = QAction("PowerPoint (one plot per slide)", self)
        act_pptx.triggered.connect(self.export_pptx)
        every.addAction(act_pptx)

        file_menu.addSeparator()
        act_quit = QAction("&Quit", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        help_menu = self.menuBar().addMenu("&Help")
        act_wiki = QAction("Project &Wiki", self)
        act_wiki.setShortcut(QKeySequence("F1"))
        act_wiki.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(WIKI_URL)))
        help_menu.addAction(act_wiki)

    def _build_ui(self) -> None:
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(6, 4, 6, 2)
        outer.setSpacing(4)

        self.category_bar = QTabBar()
        self.category_bar.setExpanding(False)
        self.category_bar.currentChanged.connect(self.on_category_changed)
        outer.addWidget(self.category_bar)

        self.sub_bar = QTabBar()
        self.sub_bar.setExpanding(False)
        self.sub_bar.setDrawBase(False)
        self.sub_bar.setUsesScrollButtons(True)
        self.sub_bar.currentChanged.connect(self.on_subtab_changed)
        outer.addWidget(self.sub_bar)

        controls = QHBoxLayout()
        self.scale_box = QCheckBox("log y-axis")
        self.scale_box.toggled.connect(self.on_scale_toggled)
        controls.addWidget(self.scale_box)

        self.dark_box = QCheckBox("dark mode")
        self.dark_box.setChecked(self.dark)
        self.dark_box.toggled.connect(self.on_dark_toggled)
        controls.addWidget(self.dark_box)

        # Yield controls, shown only while the yield tab is selected.
        self.yield_widget = QWidget()
        yield_row = QHBoxLayout(self.yield_widget)
        yield_row.setContentsMargins(14, 0, 0, 0)
        yield_row.addWidget(QLabel("Pass if value"))
        self.op_box = QComboBox()
        self.op_box.addItems([">=", "<="])
        self.op_box.currentTextChanged.connect(lambda _: self.on_yield_changed())
        yield_row.addWidget(self.op_box)
        self.threshold_edit = QLineEdit()
        self.threshold_edit.setFixedWidth(120)
        self.threshold_edit.setPlaceholderText("threshold")
        self.threshold_edit.editingFinished.connect(self.on_yield_changed)
        yield_row.addWidget(self.threshold_edit)
        controls.addWidget(self.yield_widget)
        self.yield_widget.setVisible(False)

        controls.addStretch(1)
        self.filter_button = QPushButton("Filter to selection")
        self.filter_button.clicked.connect(self.apply_device_filter)
        self.filter_button.setEnabled(False)
        controls.addWidget(self.filter_button)
        self.back_button = QPushButton("← Back to plot")
        self.back_button.clicked.connect(self.leave_drill)
        self.back_button.setVisible(False)
        controls.addWidget(self.back_button)
        self.clear_button = QPushButton("Show all devices")
        self.clear_button.clicked.connect(self.clear_device_filter)
        self.clear_button.setEnabled(False)
        controls.addWidget(self.clear_button)
        outer.addLayout(controls)

        self.view = QWebEngineView()
        self.view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        outer.addWidget(self.view, 1)
        self.setCentralWidget(root)
        self.statusBar().showMessage("No data imported yet.")

    # ---- session memory -----------------------------------------------------

    def _restore_session(self) -> None:
        window = preferences.get_window()
        if window:
            self.setGeometry(
                window["x"], window["y"], window["width"], window["height"]
            )
        else:
            self.resize(1380, 900)
        session = preferences.get_session() or {}
        self._wanted_tab = int(session.get("tab_index", 0) or 0)
        self._wanted_sub = int(session.get("sub_tab_index", 0) or 0)

    def closeEvent(self, event) -> None:
        geometry = self.geometry()
        preferences.set_window(
            geometry.x(), geometry.y(), geometry.width(), geometry.height()
        )
        preferences.set_session(
            self.mode.value if self.mode else None,
            self.category_bar.currentIndex(),
            self.sub_bar.currentIndex(),
        )
        preferences.set_theme("dark" if self.dark else "light")
        super().closeEvent(event)

    # ---- which plot is showing ---------------------------------------------

    @property
    def category(self) -> live_pipeline.Category | None:
        index = self.category_bar.currentIndex()
        if 0 <= index < len(self.categories):
            return self.categories[index]
        return None

    def current_figure(self):
        category = self.category
        if category is None:
            return None, None
        ids = category.param_ids
        index = self.sub_bar.currentIndex()
        if not ids or not (0 <= index < len(ids)):
            return None, None
        param_id = ids[index]
        return f"{category.key}/{param_id}", category.figures[param_id]

    def current_payload(self) -> dict:
        if self.drill is not None:
            fig, label = self.drill
            key = f"drill/{label}"
            return {
                "key": key,
                "figure": channel.figure_payload(fig, key, self.dark, None),
            }

        key, fig = self.current_figure()
        if fig is None:
            return {"figure": None, "message": WELCOME}
        payload = channel.figure_payload(
            fig, key, self.dark, preferences.get_scale(key)
        )
        # Highlighting is applied to the payload, not the figure: no rebuild, so
        # it lands instantly and on every tab at once.
        return {
            "key": key,
            "figure": drilldown.apply_highlight(
                payload, self._trace_owners(key, fig), self.selection
            ),
        }

    def _trace_owners(self, key: str, fig) -> list[str | None]:
        """Which device each trace belongs to, cached per plot."""
        if self.data is None:
            return []
        if key not in self._owner_cache:
            self._owner_cache[key] = drilldown.trace_devices(
                fig, self.data.devices, self.data.stack_id
            )
        return self._owner_cache[key]

    # ---- point resolution ---------------------------------------------------

    def resolve_device(self, ref: dict) -> str | None:
        if self.data is None:
            return None
        return drilldown.resolve_device(ref, self.data.devices, self.data.stack_id)

    def resolve_devices(self, refs: list[dict]) -> list[str]:
        seen: list[str] = []
        for ref in refs:
            device = self.resolve_device(ref)
            if device and device not in seen:
                seen.append(device)
        return seen

    # ---- drill-down ---------------------------------------------------------

    def drill_to(self, device: str, cycle: int | None) -> None:
        if self.data is None:
            return
        fig, label = drilldown.build_drill_figure(self.data, device, cycle)
        if fig is None:
            self.statusBar().showMessage(label)
            return
        self.drill = (fig, label)
        self.back_button.setVisible(True)
        self.statusBar().showMessage(f"Raw sweep: {label}")

    def leave_drill(self) -> None:
        self.drill = None
        self.back_button.setVisible(False)
        self.push()

    def push(self) -> None:
        self.bridge.push()

    # ---- import -------------------------------------------------------------

    def start_import(self, mode: Mode, folder: str | None = None) -> None:
        if self._loading:
            return
        if folder is None:
            caption = (
                "Select the DEVICE folder (contains the .xlsx files)"
                if mode is Mode.DEVICE
                else "Select the STACK folder (contains the device folders)"
            )
            folder = QFileDialog.getExistingDirectory(self, caption)
        if not folder:
            return

        self._loading = True
        self._pending_mode = mode
        self.progress = QProgressDialog("Starting...", None, 0, 100, self)
        self.progress.setWindowTitle("Import")
        self.progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress.setMinimumDuration(0)
        self.progress.setValue(0)

        self.thread = QThread(self)
        self.worker = channel.ImportWorker(Path(folder), mode)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.status.connect(self.progress.setLabelText)
        self.worker.status.connect(self.statusBar().showMessage)
        # Must be a bound method of this QObject, not a lambda: Qt cannot work
        # out a receiver thread for a plain callable, falls back to a direct
        # connection, and the handler would then run on the worker thread --
        # where _stop_thread()'s wait() deadlocks on itself.
        self.worker.finished.connect(self._on_import_finished)
        self.worker.failed.connect(self.on_import_failed)
        self.thread.start()

    @Slot(object, object)
    def _on_import_finished(self, data, categories) -> None:
        self.on_import_done(self._pending_mode, data, categories)

    def _stop_thread(self) -> None:
        self._loading = False
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait()
            self.thread = None
        self.worker = None
        if hasattr(self, "progress"):
            self.progress.close()

    def on_import_done(self, mode: Mode, data, categories) -> None:
        self._stop_thread()
        self.mode = mode
        self.data = data
        self.categories = categories
        self._owner_cache.clear()
        self.drill = None
        self.selection = set()
        self.device_filter = None
        self.populate_tabs()
        self.refresh_selection_ui()
        total = sum(len(c.figures) for c in categories)
        self.statusBar().showMessage(
            f"{mode.value} level | stack {data.stack_id} | {len(data.devices)} devices "
            f"| {len(categories)} categories | {total} plots"
        )

    def on_import_failed(self, message: str) -> None:
        self._stop_thread()
        self.statusBar().showMessage("Import failed.")
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("Import failed")
        box.setText(message.splitlines()[0])
        box.setDetailedText(message)
        box.exec()

    # ---- tabs ---------------------------------------------------------------

    def populate_tabs(self) -> None:
        self.category_bar.blockSignals(True)
        while self.category_bar.count():
            self.category_bar.removeTab(0)
        for category in self.categories:
            self.category_bar.addTab(category.label)
        self.category_bar.blockSignals(False)

        index = self._wanted_tab if self._wanted_tab < len(self.categories) else 0
        self.category_bar.setCurrentIndex(index)
        self.on_category_changed(index)

    def on_category_changed(self, index: int) -> None:
        category = self.category
        self.sub_bar.blockSignals(True)
        while self.sub_bar.count():
            self.sub_bar.removeTab(0)
        if category is not None:
            for param_id in category.param_ids:
                self.sub_bar.addTab(pretty_label(param_id))
        self.sub_bar.blockSignals(False)

        wanted = self._wanted_sub if self._wanted_sub < self.sub_bar.count() else 0
        self._wanted_sub = 0
        self.sub_bar.setCurrentIndex(wanted)
        self.on_subtab_changed(wanted)

    def on_subtab_changed(self, _index: int) -> None:
        # Changing tabs leaves the drill-down view.
        self.drill = None
        self.back_button.setVisible(False)
        key, fig = self.current_figure()
        is_yield = bool(self.category and self.category.key.startswith("yield"))
        self.yield_widget.setVisible(is_yield)
        if is_yield and fig is not None:
            meta = (fig.layout.meta or {}).get("yield", {})
            self.op_box.blockSignals(True)
            self.op_box.setCurrentText(meta.get("operator", ">="))
            self.op_box.blockSignals(False)
            self.threshold_edit.setText(f"{meta.get('threshold', 0):.6g}")

        if key is not None:
            scale = preferences.get_scale(key)
            if scale is None and fig is not None:
                scale = getattr(fig.layout.yaxis, "type", None) or "linear"
            self.scale_box.blockSignals(True)
            self.scale_box.setChecked(scale == "log")
            self.scale_box.blockSignals(False)
        self.push()

    # ---- view options -------------------------------------------------------

    def on_scale_toggled(self, checked: bool) -> None:
        key, _ = self.current_figure()
        if key is None:
            return
        preferences.set_scale(key, "log" if checked else "linear")
        self.push()

    def on_dark_toggled(self, checked: bool) -> None:
        self.dark = checked
        preferences.set_theme("dark" if checked else "light")
        self.push()

    # ---- yield map ----------------------------------------------------------

    def on_yield_changed(self) -> None:
        category = self.category
        if category is None or self.data is None:
            return
        index = self.sub_bar.currentIndex()
        ids = category.param_ids
        if not (0 <= index < len(ids)):
            return
        param_id = ids[index]
        meta = (category.figures[param_id].layout.meta or {}).get("yield")
        if not meta:
            return
        try:
            threshold = float(self.threshold_edit.text().replace(",", "."))
        except ValueError:
            self.statusBar().showMessage("Threshold must be a number.")
            return

        devices = self.device_filter or self.data.devices
        rebuilt = fig_yield.build_yield_map(
            box_table=self.data.box_table,
            stack_id=self.data.stack_id,
            devices=devices,
            column=meta["column"],
            label=meta["label"],
            is_log=meta["is_log"],
            operator=self.op_box.currentText(),
            threshold=threshold,
        )
        if rebuilt is None:
            return
        category.figures[param_id] = rebuilt
        info = rebuilt.layout.meta["yield"]
        self.statusBar().showMessage(
            f"{info['label']} {info['operator']} {info['threshold']:.4g} -> "
            f"{info['passed']}/{info['tested']} pass ({info['percent']:.1f} %)"
        )
        self.push()

    # ---- device selection / cross-filter -----------------------------------

    def refresh_selection_ui(self) -> None:
        self.filter_button.setEnabled(bool(self.selection))
        self.clear_button.setEnabled(self.device_filter is not None)
        if self.selection:
            self.statusBar().showMessage(
                f"{len(self.selection)} device(s) selected: "
                + ", ".join(sorted(self.selection)[:12])
            )

    def apply_device_filter(self) -> None:
        if not self.selection or self.data is None or self.mode is None:
            return
        self.device_filter = sorted(self.selection)
        self._rebuild(self.device_filter)

    def clear_device_filter(self) -> None:
        if self.data is None or self.mode is None:
            return
        self.device_filter = None
        self.selection = set()
        self._rebuild(None)

    def _rebuild(self, devices: list[str] | None) -> None:
        """Re-run the builders for a device subset.

        The builders already take `devices` as a parameter, so restricting the
        analysis is a re-run, not a new code path.
        """
        data = self.data
        if devices is not None:
            data = dataclasses.replace(self.data, devices=devices)
        self.statusBar().showMessage("Rebuilding figures...")
        QApplication.processEvents()
        if self.mode is Mode.DEVICE:
            self.categories = live_pipeline.build_device_categories(data)
        else:
            self.categories = live_pipeline.build_stack_categories(data)
        self.categories = [c for c in self.categories if c.figures]
        self._owner_cache.clear()
        self.drill = None
        self.populate_tabs()
        self.refresh_selection_ui()
        count = len(devices) if devices else len(self.data.devices)
        self.statusBar().showMessage(f"Showing {count} device(s).")

    # ---- export -------------------------------------------------------------

    def _figures_for_export(self) -> list[tuple[str, object]]:
        out = []
        for category in self.categories:
            for param_id, fig in category.figures.items():
                out.append((f"{category.key}__{param_id}", fig))
        return out

    def export_current(self, fmt: str) -> None:
        key, fig = self.current_figure()
        if fig is None:
            return
        name = key.replace("/", "__")
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export {fmt.upper()}", f"{name}.{fmt}", f"*.{fmt}"
        )
        if not path:
            return
        try:
            if fmt in ("csv", "txt"):
                exporters.write_data(fig, Path(path), fmt)
            else:
                exporters.write_image(fig, Path(path), fmt)
            self.statusBar().showMessage(f"Exported {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def export_all(self, fmt: str) -> None:
        figures = self._figures_for_export()
        if not figures:
            return
        folder = QFileDialog.getExistingDirectory(self, "Export all plots into folder")
        if not folder:
            return
        self._run_batch_export(
            lambda: exporters.write_all_images(figures, Path(folder), fmt),
            f"all plots as {fmt.upper()}",
        )

    def export_combined_pdf(self) -> None:
        figures = self._figures_for_export()
        if not figures:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Combined PDF", "memristor_plots.pdf", "*.pdf"
        )
        if path:
            self._run_batch_export(
                lambda: exporters.write_combined_pdf(figures, Path(path)),
                "combined PDF",
            )

    def export_pptx(self) -> None:
        figures = self._figures_for_export()
        if not figures:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "PowerPoint", "memristor_plots.pptx", "*.pptx"
        )
        if path:
            self._run_batch_export(
                lambda: exporters.write_pptx(figures, Path(path)), "PowerPoint"
            )

    def _run_batch_export(self, job, what: str) -> None:
        self.statusBar().showMessage(f"Exporting {what}...")
        QApplication.processEvents()
        try:
            written = job()
            self.statusBar().showMessage(f"Exported {written} plot(s) as {what}.")
        except Exception as exc:
            self.statusBar().showMessage("Export failed.")
            QMessageBox.critical(self, "Export failed", str(exc))


def pretty_label(param_id: str) -> str:
    """Human-readable sub-tab label, matching the shipping navigation bar."""
    labels = {
        "AI": "|Current| vs Voltage",
        "NORM_COND": "Normalized Conductance",
        "butterfly_curve": "Butterfly Curve",
        "VSET": "V Set",
        "V_set": "V Set",
        "V_reset": "V Reset",
        "R_LRS": "R LRS",
        "R_HRS": "R HRS",
        "I_LRS": "I LRS",
        "I_HRS": "I HRS",
        "I_reset_max": "I Reset Max",
        "Memory_window": "Memory Window",
        "V_forming": "V Forming",
        "I_leakage_pristine": "I Leakage Pristine",
        "R_pristine": "R Pristine",
    }
    if param_id in labels:
        return labels[param_id]
    for prefix, kind in (("spatial_", ""), ("yield_", "")):
        if param_id.startswith(prefix):
            rest = param_id[len(prefix) :]
            return labels.get(rest, rest.replace("_", " "))
    if param_id.startswith("corr_matrix_"):
        return param_id[len("corr_matrix_") :]
    return param_id.replace("_vs_", " vs ").replace("_", " ")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="build the window, then exit immediately (for CI)",
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    channel.export_static_assets()
    window = AnalysisWindow()
    window.show()

    if args.smoke_test:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(2500, app.quit)
        app.exec()
        print("smoke test ok")
        return

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
