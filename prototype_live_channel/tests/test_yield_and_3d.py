"""The yield map, the 3D view, and the overview tile that mirrors them."""

from __future__ import annotations

import pytest

import dashboard_data
import fig_stack3d
import fig_yield


# ── yield map ────────────────────────────────────────────────────────────────


def test_default_threshold_is_the_median(stack_data):
    values = fig_yield.device_medians(
        stack_data.box_table, stack_data.stack_id, stack_data.devices, "Memory_window"
    )
    import numpy as np

    assert fig_yield.default_threshold(values) == pytest.approx(
        float(np.median(list(values.values())))
    )
    assert fig_yield.default_threshold({}) == 0.0


def test_threshold_moves_the_verdict(stack_data):
    kwargs = dict(
        box_table=stack_data.box_table,
        stack_id=stack_data.stack_id,
        devices=stack_data.devices,
        column="Memory_window",
        label="Memory Window",
        is_log=True,
    )
    everything = fig_yield.build_yield_map(**kwargs, operator=">=", threshold=0)
    nothing = fig_yield.build_yield_map(**kwargs, operator=">=", threshold=1e30)

    assert everything.layout.meta["yield"]["percent"] == 100.0
    assert nothing.layout.meta["yield"]["percent"] == 0.0
    assert everything.layout.meta["yield"]["tested"] == len(stack_data.devices)


def test_operator_inverts_the_verdict(stack_data):
    kwargs = dict(
        box_table=stack_data.box_table,
        stack_id=stack_data.stack_id,
        devices=stack_data.devices,
        column="R_LRS",
        label="R LRS",
        is_log=True,
        threshold=0,
    )
    assert (
        fig_yield.build_yield_map(**kwargs, operator=">=").layout.meta["yield"][
            "percent"
        ]
        == 100.0
    )
    assert (
        fig_yield.build_yield_map(**kwargs, operator="<=").layout.meta["yield"][
            "percent"
        ]
        == 0.0
    )


def test_unknown_device_yields_nothing(stack_data):
    assert (
        fig_yield.build_yield_map(
            stack_data.box_table,
            stack_data.stack_id,
            ["ZZ99"],
            "Memory_window",
            "Memory Window",
            True,
            ">=",
        )
        is None
    )


# ── the overview tile must not disagree with the map ─────────────────────────


def test_tile_matches_the_yield_figure(stack_data, stack_categories):
    _data, categories = stack_categories
    yields = next(c for c in categories if c.key.startswith("yield"))
    figure = yields.figures["yield_Memory_window"]
    meta = figure.layout.meta["yield"]

    summary = dashboard_data.build_stack_summary(
        stack_data, stack_data.devices, metric="Memory_window"
    )
    assert summary.passed == meta["passed"]
    assert summary.tested == meta["tested"]
    assert summary.threshold == pytest.approx(meta["threshold"])
    assert summary.percent == pytest.approx(meta["percent"])


def test_tile_takes_the_rule_it_is_handed(stack_data):
    summary = dashboard_data.build_stack_summary(
        stack_data,
        stack_data.devices,
        metric="VSET",
        operator="<=",
        threshold=1e30,
        user_set=True,
    )
    assert summary.metric == "VSET"
    assert summary.operator == "<="
    assert summary.percent == 100.0
    assert summary.user_set is True


def test_tile_marks_a_default_as_a_default(stack_data):
    summary = dashboard_data.build_stack_summary(stack_data, stack_data.devices)
    assert summary.user_set is False
    assert summary.metric == fig_yield.METRICS[0][0]


def test_tile_offers_only_metrics_that_exist(stack_data, stack_categories):
    _data, categories = stack_categories
    available = {
        pid.removeprefix("yield_")
        for c in categories
        if c.key.startswith("yield")
        for pid in c.param_ids
    }
    summary = dashboard_data.build_stack_summary(stack_data, stack_data.devices)
    assert {column for column, _label in summary.options} == available


def test_unknown_metric_is_refused(stack_data):
    assert (
        dashboard_data.build_stack_summary(
            stack_data, stack_data.devices, metric="not_a_column"
        )
        is None
    )


# ── 3D view ──────────────────────────────────────────────────────────────────


def test_3d_has_plate_stems_and_devices(stack_data):
    fig = fig_stack3d.build_stack_3d(
        stack_data.box_table, stack_data.stack_id, stack_data.devices
    )
    types = [t.type for t in fig.data]
    # Plate, stems, devices -- plus a trace for empty grid positions, which a
    # fully populated grid like the fixtures does not have.
    assert types[0] == "surface"
    assert set(types[1:]) == {"scatter3d"}
    assert len(types) in (3, 4)
    markers = fig.data[-1]
    assert len(markers.x) == len(stack_data.devices)
    assert set(markers.customdata) == set(stack_data.devices)
    assert fig.layout.meta["param_id"] == "stack_3d"


def test_3d_height_and_colour_are_independent(stack_data):
    fig = fig_stack3d.build_stack_3d(
        stack_data.box_table,
        stack_data.stack_id,
        stack_data.devices,
        height="R_HRS",
        color="VSET",
    )
    assert fig.layout.meta["stack3d"] == {"height": "R_HRS", "color": "VSET"}
    markers = fig.data[-1]
    assert list(markers.z) != list(markers.marker.color)
    # Height is a decade exponent, colour is volts.
    assert max(markers.z) > 3
    assert max(markers.marker.color) < 5


def test_3d_colour_defaults_to_the_height_metric(stack_data):
    fig = fig_stack3d.build_stack_3d(
        stack_data.box_table, stack_data.stack_id, stack_data.devices, height="R_HRS"
    )
    assert fig.layout.meta["stack3d"] == {"height": "R_HRS", "color": "R_HRS"}
    assert list(fig.data[-1].z) == list(fig.data[-1].marker.color)


def test_3d_needs_at_least_two_placed_devices(stack_data):
    assert (
        fig_stack3d.build_stack_3d(
            stack_data.box_table, stack_data.stack_id, ["Temp_373K"]
        )
        is None
    )
