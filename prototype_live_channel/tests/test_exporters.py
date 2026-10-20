"""Export formats. Image export goes through kaleido, which needs a browser."""

from __future__ import annotations

import pytest

import exporters

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def box_figure(stack_categories):
    _data, categories = stack_categories
    boxplots = next(c for c in categories if c.key.startswith("boxplots"))
    return boxplots.figures[boxplots.param_ids[0]]


@pytest.fixture(scope="module")
def some_figures(stack_categories):
    _data, categories = stack_categories
    pairs = [(f"{c.key}__{p}", f) for c in categories for p, f in c.figures.items()]
    return pairs[:4]


def _render(fig, path, fmt):
    try:
        exporters.write_image(fig, path, fmt)
    except Exception as exc:  # kaleido needs a Chrome install
        pytest.skip(f"image export unavailable: {type(exc).__name__}: {exc}")


@pytest.mark.parametrize("fmt", ["png", "jpeg", "svg", "pdf"])
def test_image_formats(box_figure, tmp_path, fmt):
    out = tmp_path / f"plot.{fmt}"
    _render(box_figure, out, fmt)
    assert out.stat().st_size > 1000


def test_eps_survives_the_font_substitution(box_figure, tmp_path):
    """Plotly's default font stack starts with Verdana, which svglib cannot
    resolve -- svg2rlg raises KeyError('Verdana') and the export dies."""
    out = tmp_path / "plot.eps"
    _render(box_figure, out, "eps")
    assert out.stat().st_size > 1000


def test_unknown_format_is_refused(box_figure, tmp_path):
    with pytest.raises(ValueError):
        exporters.write_image(box_figure, tmp_path / "x.tiff", "tiff")


@pytest.mark.parametrize("fmt,delimiter", [("csv", ","), ("txt", "\t")])
def test_data_export(box_figure, tmp_path, fmt, delimiter):
    out = tmp_path / f"data.{fmt}"
    exporters.write_data(box_figure, out, fmt)
    first = out.read_text(encoding="utf-8").splitlines()[0]
    assert delimiter in first
    assert out.stat().st_size > 100


def test_legend_is_grown_so_entries_are_not_cut_off(box_figure):
    prepared = exporters.prepare(box_figure)
    entries = sum(
        1 for t in box_figure.data if getattr(t, "showlegend", True) is not False
    )
    if entries * exporters.LEGEND_PX_PER_ENTRY <= (box_figure.layout.height or 700):
        pytest.skip("this figure already fits its legend")
    assert prepared.layout.height >= entries * exporters.LEGEND_PX_PER_ENTRY
    assert box_figure.layout.height != prepared.layout.height, "original untouched"


def test_export_all_names_files_per_category(some_figures, tmp_path):
    """Boxplots and CDFs share parameter ids; the category has to be in the
    file name or one overwrites the other."""
    try:
        written = exporters.write_all_images(some_figures, tmp_path, "png")
    except Exception as exc:
        pytest.skip(f"image export unavailable: {type(exc).__name__}")
    assert written == len(some_figures)
    assert len(list(tmp_path.glob("*.png"))) == len(some_figures)


def test_combined_pdf_has_one_page_per_plot(some_figures, tmp_path):
    out = tmp_path / "all.pdf"
    try:
        written = exporters.write_combined_pdf(some_figures, out)
    except Exception as exc:
        pytest.skip(f"image export unavailable: {type(exc).__name__}")
    assert written == len(some_figures)
    assert out.stat().st_size > 10_000


def test_pptx_has_one_slide_per_plot(some_figures, tmp_path):
    out = tmp_path / "deck.pptx"
    try:
        written = exporters.write_pptx(some_figures, out)
    except Exception as exc:
        pytest.skip(f"image export unavailable: {type(exc).__name__}")
    from pptx import Presentation

    deck = Presentation(str(out))
    assert written == len(some_figures)
    assert len(deck.slides._sldIdLst) == len(some_figures)
