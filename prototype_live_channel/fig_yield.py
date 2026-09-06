"""Yield / pass-fail map -- the one item on FEATURES.md that main never had.

FEATURES.md describes it as computed "live im Browser (JavaScript)". On a live
channel it does not have to be: the threshold is just another query parameter,
so pass/fail and the yield percentage are computed in Python, next to the data,
and the map is re-pushed. No embedded JS, and the same numbers are available to
the exporters.

Deliberately written against the same helpers and conventions as
fig_spatial_map_stack.py, so it behaves like the rest of the stack-level plots.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from app.plotting.utils import find_device_sets, has_valid_data

_DEV_RE = re.compile(r"^([A-Za-z]+)(\d+)$")

# (column, label, is_log, default operator) -- same metrics as the spatial map.
METRICS: list[tuple[str, str, bool, str]] = [
    ("Memory_window", "Memory Window", True, ">="),
    ("R_HRS", "R HRS", True, ">="),
    ("R_LRS", "R LRS", True, "<="),
    ("VSET", "V Set", False, "<="),
    ("V_reset", "V Reset", False, ">="),
    ("I_reset_max", "I Reset Max", True, "<="),
]

PASS_COLOR = "#2e9e5b"
FAIL_COLOR = "#c8493f"


def _parse_device(dev: str) -> tuple[str, int] | None:
    m = _DEV_RE.match(dev)
    return (m.group(1).upper(), int(m.group(2))) if m else None


def device_medians(
    box_table: pd.DataFrame, stack_id: str, devices: list[str], column: str
) -> dict[str, float]:
    """Median of `column` per device -- the quantity the threshold is applied to."""
    out: dict[str, float] = {}
    for device in devices:
        sets = find_device_sets(box_table, device, stack_id=stack_id)
        df_dev = box_table[box_table["source_file"].isin(sets)]
        vals = pd.to_numeric(df_dev.get(column), errors="coerce").dropna().abs()
        if not vals.empty:
            out[device] = float(vals.median())
    return out


def default_threshold(values: dict[str, float]) -> float:
    """Median across devices: a neutral starting point, roughly 50 % yield."""
    return float(np.median(list(values.values()))) if values else 0.0


def build_yield_map(
    box_table: pd.DataFrame,
    stack_id: str,
    devices: list[str],
    column: str,
    label: str,
    is_log: bool,
    operator: str,
    threshold: float | None = None,
) -> go.Figure | None:
    """One pass/fail grid for one metric at one threshold."""
    positions = {d: p for d in devices if (p := _parse_device(d)) is not None}
    if not positions:
        return None

    values = device_medians(box_table, stack_id, devices, column)
    if not values:
        return None
    if threshold is None:
        threshold = default_threshold(values)

    rows = sorted({r for r, _ in positions.values()})
    cols = sorted({c for _, c in positions.values()})
    row_idx = {r: i for i, r in enumerate(rows)}
    col_idx = {c: i for i, c in enumerate(cols)}

    z = np.full((len(rows), len(cols)), np.nan)
    text = np.full((len(rows), len(cols)), "", dtype=object)
    passed = tested = 0

    for device, (r, c) in positions.items():
        if device not in values:
            continue
        value = values[device]
        ok = value >= threshold if operator == ">=" else value <= threshold
        z[row_idx[r], col_idx[c]] = 1.0 if ok else 0.0
        text[row_idx[r], col_idx[c]] = f"{value:.3g}"
        tested += 1
        passed += int(ok)

    if tested == 0:
        return None

    yield_pct = 100.0 * passed / tested
    fig = go.Figure(
        data=go.Heatmap(
            x=[str(c) for c in cols],
            y=rows,
            z=z,
            text=text,
            texttemplate="%{text}",
            textfont={"size": 10},
            colorscale=[[0.0, FAIL_COLOR], [1.0, PASS_COLOR]],
            zmin=0,
            zmax=1,
            showscale=False,
            hoverongaps=False,
            hovertemplate=(
                "Device: %{y}%{x}<br>" + label + ": %{text}"
                "<br>%{customdata}<extra></extra>"
            ),
            customdata=np.where(z == 1, "PASS", "FAIL"),
        )
    )
    fig.update_layout(
        title=(
            f"Stack {stack_id} – Yield – {label} {operator} {threshold:.4g}"
            f"  →  {passed}/{tested} pass ({yield_pct:.1f} %)"
        ),
        width=max(700, len(cols) * 70 + 200),
        height=max(500, len(rows) * 70 + 150),
        template="plotly_white",
        xaxis=dict(title="Column", side="bottom", type="category"),
        yaxis=dict(title="Row", autorange="reversed", type="category"),
        meta={
            "param_id": f"yield_{column}",
            "level": "stack",
            "stack_id": stack_id,
            "yield": {
                "column": column,
                "label": label,
                "is_log": is_log,
                "operator": operator,
                "threshold": threshold,
                "passed": passed,
                "tested": tested,
                "percent": yield_pct,
            },
        },
    )
    return fig


def build_yield_maps(
    box_table: pd.DataFrame, stack_id: str, devices: list[str]
) -> list[go.Figure]:
    """One map per metric, each at its default (median) threshold."""
    if not has_valid_data(box_table, devices):
        return []

    figures = []
    for column, label, is_log, operator in METRICS:
        if column not in box_table.columns:
            continue
        fig = build_yield_map(
            box_table, stack_id, devices, column, label, is_log, operator
        )
        if fig is not None:
            figures.append(fig)
    return figures
