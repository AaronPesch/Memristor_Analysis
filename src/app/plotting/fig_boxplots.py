from __future__ import annotations
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from .utils import gradient_colors, has_valid_data

_TICK_VALS = [10.0**i for i in range(-15, 16)]
_TICK_TEXT = [f"1e{i}" if i != 0 else "1" for i in range(-15, 16)]


def combined_box_fig(
    group_dfs: list[tuple[str, "pd.DataFrame"]],
    all_df: "pd.DataFrame",
    color_map: dict,
    specs: list[tuple[str, str]],
    param_id: str,
    title: str,
    is_log: bool,
    meta_extra: dict | None = None,
) -> go.Figure:
    """Combined boxplot: two parameters (specs) side-by-side, one box per group.

    Each group (device/set) is a single trace spanning both x-categories so that
    boxmode='group' places every group's box side-by-side under each category.
    All values are taken as absolute; log params also drop non-positive values.
    """
    fig = go.Figure()
    all_vals: list[float] = []

    def _series(sub, col):
        v = pd.to_numeric(sub[col], errors="coerce").dropna().abs()
        return v[v > 0] if is_log else v

    for name, sub in group_dfs:
        xs, ys = [], []
        for col, cat in specs:
            v = _series(sub, col)
            ys.extend(v.tolist())
            xs.extend([cat] * len(v))
        if ys:
            all_vals.extend(ys)
        fig.add_trace(
            go.Box(
                y=ys,
                x=xs,
                name=name,
                marker_color=color_map.get(name),
                fillcolor=color_map.get(name),
                line=dict(width=2),
                opacity=0.7,
                boxpoints=False,
                legendgroup=name,
            )
        )

    # Unified "All Data" across every group
    xs, ys = [], []
    for col, cat in specs:
        v = _series(all_df, col)
        ys.extend(v.tolist())
        xs.extend([cat] * len(v))
    if ys:
        all_vals.extend(ys)
        fig.add_trace(
            go.Box(
                y=ys,
                x=xs,
                name="All Data (unified)",
                marker_color="black",
                line=dict(width=2.5, color="black"),
                fillcolor="rgba(0,0,0,0.15)",
                boxpoints=False,
                legendgroup="unified",
            )
        )

    if is_log:
        fig.update_yaxes(
            type="log",
            tickmode="array",
            tickvals=_TICK_VALS,
            ticktext=_TICK_TEXT,
            exponentformat="power",
            showgrid=True,
            gridcolor="#E5E5E5",
            minor=dict(showgrid=False),
            zeroline=False,
            autorange=True,
        )
    else:
        fig.update_yaxes(
            type="linear",
            autorange=True,
            showgrid=True,
            gridcolor="#E5E5E5",
            zeroline=True,
            zerolinecolor="gray",
        )

    fig.update_xaxes(showgrid=True, gridcolor="#E5E5E5")
    fig.update_layout(
        title=title,
        width=900,
        height=600,
        template="plotly_white",
        showlegend=True,
        boxmode="group",
        meta={"param_id": param_id, **(meta_extra or {})},
    )

    if not all_vals:
        fig.add_annotation(
            text="No valid data found",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
        )

    return fig


def build_boxplots_figs(box_table: "pd.DataFrame", sets: list[str]) -> list[go.Figure]:
    """
    Creates a list of boxplot Figure objects, one for each parameter.
    Each figure shows individual boxes per source file PLUS a unified
    'All Data' box aggregating all sets into one dataset.

    - R_LRS, R_HRS, and I_reset_max use Log Scale.
    - Voltages (VSET, V_reset, V_forming) use Linear Scale.
    """
    if not has_valid_data(box_table, sets):
        return []

    param_map = {
        "VSET": {"pretty": "V_set (V)", "scale": "linear"},
        "V_reset": {"pretty": "V_reset (V)", "scale": "linear"},
        "R_LRS": {"pretty": "R_LRS (Ω)", "scale": "log"},
        "R_HRS": {"pretty": "R_HRS (Ω)", "scale": "log"},
        "I_reset_max": {"pretty": "I_reset_max (A)", "scale": "log"},
        "V_forming": {"pretty": "V_forming (V)", "scale": "linear"},
        "I_leakage_pristine": {"pretty": "I_leakage pristine (A)", "scale": "log"},
        "Memory_window": {"pretty": "Memory Window", "scale": "log"},
    }

    cols = gradient_colors(max(len(sets), 1))
    color_map = {s: cols[i] for i, s in enumerate(sets)}

    tick_vals = [10.0**i for i in range(-15, 16)]
    tick_text = [f"1e{i}" if i != 0 else "1" for i in range(-15, 16)]

    figures = []

    for param, info in param_map.items():
        if param not in box_table.columns:
            continue

        fig = go.Figure()
        is_log = info["scale"] == "log"
        has_any_data = False
        all_vals_for_param = []

        # Individual boxes per source file
        for s in sets:
            df_s = box_table[box_table["source_file"] == s]
            vals = pd.to_numeric(df_s[param], errors="coerce").dropna()

            if is_log:
                vals = vals.abs()
                vals = vals[vals > 0]

            if not vals.empty:
                has_any_data = True
                all_vals_for_param.extend(vals.tolist())

            fig.add_trace(
                go.Box(
                    y=vals,
                    name=s,
                    width=0.3,
                    marker_color=color_map.get(s),
                    boxmean=False,
                    line=dict(width=2),
                    fillcolor=color_map.get(s),
                    opacity=0.7,
                    boxpoints=False,
                    legendgroup=s,
                )
            )

        # Unified "All Data" box — all sets combined
        all_vals = pd.to_numeric(box_table[param], errors="coerce").dropna()
        if is_log:
            all_vals = all_vals.abs()
            all_vals = all_vals[all_vals > 0]

        if not all_vals.empty:
            has_any_data = True
            all_vals_for_param.extend(all_vals.tolist())
            fig.add_trace(
                go.Box(
                    y=all_vals,
                    name="All Data (unified)",
                    width=0.3,
                    marker_color="black",
                    boxmean=False,
                    line=dict(width=2.5, color="black"),
                    fillcolor="rgba(0,0,0,0.15)",
                    boxpoints=False,
                    legendgroup="unified",
                )
            )

        if is_log:
            yaxis_config = dict(
                type="log",
                tickmode="array",
                tickvals=tick_vals,
                ticktext=tick_text,
                title_text=f"|{info['pretty']}|",
                exponentformat="power",
                showgrid=True,
                gridcolor="#E5E5E5",
                minor=dict(showgrid=False),
                zeroline=False,
            )

            if all_vals_for_param:
                lmin = np.log10(min(all_vals_for_param))
                lmax = np.log10(max(all_vals_for_param))
                if (lmax - lmin) < 1.0:
                    mid = (lmin + lmax) / 2
                    yaxis_config["range"] = [mid - 0.55, mid + 0.55]
                else:
                    yaxis_config["autorange"] = True

            fig.update_yaxes(**yaxis_config)
        else:
            fig.update_yaxes(
                type="linear",
                title_text=info["pretty"],
                autorange=True,
                showgrid=True,
                gridcolor="#E5E5E5",
                zeroline=True,
                zerolinecolor="gray",
            )

        fig.update_xaxes(
            title_text="Set / File",
            showgrid=True,
            gridcolor="#E5E5E5",
            showticklabels=False,
        )

        fig.update_layout(
            title=f"Boxplot – {info['pretty']} ({info['scale'].capitalize()} Scale)",
            width=max(900, (len(sets) + 1) * 70),
            height=600,
            template="plotly_white",
            showlegend=True,
            boxmode="group",
            boxgap=0.1,
            meta={"param_id": param},
        )

        if not has_any_data:
            fig.add_annotation(
                text="No valid data found",
                xref="paper",
                yref="paper",
                x=0.5,
                y=0.5,
                showarrow=False,
            )

        figures.append(fig)

    # Combined comparison figures (per-set, filterable legend)
    group_dfs = [(s, box_table[box_table["source_file"] == s]) for s in sets]
    if {"VSET", "V_reset"}.issubset(box_table.columns):
        figures.append(
            combined_box_fig(
                group_dfs,
                box_table,
                color_map,
                [("VSET", "V_set"), ("V_reset", "V_reset")],
                "V_set_vs_V_reset",
                "Boxplot – |V_set| vs |V_reset|",
                is_log=False,
            )
        )
    if {"R_HRS", "R_LRS"}.issubset(box_table.columns):
        figures.append(
            combined_box_fig(
                group_dfs,
                box_table,
                color_map,
                [("R_HRS", "R_HRS"), ("R_LRS", "R_LRS")],
                "R_HRS_vs_R_LRS",
                "Boxplot – |R_HRS| vs |R_LRS| (Log Scale)",
                is_log=True,
            )
        )

    return figures
