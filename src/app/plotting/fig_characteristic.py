from __future__ import annotations
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from .utils import gradient_colors, _RESET_LOW, _RESET_HIGH



def build_characteristic_figs(
    raw_by_set: dict[str, "pd.DataFrame"],
    sets: list[str],
    raw_by_reset: dict[str, "pd.DataFrame"] | None = None,
) -> list[go.Figure]:
    """
    Creates three figures:
    1. AI (Current) vs AV - Log Scale - includes both set AND reset data
    2. NORM_COND (Normalized Conductance G/G0) vs AV - Linear Scale
    3. Butterfly Curve - |I| vs V - true autoscale & vline = 0
    """
    if not sets:
        return []

    if raw_by_reset is None:
        raw_by_reset = {}

    set_cols = gradient_colors(max(len(sets), 1))
    set_color_map = {s: set_cols[i] for i, s in enumerate(sets)}

    all_reset_keys = list(raw_by_reset.keys())
    reset_cols = gradient_colors(max(len(all_reset_keys), 1), low=_RESET_LOW, high=_RESET_HIGH)
    reset_color_map = {s: reset_cols[i] for i, s in enumerate(all_reset_keys)}

    tick_vals = [10.0**i for i in range(-15, 1)]
    tick_text = [f"1e{i}" if i != 0 else "1" for i in range(-15, 1)]

    figures = []

    # ── Fig 1: |Current| vs V (set + reset) ────────────────────────────────
    fig1 = go.Figure()
    all_y_vals_1 = []

    # Set data
    for s in sets:
        df = raw_by_set[s]
        cycles = df["cycle_number"].unique()
        color = set_color_map[s]

        for idx, cyc in enumerate(cycles):
            tiny = df[df["cycle_number"] == cyc]
            y_vals = pd.to_numeric(tiny["AI"], errors="coerce").abs()
            all_y_vals_1.extend(y_vals[y_vals > 0].tolist())

            fig1.add_trace(
                go.Scatter(
                    x=tiny["AV"],
                    y=y_vals,
                    mode="lines",
                    line=dict(color=color, width=1.2),
                    opacity=0.5,
                    name=f"{s} (set)",
                    legendgroup=s,
                    showlegend=(idx == 0),
                    hovertemplate=f"Set: {s}<br>Cycle: {cyc}<br>V: %{{x}}V<br>I: %{{y}}<extra></extra>",
                )
            )

    # Reset data
    for s, df_reset in raw_by_reset.items():
        if df_reset.empty:
            continue
        cycles = df_reset["cycle_number"].unique()
        color = reset_color_map.get(s, "#888888")

        for idx, cyc in enumerate(cycles):
            tiny = df_reset[df_reset["cycle_number"] == cyc]
            y_vals = pd.to_numeric(tiny["AI"], errors="coerce").abs()
            all_y_vals_1.extend(y_vals[y_vals > 0].tolist())

            fig1.add_trace(
                go.Scatter(
                    x=tiny["AV"],
                    y=y_vals,
                    mode="lines",
                    line=dict(color=color, width=1.2, dash="dot"),
                    opacity=0.5,
                    name=f"{s} (reset)",
                    legendgroup=f"{s}_reset",
                    showlegend=(idx == 0),
                    hovertemplate=f"Reset: {s}<br>Cycle: {cyc}<br>V: %{{x}}V<br>I: %{{y}}<extra></extra>",
                )
            )

    fig1.update_xaxes(
        title_text="Voltage (V)",
        autorange=True,
        gridcolor="#E5E5E5",
        zeroline=True,
        zerolinecolor="gray",
    )

    yaxis_config_1 = dict(
        type="log",
        tickmode="array",
        tickvals=tick_vals,
        ticktext=tick_text,
        exponentformat="power",
        gridcolor="#E5E5E5",
        minor=dict(showgrid=False),
        title_text="|Current (A)|",
    )
    if all_y_vals_1:
        lmin, lmax = np.log10(min(all_y_vals_1)), np.log10(max(all_y_vals_1))
        if (lmax - lmin) < 1.0:
            mid = (lmin + lmax) / 2
            yaxis_config_1["range"] = [mid - 0.55, mid + 0.55]
    fig1.update_yaxes(**yaxis_config_1)

    fig1.update_layout(
        title="Characteristic Plot – |Current| vs V (Set + Reset)",
        width=1000,
        height=700,
        template="plotly_white",
        legend=dict(groupclick="toggleitem", title="Files"),
        meta={"param_id": "AI"},
    )
    figures.append(fig1)

    # ── Fig 2: Normalized Conductance (G/G0) vs V (set + reset) ─────────────
    fig2 = go.Figure()

    for s in sets:
        df = raw_by_set[s]
        cycles = df["cycle_number"].unique()
        color = set_color_map[s]

        for idx, cyc in enumerate(cycles):
            tiny = df[df["cycle_number"] == cyc]
            y_vals = pd.to_numeric(tiny["NORM_COND"], errors="coerce")

            fig2.add_trace(
                go.Scatter(
                    x=tiny["AV"],
                    y=y_vals,
                    mode="lines",
                    line=dict(color=color, width=1.2),
                    opacity=0.5,
                    name=f"{s} (set)",
                    legendgroup=s,
                    showlegend=(idx == 0),
                    hovertemplate=f"Set: {s}<br>Cycle: {cyc}<br>V: %{{x}}V<br>G/G₀: %{{y:.3f}}<extra></extra>",
                )
            )

    for s, df_reset in raw_by_reset.items():
        if df_reset.empty:
            continue
        cycles = df_reset["cycle_number"].unique()
        color = reset_color_map.get(s, "#888888")

        for idx, cyc in enumerate(cycles):
            tiny = df_reset[df_reset["cycle_number"] == cyc]
            y_vals = pd.to_numeric(tiny["NORM_COND"], errors="coerce")
            x_vals = tiny["AV"]

            fig2.add_trace(
                go.Scatter(
                    x=x_vals,
                    y=y_vals,
                    mode="lines",
                    line=dict(color=color, width=1.2, dash="dot"),
                    opacity=0.5,
                    name=f"{s} (reset)",
                    legendgroup=f"{s}_reset",
                    showlegend=(idx == 0),
                    hovertemplate=f"Reset: {s}<br>Cycle: {cyc}<br>V: %{{x}}V<br>G/G₀: %{{y:.3f}}<extra></extra>",
                )
            )

    fig2.add_vline(x=0, line_width=2, line_color="black")

    fig2.update_xaxes(
        title_text="Voltage (V)",
        autorange=True,
        gridcolor="#E5E5E5",
        zeroline=True,
        zerolinecolor="black",
        zerolinewidth=2,
    )
    fig2.update_yaxes(
        type="linear",
        title_text="Normalized conductance (G/G₀)",
        gridcolor="#E5E5E5",
        zeroline=True,
        zerolinecolor="gray",
        autorange=True,
    )
    fig2.update_layout(
        title="Characteristic Plot – Normalized Conductance (G/G₀) vs V (Set + Reset)",
        width=1000,
        height=700,
        template="plotly_white",
        legend=dict(groupclick="toggleitem", title="Files"),
        meta={"param_id": "NORM_COND"},
    )
    figures.append(fig2)

    # ── Fig 3: Butterfly Curve ──────────────────────────────────────────────
    fig_butterfly = go.Figure()
    all_i_vals = []

    for s in sets:
        df = raw_by_set[s]
        cycles = df["cycle_number"].unique()
        color = set_color_map[s]

        for idx, cyc in enumerate(cycles):
            tiny = df[df["cycle_number"] == cyc]

            av = pd.to_numeric(tiny["AV"], errors="coerce")
            ai = pd.to_numeric(tiny["AI"], errors="coerce").abs()

            valid = ai > 0
            av_valid = av[valid]
            ai_valid = ai[valid]

            all_i_vals.extend(ai_valid.tolist())

            fig_butterfly.add_trace(
                go.Scatter(
                    x=av_valid,
                    y=ai_valid,
                    mode="lines",
                    line=dict(color=color, width=1.2),
                    opacity=0.5,
                    name=s,
                    legendgroup=s,
                    showlegend=(idx == 0),
                    hovertemplate=f"Set: {s}<br>Cycle: {cyc}<br>V: %{{x}}V<br>|I|: %{{y}}<extra></extra>",
                )
            )

    yaxis_config_butterfly = dict(
        type="log",
        tickmode="array",
        tickvals=tick_vals,
        ticktext=tick_text,
        exponentformat="power",
        gridcolor="#E5E5E5",
        minor=dict(showgrid=False),
        title_text="|Imeas (A)|",
    )
    if all_i_vals:
        lmin, lmax = np.log10(min(all_i_vals)), np.log10(max(all_i_vals))
        if (lmax - lmin) < 1.0:
            mid = (lmin + lmax) / 2
            yaxis_config_butterfly["range"] = [mid - 0.55, mid + 0.55]
    fig_butterfly.update_yaxes(**yaxis_config_butterfly)

    fig_butterfly.update_xaxes(
        title_text="Vforce (V)",
        gridcolor="#E5E5E5",
        zeroline=True,
        zerolinecolor="black",
        zerolinewidth=2,
        autorange=True,
    )

    fig_butterfly.add_vline(x=0, line_width=2, line_color="black")

    fig_butterfly.update_layout(
        title="Butterfly Curve – |I| vs V (All Sets)",
        width=1000,
        height=700,
        template="plotly_white",
        legend=dict(groupclick="toggleitem", title="Files"),
        meta={"param_id": "butterfly_curve"},
    )
    figures.append(fig_butterfly)

    return figures
