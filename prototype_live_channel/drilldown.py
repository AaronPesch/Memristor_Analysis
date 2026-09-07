"""Selection highlighting and drill-down from an aggregate to the raw sweep.

Both work by reading what the existing builders already put on their traces:
on stack level every trace is named after its device, and on device level after
its source file, from which the device is recoverable. Nothing in
`src/app/plotting` had to change.
"""

from __future__ import annotations

import plotly.graph_objects as go

from app.plotting.fig_characteristic import build_characteristic_figs
from app.plotting.transforms import _device_from_source

DIM_OPACITY = 0.12


def device_of_trace(trace, devices: set[str], stack_id: str) -> str | None:
    """Which device does this trace belong to?

    Stack-level figures name traces after the device directly; device-level
    figures name them after the source file, e.g. T25098_C1_03_endurance_set.
    """
    name = getattr(trace, "name", None)
    if not name:
        return None
    if name in devices:
        return name
    device = _device_from_source(name, stack_id)
    return device if device in devices else None


def trace_devices(
    fig: go.Figure, devices: list[str], stack_id: str
) -> list[str | None]:
    known = set(devices)
    return [device_of_trace(t, known, stack_id) for t in fig.data]


def resolve_device(ref: dict, devices: list[str], stack_id: str) -> str | None:
    """Turn a clicked point into a device id.

    Resolution lives here rather than in the page because only this side knows
    the device list and the stack id. A source file is named
    `<stack_id>_<device>_<NN>_<type>`, and a stack id may itself contain
    underscores (h25096_b1), so pattern-matching the name in JavaScript picks
    the wrong segment -- it matched the stack id T25098 before the device C1.
    """
    known = set(devices)

    name = ref.get("name")
    if isinstance(name, str) and name:
        if name in known:
            return name
        device = _device_from_source(name, stack_id)
        if device in known:
            return device

    # Heatmap cell: row letter on y, column number on x.
    row, col = ref.get("y"), ref.get("x")
    if isinstance(row, str) and row.isalpha() and col is not None:
        candidate = f"{row}{col}".replace(".0", "")
        if candidate in known:
            return candidate
    return None


def apply_highlight(
    payload: dict, owners: list[str | None], selection: set[str]
) -> dict:
    """Dim every trace that does not belong to the selection.

    Applied to the serialized payload, so the stored figure is untouched and the
    exporters keep seeing what the builders produced. No rebuild is involved,
    which is what makes this instant across every tab.
    """
    if not selection:
        return payload
    for trace, owner in zip(payload.get("data", []), owners):
        if owner is not None and owner not in selection:
            trace["opacity"] = DIM_OPACITY
            trace["showlegend"] = False
    return payload


def sets_of_device(data, device: str) -> list[str]:
    """The endurance-set source files belonging to one device."""
    return [s for s in data.sets if _device_from_source(s, data.stack_id) == device]


def resets_of_device(data, device: str) -> list[str]:
    return [s for s in data.resets if _device_from_source(s, data.stack_id) == device]


def build_drill_figure(
    data, device: str, cycle: int | None = None
) -> tuple[go.Figure | None, str]:
    """The |Current| vs Voltage sweep behind an aggregate point.

    Reuses `build_characteristic_figs` -- the same builder, the same styling,
    just handed a filtered slice of the raw data it already holds in memory.
    Returns (figure, label); the figure is None when the device has no sweeps.
    """
    sets = sets_of_device(data, device)
    if not sets:
        return None, f"{device}: no endurance-set data"

    raw_by_set = {}
    for source in sets:
        frame = data.raw_characteristic.get(source)
        if frame is None or frame.empty:
            continue
        if cycle is not None:
            frame = frame[frame["cycle_number"] == cycle]
            if frame.empty:
                continue
        raw_by_set[source] = frame

    if not raw_by_set:
        where = f"cycle {cycle}" if cycle is not None else "any cycle"
        return None, f"{device}: no sweep data for {where}"

    raw_by_reset = {}
    for source in resets_of_device(data, device):
        frame = data.raw_reset.get(source)
        if frame is None or frame.empty:
            continue
        if cycle is not None:
            frame = frame[frame["cycle_number"] == cycle]
            if frame.empty:
                continue
        raw_by_reset[source] = frame

    figures = build_characteristic_figs(
        raw_by_set, list(raw_by_set), raw_by_reset=raw_by_reset
    )
    current = next(
        (f for f in figures if (f.layout.meta or {}).get("param_id") == "AI"), None
    )
    if current is None:
        return None, f"{device}: characteristic plot unavailable"

    suffix = f", cycle {cycle}" if cycle is not None else f", {len(raw_by_set)} set(s)"
    title = f"{device}{suffix} - |Current| vs Voltage"
    current.update_layout(title=dict(text=title))
    return current, title
