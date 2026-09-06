"""Export figures to images, data files, a multi-page PDF and PowerPoint.

Note what is missing compared with the shipping `PlotViewer`: there is no
sidecar `.json` to read back and no `html_path` to derive it from. The figure
object is right here, so every exporter starts from the real thing.
"""

from __future__ import annotations

import csv
import io
import os
import tempfile
from pathlib import Path

import numpy as np
import plotly.io as pio

LEGEND_PX_PER_ENTRY = 35
IMAGE_FORMATS = {"png", "jpeg", "jpg", "svg", "pdf", "eps"}


def prepare(fig):
    """Grow the figure so every legend entry fits, as the shipping export does."""
    entries = sum(1 for t in fig.data if getattr(t, "showlegend", True) is not False)
    height = fig.layout.height or 700
    needed = max(height, entries * LEGEND_PX_PER_ENTRY)
    if needed <= height:
        return fig
    grown = pio.from_json(fig.to_json())
    grown.update_layout(height=needed, legend=dict(maxheight=needed))
    return grown


def _png_bytes(fig, scale: float = 2.0) -> bytes:
    return prepare(fig).to_image(format="png", scale=scale)


def write_image(fig, path: Path, fmt: str) -> None:
    fmt = fmt.lower().strip()
    if fmt not in IMAGE_FORMATS:
        raise ValueError(f"Unsupported image format: {fmt}")
    prepared = prepare(fig)

    if fmt == "eps":
        # kaleido has no EPS writer, so go via SVG like the shipping viewer.
        #
        # Plotly's default font stack starts with Verdana, which svglib cannot
        # resolve to a ReportLab font -- it raises KeyError('Verdana') and the
        # export dies. Pin one of the built-in PostScript fonts for the SVG
        # hand-off; it only affects the EPS, never the on-screen figure.
        from reportlab.graphics import renderPS
        from svglib.svglib import svg2rlg

        prepared = pio.from_json(prepared.to_json())
        prepared.update_layout(font_family="Helvetica")

        handle, svg_path = tempfile.mkstemp(suffix=".svg")
        os.close(handle)
        try:
            prepared.write_image(svg_path, format="svg")
            drawing = svg2rlg(svg_path)
            if drawing is None:
                raise RuntimeError("EPS export failed: could not parse the SVG")
            renderPS.drawToFile(drawing, str(path))
        finally:
            Path(svg_path).unlink(missing_ok=True)
        return

    prepared.write_image(str(path), format=fmt)


def _decode(array):
    """Plotly may hand back base64-packed binary arrays; normalize to a list."""
    if array is None:
        return []
    if isinstance(array, dict) and "bdata" in array:
        import base64

        return np.frombuffer(
            base64.b64decode(array["bdata"]), dtype=array["dtype"]
        ).tolist()
    if hasattr(array, "tolist"):
        return array.tolist()
    return list(array)


def trace_columns(fig) -> list[tuple[str, list]]:
    columns: list[tuple[str, list]] = []
    for index, trace in enumerate(fig.data):
        name = trace.name or f"trace{index}"
        if trace.type in ("box", "violin"):
            columns.append((f"{name}_y", _decode(trace.y)))
        elif trace.type == "heatmap":
            columns.append((f"{name}_x", _decode(trace.x)))
            columns.append((f"{name}_y", _decode(trace.y)))
            z = _decode(trace.z)
            for row_index, row in enumerate(z):
                columns.append((f"{name}_z{row_index}", _decode(row)))
        else:
            columns.append((f"{name}_x", _decode(trace.x)))
            columns.append((f"{name}_y", _decode(trace.y)))
    return columns


def write_data(fig, path: Path, fmt: str) -> None:
    columns = trace_columns(fig)
    if not columns:
        raise RuntimeError("This plot carries no tabular data to export.")
    delimiter = "\t" if fmt.lower() == "txt" else ","
    longest = max((len(values) for _, values in columns), default=0)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter=delimiter)
        writer.writerow([name for name, _ in columns])
        for row in range(longest):
            writer.writerow(
                [values[row] if row < len(values) else "" for _, values in columns]
            )


def write_all_images(figures: list[tuple[str, object]], folder: Path, fmt: str) -> int:
    folder.mkdir(parents=True, exist_ok=True)
    written = 0
    for name, fig in figures:
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
        write_image(fig, folder / f"{safe}.{fmt}", fmt)
        written += 1
    return written


def write_combined_pdf(figures: list[tuple[str, object]], path: Path) -> int:
    """One plot per page, sized to the rendered image."""
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas

    pdf = rl_canvas.Canvas(str(path))
    written = 0
    for name, fig in figures:
        reader = ImageReader(io.BytesIO(_png_bytes(fig)))
        width, height = reader.getSize()
        pdf.setPageSize((width, height))
        pdf.drawImage(reader, 0, 0, width=width, height=height)
        pdf.setTitle(name)
        pdf.showPage()
        written += 1
    pdf.save()
    return written


def write_pptx(figures: list[tuple[str, object]], path: Path) -> int:
    """One plot per slide, centred on a 16:9 blank layout."""
    from pptx import Presentation
    from pptx.util import Emu, Inches

    deck = Presentation()
    deck.slide_width = Inches(13.333)
    deck.slide_height = Inches(7.5)
    blank = deck.slide_layouts[6]

    written = 0
    for _name, fig in figures:
        slide = deck.slides.add_slide(blank)
        image = io.BytesIO(_png_bytes(fig))
        picture = slide.shapes.add_picture(image, Emu(0), Emu(0))

        scale = min(
            deck.slide_width / picture.width, deck.slide_height / picture.height
        )
        picture.width = int(picture.width * scale)
        picture.height = int(picture.height * scale)
        picture.left = int((deck.slide_width - picture.width) / 2)
        picture.top = int((deck.slide_height - picture.height) / 2)
        written += 1

    deck.save(str(path))
    return written
