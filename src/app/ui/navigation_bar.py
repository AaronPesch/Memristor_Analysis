import os
from pathlib import Path
import PySide6.QtWidgets as qt
from PySide6.QtCore import Qt

from .plot_viewer import PlotViewer
from app.core.paths import TEMP_DIR
from app.core.modes import Mode


class NavigationBar(qt.QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Map directories to Mode values
        self.temp_device_dir = TEMP_DIR / Mode.DEVICE.value
        self.temp_stack_dir = TEMP_DIR / Mode.STACK.value

        # Ensure directories exist
        self.temp_device_dir.mkdir(parents=True, exist_ok=True)
        self.temp_stack_dir.mkdir(parents=True, exist_ok=True)

        # Dropdown UI is removed completely
        self.show_welcome_screen()

    def is_folder_empty(self, directory: Path):
        """Checks if a directory exists and contains any HTML files."""
        if not directory.exists():
            return True
        return len(list(directory.rglob("*.html"))) == 0

    def show_welcome_screen(self):
        """Displays the startup information tab."""
        self.clear()

        welcome_widget = qt.QWidget()
        layout = qt.QVBoxLayout(welcome_widget)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)

        device_data_exists = not self.is_folder_empty(self.temp_device_dir)
        stack_data_exists = not self.is_folder_empty(self.temp_stack_dir)

        if not device_data_exists and not stack_data_exists:
            title = qt.QLabel("Please import data to start the analysis.")
            title.setStyleSheet("font-size: 18px; font-weight: bold; color: #ccc;")

            instructions = qt.QLabel(
                "Use the File menu or the following shortcuts:\n\n"
                "• Ctrl+O : Import Device Data\n"
                "• Ctrl+Shift+O : Import Stack Data"
            )
            instructions.setAlignment(Qt.AlignCenter)
            instructions.setStyleSheet(
                "font-size: 14px; color: #888; line-height: 150%;"
            )

            layout.addStretch()
            layout.addWidget(title, alignment=Qt.AlignCenter)
            layout.addWidget(instructions, alignment=Qt.AlignCenter)
            layout.addStretch()
        else:
            title = qt.QLabel("Existing analysis data found.")
            title.setStyleSheet("font-size: 18px; font-weight: bold; color: #ccc;")
            layout.addStretch()
            layout.addWidget(title, alignment=Qt.AlignCenter)

            if device_data_exists:
                dev_btn = qt.QPushButton("Continue Device Level Analysis")
                dev_btn.setFixedSize(300, 45)
                # We pass the mode value specifically
                dev_btn.clicked.connect(
                    lambda: self.update_tabs_by_level(Mode.DEVICE.value)
                )
                layout.addWidget(dev_btn, alignment=Qt.AlignCenter)

            if stack_data_exists:
                stack_btn = qt.QPushButton("Continue Stack Level Analysis")
                stack_btn.setFixedSize(300, 45)
                stack_btn.clicked.connect(
                    lambda: self.update_tabs_by_level(Mode.STACK.value)
                )
                layout.addWidget(stack_btn, alignment=Qt.AlignCenter)

            layout.addStretch()

        self.addTab(welcome_widget, "Start")

    def update_tabs_by_level(self, level_text=None):
        """
        Populates tabs based on the requested level.
        If level_text is None, it defaults to the MEMRISTOR_MODE environment variable.
        """
        self.clear()

        # Fallback to environment variable if no text is provided
        if level_text is None:
            level_text = os.environ.get("MEMRISTOR_MODE", Mode.DEVICE.value)

        param_labels = {
            "V_set": "V Set",
            "V_reset": "V Reset",
            "R_LRS": "R LRS",
            "R_HRS": "R HRS",
            "I_LRS": "I LRS",
            "I_HRS": "I HRS",
            "I_reset_max": "I Reset Max",
            "Memory_window": "Memory Window",
            "VSET": "V Set",
            "V_forming": "V Forming",
            "I_leakage_pristine": "I Leakage Pristine",
            "R_pristine": "R Pristine",
        }

        corr_labels = {
            "V_set_vs_I_HRS": "Vset vs IHRS",
            "V_set_vs_R_HRS": "Vset vs RHRS",
            "V_reset_vs_I_LRS": "Vreset vs ILRS",
            "V_reset_vs_R_LRS": "Vreset vs RLRS",
            "V_reset_vs_I_reset_max": "Vreset vs Ireset",
            "V_set_vs_V_reset": "Vset vs Vreset",
            "V_forming_vs_first_V_reset": "Forming vs 1st Reset",
            "I_leakage_pristine_vs_V_forming": "Leakage vs Forming",
            "R_pristine_vs_V_forming": "R Pristine vs Forming",
        }

        if level_text == Mode.DEVICE.value:
            base_dir = self.temp_device_dir
            char_labels = {"AI": "|Current| vs Voltage", "NORM_COND": "Normalized conductance"}

            self.addTab(
                self._create_nested_tab(
                    base_dir, "endurance_performance", param_labels
                ),
                "Endurance Performance",
            )
            self.addTab(
                self._create_nested_tab(base_dir, "boxplots", param_labels),
                "Endurance Boxplots",
            )
            self.addTab(
                self._create_nested_tab(base_dir, "cdfs", param_labels), "Endurance CDF"
            )
            self.addTab(
                self._create_nested_tab(base_dir, "characteristic_plots", char_labels),
                "Characteristic Plots",
            )
            self.addTab(
                self._create_nested_tab(base_dir, "correlation_plots", corr_labels),
                "Corr. Scatter",
            )
            self.addTab(
                self._create_nested_tab(
                    base_dir,
                    "correlation_matrices",
                    self._discover_labels(base_dir / "correlation_matrices"),
                ),
                "Corr. Matrix",
            )

        elif level_text == Mode.STACK.value:
            base_dir = self.temp_stack_dir
            char_labels = {
                "AI": "|Current| vs Voltage",
                "NORM_COND": "Normalized conductance",
                "butterfly_curve": "Butterfly",
            }

            self.addTab(
                self._create_nested_tab(base_dir, "boxplots_stack_level", param_labels),
                "Boxplots",
            )

            self.addTab(
                self._create_nested_tab(base_dir, "cdfs_stack_level", param_labels),
                "CDF",
            )

            self.addTab(
                self._create_nested_tab(
                    base_dir, "correlation_plots_stack_level", corr_labels
                ),
                "Corr. Scatter",
            )

            self.addTab(
                self._create_nested_tab(
                    base_dir,
                    "correlation_matrices_stack_level",
                    self._discover_labels(
                        base_dir / "correlation_matrices_stack_level"
                    ),
                ),
                "Corr. Matrix",
            )

    def _discover_labels(self, folder: Path) -> dict:
        """Auto-discover HTML files in a folder and build a labels map."""
        if not folder.exists():
            return {}
        return {
            f.stem: f.stem.replace("corr_matrix_", "").replace("_", " ").title()
            for f in sorted(folder.glob("*.html"))
        }

    def _create_nested_tab(self, base_dir: Path, subfolder_name: str, labels_map: dict):
        """Helper to create a QTabWidget from a subfolder of HTML files."""
        sub_tab_widget = qt.QTabWidget()
        folder_path = base_dir / subfolder_name

        found_any = False
        for param_id, label in labels_map.items():
            file_path = folder_path / f"{param_id}.html"
            if file_path.exists():
                viewer = PlotViewer()
                viewer.load_html_file(str(file_path))
                sub_tab_widget.addTab(viewer, label)
                found_any = True

        if not found_any:
            viewer = PlotViewer()
            viewer.browser.setHtml(
                "<body style='background:#111; color:#555; display:flex; justify-content:center; "
                "align-items:center; height:100vh; font-family:sans-serif;'>"
                f"<div>No data available in {subfolder_name}.</div></body>"
            )
            sub_tab_widget.addTab(viewer, "Empty")

        return sub_tab_widget

    def get_current_viewer(self) -> PlotViewer:
        widget = self.currentWidget()
        if isinstance(widget, PlotViewer):
            return widget
        if isinstance(widget, qt.QTabWidget):
            sub_widget = widget.currentWidget()
            if isinstance(sub_widget, PlotViewer):
                return sub_widget
        return None

    def get_all_viewers(self) -> list[PlotViewer]:
        viewers = []
        for i in range(self.count()):
            widget = self.widget(i)
            if isinstance(widget, PlotViewer):
                viewers.append(widget)
            elif isinstance(widget, qt.QTabWidget):
                for j in range(widget.count()):
                    sub_widget = widget.widget(j)
                    if isinstance(sub_widget, PlotViewer):
                        viewers.append(sub_widget)
        return viewers
