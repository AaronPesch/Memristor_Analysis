from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget
from PySide6.QtCore import QUrl
from pathlib import Path
import plotly.io as pio
import os
import csv
import base64
import numpy as np
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPS
import tempfile

_LEGEND_PX_PER_ENTRY = 35


class PlotViewer(QWidget):
    def __init__(self, figure=None):
        super().__init__()
        self.figure = figure
        self.html_path: str | None = None
        self.default_scale: str | None = None
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)  # Remove padding

        self.browser = QWebEngineView()
        self.main_layout.addWidget(self.browser)

        if figure:
            self.render_plot()

    def render_plot(self):
        if self.figure is not None:
            # Note: include_plotlyjs='cdn' requires internet.
            # Use 'require' or True for offline use.
            html = self.figure.to_html(include_plotlyjs="cdn", full_html=False)
            self.browser.setHtml(html)
        else:
            self.browser.setHtml(
                "<html><body style='background:#111; color:#555; display:flex; justify-content:center; align-items:center; height:100vh; font-family:sans-serif;'><div>No plot data available.</div></body></html>"
            )

    def load_html_file(self, file_path: str):
        if os.path.exists(file_path):
            self.html_path = file_path
            local_url = QUrl.fromLocalFile(os.path.abspath(file_path))
            self.browser.load(local_url)
            if self.default_scale:
                self.browser.loadFinished.connect(self._apply_default_scale)
        else:
            print(f"Error: File not found at {file_path}")

    def _apply_default_scale(self, ok: bool):
        self.browser.loadFinished.disconnect(self._apply_default_scale)
        if ok and self.default_scale:
            self.set_scale(self.default_scale)

    def set_scale(self, scale_type: str):
        if self.figure is not None:
            self.figure.update_layout(yaxis_type=scale_type)
            self.render_plot()
        else:
            js = f"""
            var divs = document.querySelectorAll('.plotly-graph-div');
            if (divs.length > 0) {{
                Plotly.relayout(divs[0], {{
                     'yaxis.type': '{scale_type}',
                    'yaxis.autorange': true
                }});
            }}
            """
            self.browser.page().runJavaScript(js)

    @staticmethod
    def _prepare_for_export(fig):
        """Return a figure with height expanded to fit all legend entries, if needed."""
        n = sum(1 for t in fig.data if getattr(t, "showlegend", True) is not False)
        current_h = fig.layout.height or 700
        needed = max(current_h, n * _LEGEND_PX_PER_ENTRY)
        if needed > current_h:
            fig = pio.from_json(fig.to_json())
            fig.update_layout(height=needed, legend=dict(maxheight=needed))
        return fig

    def export_image(self, out_path: str, fmt: str) -> bool:
        fmt = fmt.lower().strip()

        if self.figure is not None:
            fig = self._prepare_for_export(self.figure)
            if fmt == "eps":
                with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp:
                    svg_path = tmp.name
                try:
                    fig.write_image(svg_path, format="svg")

                    drawing = svg2rlg(svg_path)
                    if drawing is None:
                        print("EPS export failed: SVG parsing returned None")
                        return False

                    renderPS.drawToFile(drawing, out_path)
                    return True

                except Exception as e:
                    print(f"EPS export error: {e}")
                    return False

                finally:
                    if os.path.exists(svg_path):
                        os.remove(svg_path)

            try:
                fig.write_image(out_path, format=fmt)
                return True
            except Exception as e:
                print(f"Export error: {e}")
                return False

        # Otherwise export from sidecar JSON next to the loaded HTML
        if not self.html_path:
            return False

        json_path = Path(self.html_path).with_suffix(".json")
        if not json_path.exists():
            return False

        fig = pio.from_json(json_path.read_text(encoding="utf-8"))
        fig = self._prepare_for_export(fig)

        if fmt == "eps":
            with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp:
                svg_path = tmp.name
            try:
                fig.write_image(svg_path, format="svg")

                drawing = svg2rlg(svg_path)
                if drawing is None:
                    print("EPS export failed: SVG parsing returned None")
                    return False

                renderPS.drawToFile(drawing, out_path)
                return True

            except Exception as e:
                print(f"EPS export error: {e}")
                return False

            finally:
                if os.path.exists(svg_path):
                    os.remove(svg_path)

        # Normal formats (PNG/SVG/PDF)
        fig.write_image(out_path, format=fmt)
        return True

    def export_data(self, out_path: str, fmt: str) -> bool:
        fig = self._resolve_figure()
        if fig is None:
            return False

        delimiter = "\t" if fmt.lower() == "txt" else ","
        columns = self._extract_trace_columns(fig)
        if not columns:
            return False

        try:
            self._write_delimited(out_path, columns, delimiter)
            return True
        except Exception as e:
            print(f"Data export error: {e}")
            return False

    def _resolve_figure(self):
        if self.figure is not None:
            return self.figure

        if not self.html_path:
            return None

        json_path = Path(self.html_path).with_suffix(".json")
        if not json_path.exists():
            return None

        return pio.from_json(json_path.read_text(encoding="utf-8"))

    @staticmethod
    def _decode_array(arr):
        if arr is None:
            return []
        if isinstance(arr, dict) and "bdata" in arr:
            return np.frombuffer(
                base64.b64decode(arr["bdata"]), dtype=arr["dtype"]
            ).tolist()
        if hasattr(arr, "tolist"):
            return arr.tolist()
        return list(arr)

    @staticmethod
    def _extract_trace_columns(fig):
        columns = []
        for trace in fig.data:
            name = trace.name or "trace"
            if trace.type == "box":
                y = PlotViewer._decode_array(trace.y)
                columns.append((f"{name}_y", y))
            else:
                x = PlotViewer._decode_array(trace.x)
                y = PlotViewer._decode_array(trace.y)
                columns.append((f"{name}_x", x))
                columns.append((f"{name}_y", y))
        return columns

    @staticmethod
    def _write_delimited(out_path, columns, delimiter):
        headers = [col[0] for col in columns]
        data = [col[1] for col in columns]
        max_len = max(len(d) for d in data) if data else 0

        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=delimiter)
            writer.writerow(headers)
            for i in range(max_len):
                row = [d[i] if i < len(d) else "" for d in data]
                writer.writerow(row)
