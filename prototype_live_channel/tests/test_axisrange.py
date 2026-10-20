"""The user-chosen range on the axis that carries the measured values."""

from __future__ import annotations

import pytest

import axisrange


# ── which axis the values are on ─────────────────────────────────────────────


def test_boxplots_and_correlation_carry_the_value_on_y():
    assert axisrange.value_axis("boxplots_stack_level") == "yaxis"
    assert axisrange.value_axis("boxplots") == "yaxis"
    assert axisrange.value_axis("correlation_plots_stack_level") == "yaxis"


def test_a_cdf_carries_the_value_on_x():
    """y is cumulative probability in percent; clipping it would cut the
    percentage axis, not the data."""
    assert axisrange.value_axis("cdfs_stack_level") == "xaxis"
    assert axisrange.value_axis("cdfs") == "xaxis"


def test_plots_without_a_sensible_value_axis():
    for key in (
        "spatial_maps_stack_level",
        "yield_map_stack_level",
        "overview",
        "correlation_matrices",
        "characteristic_plots",
    ):
        assert axisrange.value_axis(key) is None


# ── reading the two inputs ───────────────────────────────────────────────────


def test_both_fields_empty_means_automatic():
    assert axisrange.parse_bounds("", "  ") is None


def test_bounds_are_ordered_for_the_user():
    assert axisrange.parse_bounds("10", "1") == (1.0, 10.0)
    assert axisrange.parse_bounds("1", "10") == (1.0, 10.0)


def test_a_decimal_comma_is_accepted():
    assert axisrange.parse_bounds("0,5", "1,5") == (0.5, 1.5)


def test_scientific_notation_is_accepted():
    assert axisrange.parse_bounds("1e3", "5e6") == (1000.0, 5_000_000.0)


@pytest.mark.parametrize(
    "low,high,message",
    [
        ("1", "", "both"),
        ("", "10", "both"),
        ("5", "5", "same"),
    ],
)
def test_incomplete_or_empty_ranges_are_refused(low, high, message):
    with pytest.raises(ValueError, match=message):
        axisrange.parse_bounds(low, high)


def test_nonsense_is_refused():
    with pytest.raises(ValueError):
        axisrange.parse_bounds("abc", "10")


# ── clipping the figure ──────────────────────────────────────────────────────


def test_range_is_written_to_the_requested_axis():
    payload = {"layout": {}}
    axisrange.apply_range(payload, "yaxis", (1.0, 10.0))
    assert payload["layout"]["yaxis"]["range"] == [1.0, 10.0]
    assert payload["layout"]["yaxis"]["autorange"] is False
    assert "xaxis" not in payload["layout"]


def test_no_range_leaves_the_payload_alone():
    payload = {"layout": {"yaxis": {"type": "log"}}}
    assert axisrange.apply_range(payload, "yaxis", None) == {
        "layout": {"yaxis": {"type": "log"}}
    }


def test_a_log_axis_takes_decade_exponents():
    """Plotly reads a log axis range as exponents. Handing it raw values shows
    a silently wrong window rather than failing."""
    payload = {"layout": {"yaxis": {"type": "log"}}}
    axisrange.apply_range(payload, "yaxis", (1e3, 1e6))
    assert payload["layout"]["yaxis"]["range"] == pytest.approx([3.0, 6.0])


def test_a_log_axis_refuses_bounds_at_or_below_zero():
    payload = {"layout": {"yaxis": {"type": "log"}}}
    axisrange.apply_range(payload, "yaxis", (0.0, 10.0))
    assert "range" not in payload["layout"]["yaxis"]


def test_a_linear_axis_takes_the_values_as_given():
    payload = {"layout": {"yaxis": {"type": "linear"}}}
    axisrange.apply_range(payload, "yaxis", (-2.0, 2.0))
    assert payload["layout"]["yaxis"]["range"] == [-2.0, 2.0]


# ── the hint telling the user what is there ──────────────────────────────────


def test_bounds_of_a_boxplot(stack_categories):
    _data, categories = stack_categories
    boxplots = next(c for c in categories if c.key.startswith("boxplots"))
    fig = boxplots.figures[boxplots.param_ids[0]]

    bounds = axisrange.data_bounds(fig, "yaxis")
    assert bounds is not None
    low, high = bounds
    assert low < high


def test_bounds_of_a_cdf_are_values_not_percentages(stack_categories):
    _data, categories = stack_categories
    cdfs = next(c for c in categories if c.key.startswith("cdfs"))
    fig = cdfs.figures["R_HRS"]

    on_x = axisrange.data_bounds(fig, "xaxis")
    on_y = axisrange.data_bounds(fig, "yaxis")
    assert on_x is not None and on_y is not None
    # y is cumulative probability, so it stays inside 0..100; the resistances
    # on x are orders of magnitude larger.
    assert on_y[1] <= 100.0
    assert on_x[1] > on_y[1]


def test_bounds_report_nothing_for_an_empty_axis():
    class Empty:
        data = ()

    assert axisrange.data_bounds(Empty(), "yaxis") is None
    assert "no numeric data" in axisrange.describe(None)


def test_the_hint_names_both_ends():
    text = axisrange.describe((1234.5, 6.7e8))
    assert "1,234" in text or "1234" in text
    assert "e+08" in text or "670000000" in text
