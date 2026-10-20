"""The import and the figure builders, without touching the file system."""

from __future__ import annotations

import pytest


def test_import_produces_a_cycles_table(stack_db):
    import duckdb

    with duckdb.connect(str(stack_db), read_only=True) as conn:
        tables = {r[0] for r in conn.execute("SHOW TABLES").fetchall()}
        rows = conn.execute("SELECT count(*) FROM cycles").fetchone()[0]
    assert "cycles" in tables
    assert rows > 0


def test_devices_and_sets_are_discovered(stack_data):
    assert stack_data.stack_id
    assert len(stack_data.devices) == 16
    assert len(stack_data.sets) == 16
    assert stack_data.v_read == pytest.approx(0.2, abs=1e-6)


def test_stack_categories_are_built(stack_categories):
    _data, categories = stack_categories
    labels = [c.label for c in categories]
    assert labels == [
        "Boxplots",
        "CDF",
        "Correlation",
        "Correlation Matrix",
        "Stack Map",
        "Yield Map",
    ]
    assert all(c.figures for c in categories)


def test_every_figure_is_keyed_by_its_param_id(stack_categories):
    _data, categories = stack_categories
    for category in categories:
        for param_id, fig in category.figures.items():
            assert (fig.layout.meta or {}).get("param_id") == param_id


def test_pipeline_writes_no_files(stack_categories, tmp_path):
    """The whole point of live_pipeline: figures come back, nothing is written."""
    import live_pipeline
    from app.core.modes import Mode
    from app.plotting.config import Config

    before = set(tmp_path.rglob("*"))
    data, _categories = stack_categories
    cfg = Config(
        db_file=tmp_path / "unused.duckdb", output_dir=tmp_path, mode=Mode.STACK
    )
    live_pipeline.build_categories(cfg, data)
    assert set(tmp_path.rglob("*")) == before
