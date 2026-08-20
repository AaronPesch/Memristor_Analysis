from __future__ import annotations
import re
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from .utils import has_valid_data, find_device_sets

_DEV_RE = re.compile(r"^([A-Za-z]+)(\d+)$")

# (column, label, is_log)
_METRICS = [
    ("VSET", "V Set", False),
    ("V_reset", "V Reset", False),
    ("R_HRS", "R HRS", True),
    ("R_LRS", "R LRS", True),
    ("Memory_window", "Memory Window", True),
    ("I_reset_max", "I Reset Max", True),
]


def _parse_device(dev: str) -> tuple[str, int] | None:
    """Parse a device string like 'B12' into ('B', 12)."""
    m = _DEV_RE.match(dev)
    if not m:
        return None
    return m.group(1).upper(), int(m.group(2))


def build_stack_level_spatial_maps(
    box_table: pd.DataFrame,
    stack_id: str,
    devices: list[str],
) -> list[go.Figure]:
    """
    Stack-level spatial maps: one grid heatmap per metric, each device placed at
    its (row letter, column number) position and colored by the median of the
    metric across that device's cycles (absolute value; log metrics drop <= 0).
    """
    if not has_valid_data(box_table, devices):
        return []

    # Parse device positions
    positions: dict[str, tuple[str, int]] = {}
    for device in devices:
        pos = _parse_device(device)
        if pos is not None:
            positions[device] = pos

    if not positions:
        return []

    rows = sorted({r for r, _ in positions.values()})
    cols = sorted({c for _, c in positions.values()})
    row_idx = {r: i for i, r in enumerate(rows)}
    col_idx = {c: i for i, c in enumerate(cols)}

    figures = []

    for col, label, is_log in _METRICS:
        if col not in box_table.columns:
            continue

        # Aggregate median metric per device
        value = np.full((len(rows), len(cols)), np.nan)
        has_any = False

        for device, (r, c) in positions.items():
            device_sets = find_device_sets(box_table, device, stack_id=stack_id)
            df_dev = box_table[box_table["source_file"].isin(device_sets)]
            vals = pd.to_numeric(df_dev[col], errors="coerce").dropna().abs()
            if is_log:
                vals = vals[vals > 0]
            if vals.empty:
                continue
            value[row_idx[r], col_idx[c]] = float(vals.median())
            has_any = True

        if not has_any:
            continue

        # Color by log10 for log metrics; show real values as text/hover
        if is_log:
            with np.errstate(divide="ignore", invalid="ignore"):
                z_color = np.log10(value)
            colorbar_title = f"log10({label})"
        else:
            z_color = value
            colorbar_title = label

        text = np.where(
            np.isnan(value),
            "",
            np.vectorize(lambda v: "" if np.isnan(v) else f"{v:.3g}")(value),
        )

        fig = go.Figure(
            data=go.Heatmap(
                x=[str(c) for c in cols],
                y=rows,
                z=z_color,
                text=text,
                texttemplate="%{text}",
                textfont={"size": 10},
                colorscale="Viridis",
                colorbar=dict(title=colorbar_title),
                hoverongaps=False,
                hovertemplate=(
                    "Device: %{y}%{x}<br>Row: %{y}<br>Col: %{x}"
                    "<br>Value: %{text}<extra></extra>"
                ),
            )
        )
        fig.update_layout(
            title=f"Stack {stack_id} – Spatial Map – {label}",
            width=max(700, len(cols) * 70 + 200),
            height=max(500, len(rows) * 70 + 150),
            template="plotly_white",
            xaxis=dict(title="Column", side="bottom", type="category"),
            yaxis=dict(title="Row", autorange="reversed", type="category"),
            meta={"param_id": f"spatial_{col}", "level": "stack", "stack_id": stack_id},
        )
        figures.append(fig)

    return figures
