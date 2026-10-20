"""A user-chosen range on the axis that carries the measured values.

Which axis that is depends on the plot. Boxplots and correlation scatters put
the value on y, but a CDF puts it on x and keeps cumulative probability on y --
clipping y there would cut the percentage axis, not the data. So the control is
"value axis" rather than "y axis", and this module decides which one that is.

Kept apart from the window so the bounds and the clipping are testable without
a Qt event loop.
"""

from __future__ import annotations

import base64

import numpy as np

# Category key prefix -> the axis carrying the measured value.
VALUE_AXIS = {
    "boxplots": "yaxis",
    "cdfs": "xaxis",
    "correlation_plots": "yaxis",
}


def value_axis(category_key: str) -> str | None:
    """The axis a range applies to, or None where a range makes no sense."""
    for prefix, axis in VALUE_AXIS.items():
        if category_key.startswith(prefix):
            return axis
    return None


def _decode(array) -> list:
    """Plotly may hand arrays back base64-packed."""
    if array is None:
        return []
    if isinstance(array, dict) and "bdata" in array:
        return np.frombuffer(
            base64.b64decode(array["bdata"]), dtype=array["dtype"]
        ).tolist()
    if hasattr(array, "tolist"):
        return array.tolist()
    return list(array)


def data_bounds(fig, axis: str) -> tuple[float, float] | None:
    """The extent of the plotted data along `axis`, so the user knows what to ask
    for. Returns None when the axis carries nothing numeric."""
    attribute = "x" if axis == "xaxis" else "y"
    values: list[float] = []
    for trace in fig.data:
        for item in _decode(getattr(trace, attribute, None)):
            if isinstance(item, (int, float)) and item == item:
                values.append(float(item))
    if not values:
        return None
    return min(values), max(values)


def parse_bounds(low: str, high: str) -> tuple[float, float] | None:
    """Read the two inputs. Raises ValueError with a message fit for the UI."""
    low, high = low.strip().replace(",", "."), high.strip().replace(",", ".")
    if not low and not high:
        return None
    if not low or not high:
        raise ValueError("Enter both a lower and an upper bound.")
    lower, upper = float(low), float(high)
    if lower == upper:
        raise ValueError("Lower and upper bound are the same.")
    return (lower, upper) if lower < upper else (upper, lower)


def apply_range(payload: dict, axis: str, bounds: tuple[float, float] | None) -> dict:
    """Clip one axis of a serialized figure.

    On a log axis Plotly expects the range as decade exponents, not as values --
    handing it raw numbers there silently shows the wrong window. Bounds at or
    below zero cannot be placed on a log axis at all, so the range is dropped
    rather than guessed at.
    """
    if bounds is None:
        return payload

    config = payload.setdefault("layout", {}).setdefault(axis, {})
    lower, upper = bounds

    if config.get("type") == "log":
        if lower <= 0 or upper <= 0:
            return payload
        lower, upper = float(np.log10(lower)), float(np.log10(upper))

    config["range"] = [lower, upper]
    config["autorange"] = False
    return payload


def describe(bounds: tuple[float, float] | None) -> str:
    """The hint shown next to the inputs."""
    if bounds is None:
        return "no numeric data on this axis"
    low, high = bounds
    return f"data spans {_fmt(low)} … {_fmt(high)}"


def _fmt(value: float) -> str:
    if value == 0:
        return "0"
    return f"{value:,.4g}" if 1e-3 <= abs(value) < 1e5 else f"{value:.3e}"
