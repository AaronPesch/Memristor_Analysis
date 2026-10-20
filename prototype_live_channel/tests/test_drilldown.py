"""Resolving a clicked point to a device, highlighting, and the raw sweep."""

from __future__ import annotations

import pytest

import drilldown


@pytest.fixture(scope="module")
def devices(stack_data):
    return list(stack_data.devices)


# ── resolving a click ────────────────────────────────────────────────────────


def test_trace_name_that_is_a_device(devices):
    assert (
        drilldown.resolve_device({"name": devices[0]}, devices, "STACK") == devices[0]
    )


def test_source_file_name_yields_the_device():
    """`<stack_id>_<device>_<NN>_<type>`; a stack id may contain underscores
    itself, which is why this cannot be split in the page."""
    devices = ["C1", "C10"]
    ref = {"name": "T25098_C1_03_endurance_set"}
    assert drilldown.resolve_device(ref, devices, "T25098") == "C1"


def test_stack_id_is_not_mistaken_for_a_device():
    """T25098 matches <letters><digits> but is the stack, not a device."""
    assert drilldown.resolve_device({"name": "T25098"}, ["C1"], "T25098") is None


def test_heatmap_cell_resolves_from_row_and_column():
    assert (
        drilldown.resolve_device({"name": None, "y": "F", "x": "5"}, ["F5"], "S")
        == "F5"
    )


def test_customdata_identifies_a_point_in_a_shared_trace():
    """The 3D view holds every device in one trace."""
    ref = {"name": "devices", "custom": "B2", "x": 1, "y": 1}
    assert drilldown.resolve_device(ref, ["B2"], "S") == "B2"


def test_customdata_is_validated_against_the_known_devices():
    """The yield heatmap carries PASS/FAIL in customdata; it must not become a
    device named PASS."""
    assert drilldown.resolve_device({"custom": "PASS"}, ["B2"], "S") is None


def test_aggregate_traces_belong_to_no_device():
    assert (
        drilldown.resolve_device({"name": "All Devices (unified)"}, ["B2"], "S") is None
    )
    assert drilldown.resolve_device({}, ["B2"], "S") is None


# ── highlighting ─────────────────────────────────────────────────────────────


def test_highlight_dims_everything_outside_the_selection(stack_data, stack_categories):
    _data, categories = stack_categories
    cdf = next(c for c in categories if c.key.startswith("cdfs"))
    key = cdf.param_ids[0]
    fig = cdf.figures[key]

    owners = drilldown.trace_devices(fig, stack_data.devices, stack_data.stack_id)
    owned = [o for o in owners if o]
    assert owned, "the CDF names its traces after devices"

    payload = {"data": [{} for _ in fig.data]}
    drilldown.apply_highlight(payload, owners, {owned[0]})
    dimmed = [t for t in payload["data"] if t.get("opacity") == drilldown.DIM_OPACITY]
    assert len(dimmed) == len(owned) - 1


def test_highlight_leaves_unowned_traces_alone(stack_data, stack_categories):
    """An aggregate curve belongs to no device and should stay readable."""
    _data, categories = stack_categories
    cdf = next(c for c in categories if c.key.startswith("cdfs"))
    fig = cdf.figures[cdf.param_ids[0]]
    owners = drilldown.trace_devices(fig, stack_data.devices, stack_data.stack_id)
    if all(owners):
        pytest.skip("this figure has no aggregate trace")

    payload = {"data": [{} for _ in fig.data]}
    drilldown.apply_highlight(payload, owners, {next(o for o in owners if o)})
    for trace, owner in zip(payload["data"], owners):
        if owner is None:
            assert "opacity" not in trace


def test_empty_selection_changes_nothing():
    payload = {"data": [{}, {}]}
    assert drilldown.apply_highlight(payload, ["A1", "A2"], set()) == {"data": [{}, {}]}


def test_highlight_does_not_touch_the_stored_figure(stack_data, stack_categories):
    """Exports must keep seeing what the builders produced."""
    _data, categories = stack_categories
    cdf = next(c for c in categories if c.key.startswith("cdfs"))
    fig = cdf.figures[cdf.param_ids[0]]
    before = [getattr(t, "opacity", None) for t in fig.data]

    owners = drilldown.trace_devices(fig, stack_data.devices, stack_data.stack_id)
    payload = {"data": [{} for _ in fig.data]}
    drilldown.apply_highlight(payload, owners, {next(o for o in owners if o)})

    assert [getattr(t, "opacity", None) for t in fig.data] == before


# ── the raw sweep behind an aggregate point ──────────────────────────────────


def test_drill_down_builds_the_characteristic(stack_data):
    device = stack_data.devices[0]
    fig, label = drilldown.build_drill_figure(stack_data, device)
    assert fig is not None
    assert device in label
    assert len(fig.data) > 0


def test_drill_down_to_a_single_cycle(stack_data):
    device = stack_data.devices[0]
    sets = drilldown.sets_of_device(stack_data, device)
    frame = stack_data.raw_characteristic[sets[0]]
    cycle = int(frame["cycle_number"].iloc[0])

    whole, _ = drilldown.build_drill_figure(stack_data, device)
    single, label = drilldown.build_drill_figure(stack_data, device, cycle)
    assert single is not None
    assert len(single.data) < len(whole.data)
    assert f"cycle {cycle}" in label


def test_unknown_device_reports_instead_of_raising(stack_data):
    fig, message = drilldown.build_drill_figure(stack_data, "ZZ99")
    assert fig is None
    assert "ZZ99" in message


def test_cycle_without_data_reports(stack_data):
    fig, message = drilldown.build_drill_figure(
        stack_data, stack_data.devices[0], 99999
    )
    assert fig is None
    assert "99999" in message
