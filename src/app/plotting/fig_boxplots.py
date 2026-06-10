from __future__ import annotations
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from .utils import gradient_colors, has_valid_data


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
            width=900,
            height=600,
            template="plotly_white",
            showlegend=True,
            boxmode="group",
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

    return figures
