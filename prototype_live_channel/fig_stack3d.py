"""The stack as a rotatable 3D landscape.

The same per-device medians as the 2D stack map, lifted onto a height axis. As
an analysis tool the flat map is better -- nothing occludes anything and values
are readable. What this adds is a second variable: height and colour can carry
different parameters, which the flat map cannot do, and it photographs well.

Metrics and per-device aggregation come from fig_yield, so the 3D view, the 2D
map and the yield numbers can never drift apart.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go

import fig_yield
from app.plotting.utils import has_valid_data

DEVICE_RE = re.compile(r"^([A-Za-z]+)(\d+)$")

# (column, label, is_log) -- derived from the yield metrics so the two agree.
METRICS = [(c, label, is_log) for c, label, is_log, _op in fig_yield.METRICS]
METRIC_LABELS = {column: label for column, label, _ in METRICS}
DEFAULT_HEIGHT = "Memory_window"

BASE_COLOR = "#8899aa"
STEM_COLOR = "rgba(140,150,165,0.55)"
EMPTY_COLOR = "rgba(140,150,165,0.35)"


def _is_log(column: str) -> bool:
    return next((log for c, _, log in METRICS if c == column), False)


def _positions(devices: list[str]) -> dict[str, tuple[str, int]]:
    out = {}
    for device in devices:
        match = DEVICE_RE.match(device)
        if match:
            out[device] = (match.group(1).upper(), int(match.group(2)))
    return out


def _axis_value(value: float, is_log: bool) -> float | None:
    """Height on the axis: decades for resistances, the value itself otherwise."""
    if value is None or value != value:
        return None
    if is_log:
        return float(np.log10(value)) if value > 0 else None
    return float(value)


def build_stack_3d(
    box_table: pd.DataFrame,
    stack_id: str,
    devices: list[str],
    height: str = DEFAULT_HEIGHT,
    color: str | None = None,
) -> go.Figure | None:
    """One marker per device above its grid position.

    `height` and `color` may name different parameters -- that is the point of
    the view. `color=None` colours by the height metric.
    """
    if not has_valid_data(box_table, devices):
        return None
    if height not in box_table.columns:
        return None
    color = color or height
    if color not in box_table.columns:
        color = height

    positions = _positions(devices)
    if len(positions) < 2:
        return None

    height_values = fig_yield.device_medians(box_table, stack_id, devices, height)
    color_values = fig_yield.device_medians(box_table, stack_id, devices, color)
    height_log, color_log = _is_log(height), _is_log(color)

    placed: list[tuple[str, int, int, float, float]] = []
    for device, (row, col) in positions.items():
        z = _axis_value(height_values.get(device), height_log)
        if z is None:
            continue
        tint = _axis_value(color_values.get(device), color_log)
        placed.append((device, col, row, z, tint if tint is not None else z))
    if not placed:
        return None

    rows = sorted({row for _, _, row, _, _ in placed})
    cols = sorted({col for _, col, _, _, _ in placed})
    row_index = {row: i + 1 for i, row in enumerate(rows)}

    xs = [col for _, col, _, _, _ in placed]
    ys = [row_index[row] for _, _, row, _, _ in placed]
    zs = [z for _, _, _, z, _ in placed]
    tints = [t for _, _, _, _, t in placed]
    names = [d for d, _, _, _, _ in placed]

    span = (max(zs) - min(zs)) or 1.0
    floor = min(zs) - 0.12 * span

    height_label = METRIC_LABELS.get(height, height)
    color_label = METRIC_LABELS.get(color, color)
    height_axis = f"log10({height_label})" if height_log else height_label
    color_axis = f"log10({color_label})" if color_log else color_label

    fig = go.Figure()

    # Base plate: gives the floating markers a die to stand on, and makes the
    # empty grid positions visible.
    fig.add_trace(
        go.Surface(
            x=[min(cols) - 0.6, max(cols) + 0.6],
            y=[0.4, len(rows) + 0.6],
            z=[[floor, floor], [floor, floor]],
            colorscale=[[0, BASE_COLOR], [1, BASE_COLOR]],
            opacity=0.18,
            showscale=False,
            hoverinfo="skip",
            name="die",
        )
    )

    # Grid positions with no device, flat on the plate.
    taken = {(col, row_index[row]) for _, col, row, _, _ in placed}
    empty_x = [c for c in cols for r in range(1, len(rows) + 1) if (c, r) not in taken]
    empty_y = [r for c in cols for r in range(1, len(rows) + 1) if (c, r) not in taken]
    if empty_x:
        fig.add_trace(
            go.Scatter3d(
                x=empty_x,
                y=empty_y,
                z=[floor] * len(empty_x),
                mode="markers",
                marker=dict(size=3, color=EMPTY_COLOR, symbol="square"),
                hoverinfo="skip",
                showlegend=False,
                name="empty",
            )
        )

    # Stems. One trace with None separators rather than 30 traces.
    stem_x: list[float | None] = []
    stem_y: list[float | None] = []
    stem_z: list[float | None] = []
    for x, y, z in zip(xs, ys, zs):
        stem_x += [x, x, None]
        stem_y += [y, y, None]
        stem_z += [floor, z, None]
    fig.add_trace(
        go.Scatter3d(
            x=stem_x,
            y=stem_y,
            z=stem_z,
            mode="lines",
            line=dict(color=STEM_COLOR, width=4),
            hoverinfo="skip",
            showlegend=False,
            name="stems",
        )
    )

    decoupled = color != height
    hover = (
        "%{customdata}<br>"
        + height_label
        + ": %{z:.3f}"
        + (f"<br>{color_label}: %{{marker.color:.3f}}" if decoupled else "")
        + "<extra></extra>"
    )
    fig.add_trace(
        go.Scatter3d(
            x=xs,
            y=ys,
            z=zs,
            mode="markers",
            marker=dict(
                size=9,
                color=tints,
                colorscale="Viridis",
                showscale=True,
                colorbar=dict(
                    title=dict(text=color_axis, font=dict(size=10)), thickness=12
                ),
                line=dict(width=1, color="rgba(0,0,0,0.35)"),
            ),
            customdata=names,
            hovertemplate=hover,
            # The trace name is how a click resolves to a device elsewhere;
            # here customdata carries it per point instead.
            name="devices",
            showlegend=False,
        )
    )

    subtitle = f" · colour: {color_label}" if decoupled else ""
    fig.update_layout(
        title=f"Stack {stack_id} – 3D – height: {height_label}{subtitle}",
        template="plotly_white",
        margin=dict(l=0, r=0, t=46, b=0),
        scene=dict(
            xaxis=dict(title="Column", tickmode="array", tickvals=cols),
            yaxis=dict(
                title="Row",
                tickmode="array",
                tickvals=list(row_index.values()),
                ticktext=rows,
            ),
            zaxis=dict(title=height_axis),
            aspectmode="manual",
            aspectratio=dict(
                x=1.5, y=max(0.6, len(rows) / max(len(cols), 1) * 1.5), z=0.75
            ),
            camera=dict(eye=dict(x=1.6, y=-1.7, z=0.9)),
        ),
        meta={
            "param_id": "stack_3d",
            "level": "stack",
            "stack_id": stack_id,
            "stack3d": {"height": height, "color": color},
        },
    )
    return fig
