"""The live channel: a window, a page, and figures travelling between them.

Marked `gui` -- these build a real QWebEngineView. Deselect with
`-m "not gui"` where no display or Chromium sandbox is available.
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.gui

from app.core.modes import Mode  # noqa: E402


@pytest.fixture
def window(qtbot, stack_db, monkeypatch, tmp_path):
    """A window whose page has finished loading, with no data imported yet."""
    import analysis_app
    import channel

    monkeypatch.setattr(channel, "DB_FILE", stack_db)
    channel.export_static_assets()

    win = analysis_app.AnalysisWindow()
    qtbot.addWidget(win)
    win.show()

    loaded = []
    win.view.loadFinished.connect(loaded.append)
    try:
        qtbot.waitUntil(lambda: bool(loaded), timeout=30_000)
    except Exception:  # pragma: no cover - environment without a web view
        pytest.skip("the web view did not load in this environment")
    if not loaded[0]:
        pytest.skip("the web view reported a failed load")
    return win


def run_js(qtbot, win, script):
    """runJavaScript is asynchronous; wait for the answer."""
    box = []
    win.view.page().runJavaScript(script, box.append)
    qtbot.waitUntil(lambda: bool(box), timeout=15_000)
    return box[0]


@pytest.fixture
def categories_copy(stack_categories):
    """A private copy of the session categories.

    The window mutates them -- on_yield_changed replaces a figure -- and a
    session fixture handed out by reference would leak that into every later
    test."""
    import live_pipeline

    data, categories = stack_categories
    return data, [
        live_pipeline.Category(key=c.key, label=c.label, figures=dict(c.figures))
        for c in categories
    ]


def feed(win, data, categories, overview=None):
    win.on_import_done(Mode.STACK, data, categories, overview)


# ── the page before anything is imported ─────────────────────────────────────


def test_placeholder_until_data_arrives(qtbot, window):
    state = json.loads(
        run_js(
            qtbot,
            window,
            "JSON.stringify({ph: document.getElementById('placeholder').style.display,"
            " plots: document.querySelectorAll('.js-plotly-plot').length})",
        )
    )
    assert state["ph"] != "none"
    assert state["plots"] == 0


def test_bridge_is_reachable_from_the_page(qtbot, window):
    kinds = json.loads(
        run_js(
            qtbot,
            window,
            "JSON.stringify({channel: typeof QWebChannel, bridge: typeof bridge,"
            " plotly: typeof Plotly})",
        )
    )
    assert kinds == {"channel": "function", "bridge": "object", "plotly": "object"}


# ── figures reaching the page ────────────────────────────────────────────────


def test_a_figure_is_drawn_and_keeps_its_zoom_key(qtbot, window, categories_copy):
    data, categories = categories_copy
    feed(window, data, categories)
    qtbot.wait(1200)

    state = json.loads(
        run_js(
            qtbot,
            window,
            "JSON.stringify({plots: document.querySelectorAll('.js-plotly-plot').length,"
            " traces: (document.getElementById('plot').data||[]).length,"
            " uirev: (document.getElementById('plot').layout||{}).uirevision})",
        )
    )
    assert state["plots"] == 1
    assert state["traces"] > 0
    # Without a stable uirevision, Plotly.react throws away the user's zoom.
    assert state["uirev"]


def test_switching_tabs_swaps_the_figure(qtbot, window, categories_copy):
    data, categories = categories_copy
    feed(window, data, categories)
    qtbot.wait(900)

    first = run_js(
        qtbot, window, "(document.getElementById('plot').layout||{}).uirevision"
    )
    window.category_bar.setCurrentIndex(window.category_bar.count() - 1)
    qtbot.wait(900)
    second = run_js(
        qtbot, window, "(document.getElementById('plot').layout||{}).uirevision"
    )
    assert first != second


def test_dark_mode_reaches_every_surface(qtbot, window, categories_copy):
    data, categories = categories_copy
    feed(window, data, categories)
    qtbot.wait(900)

    window.dark_box.setChecked(True)
    qtbot.wait(700)
    assert window.view.page().backgroundColor().name() == "#1e1e1e"
    paper = run_js(
        qtbot, window, "(document.getElementById('plot').layout||{}).paper_bgcolor"
    )
    assert paper == "#1e1e1e"

    window.dark_box.setChecked(False)
    qtbot.wait(700)
    assert window.view.page().backgroundColor().name() == "#ffffff"


# ── the page talking back ────────────────────────────────────────────────────


def test_selection_travels_from_the_page_to_python(window, categories_copy):
    data, categories = categories_copy
    feed(window, data, categories)
    device = data.devices[0]

    answer = json.loads(
        window.bridge.event(
            json.dumps({"kind": "toggle_device", "point": {"name": device}})
        )
    )
    assert window.selection == {device}
    assert answer["figure"] is not None

    window.bridge.event(json.dumps({"kind": "clear_selection"}))
    assert window.selection == set()


def test_drill_down_over_the_bridge(window, categories_copy):
    data, categories = categories_copy
    feed(window, data, categories)
    device = data.devices[0]

    answer = json.loads(
        window.bridge.event(json.dumps({"kind": "drill", "point": {"name": device}}))
    )
    assert window.drill is not None
    assert answer["key"].startswith("drill/")

    window.leave_drill()
    assert window.drill is None


def test_goto_jumps_to_a_category(window, categories_copy):
    data, categories = categories_copy
    feed(window, data, categories)

    window.bridge.event(
        json.dumps({"kind": "goto", "category": "yield_map_stack_level"})
    )
    assert window.category.key == "yield_map_stack_level"

    window.bridge.event(json.dumps({"kind": "goto", "category": "nope"}))
    assert "No tab" in window.statusBar().currentMessage()


# ── the overview tab ─────────────────────────────────────────────────────────


def test_overview_is_the_landing_tab(
    qtbot, window, categories_copy, stack_db, synthetic_stack
):
    import dashboard_data

    data, categories = categories_copy
    overview = dashboard_data.collect(data, stack_db, synthetic_stack, "stack")
    feed(window, data, categories, overview)

    assert window.category_bar.tabText(0) == "Overview"
    assert window.category_bar.currentIndex() == 0
    assert window.sub_bar.count() == 0

    qtbot.wait(1200)
    state = json.loads(
        run_js(
            qtbot,
            window,
            "JSON.stringify({panel: getComputedStyle(document.getElementById('panel')).display,"
            " plot: getComputedStyle(document.getElementById('plot')).display,"
            " tiles: document.querySelectorAll('#panel .tile').length})",
        )
    )
    assert state["panel"] == "block"
    assert state["plot"] == "none"
    assert state["tiles"] == 5


def test_overview_tile_follows_the_yield_map(
    window, categories_copy, stack_db, synthetic_stack
):
    import dashboard_data

    data, categories = categories_copy
    overview = dashboard_data.collect(data, stack_db, synthetic_stack, "stack")
    feed(window, data, categories, overview)

    keys = [c.key for c in window.categories]
    yield_index = keys.index("yield_map_stack_level")
    window.category_bar.setCurrentIndex(yield_index)
    ids = window.categories[yield_index].param_ids
    window.sub_bar.setCurrentIndex(ids.index("yield_Memory_window"))

    window.op_box.setCurrentText(">=")
    window.threshold_edit.setText("0")
    window.on_yield_changed()

    window.category_bar.setCurrentIndex(0)
    window.current_payload()
    tile = window.overview.stack
    assert tile.threshold == pytest.approx(0)
    assert tile.percent == 100.0
    assert tile.user_set is True


# ── the import worker ────────────────────────────────────────────────────────


def test_import_through_the_worker_thread(qtbot, window, synthetic_stack):
    """The handler must run on the main thread.

    Connecting `finished` to a lambda made Qt fall back to a direct connection,
    so the handler ran on the worker thread and _stop_thread()'s wait()
    deadlocked on the thread calling it.
    """
    window.start_import(Mode.STACK, folder=str(synthetic_stack))
    assert window._loading is True

    qtbot.waitUntil(lambda: window.data is not None, timeout=180_000)

    assert window._loading is False
    assert window.thread is None, "the worker thread was torn down"
    assert window.overview is not None
    assert window.category_bar.tabText(0) == "Overview"
