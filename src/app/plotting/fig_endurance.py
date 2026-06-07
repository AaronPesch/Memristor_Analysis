from __future__ import annotations
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from .utils import gradient_colors, has_valid_data


def build_endurance_figs(end_df: "pd.DataFrame", sets: list[str]) -> list[go.Figure]:
    """
    Creates a list of Endurance Figures (one per parameter).
    """
    if not has_valid_data(end_df, sets):
        return []

    param_map = {
        "V_set": {"pretty": "V_set (V)", "scale": "linear"},
        "V_reset": {"pretty": "V_reset (V)", "scale": "linear"},
        "I_LRS": {"pretty": "I_LRS (A)", "scale": "log"},
        "I_HRS": {"pretty": "I_HRS (A)", "scale": "log"},
        "R_LRS": {"pretty": "R_LRS (Ω)", "scale": "log"},
        "R_HRS": {"pretty": "R_HRS (Ω)", "scale": "log"},
        "I_reset_max": {"pretty": "I_reset_max (A)", "scale": "log"},
        "Memory_window": {"pretty": "Memory Window (Ω)", "scale": "log"},
    }

    cols = gradient_colors(max(len(sets), 1))
    color_map = {s: cols[i] for i, s in enumerate(sets)}

    tick_vals = [10.0**i for i in range(-15, 16)]
    tick_text = [f"1e{i}" if i != 0 else "1" for i in range(-15, 16)]

    figures = []

    for param, info in param_map.items():
        if param not in end_df.columns:
            continue

        fig = go.Figure()
        is_log = info["scale"] == "log"
        has_any_data = False
        all_y_vals = []

        for s in sets:
            df_s = end_df[end_df["source_file"] == s].copy()
            if df_s.empty:
                continue

            x = df_s["cycle_number"]
            y = pd.to_numeric(df_s[param], errors="coerce")

            if is_log:
                y = y.abs()
                valid_y = y[y > 0].dropna()
                all_y_vals.extend(valid_y.tolist())
            else:
                all_y_vals.extend(y.dropna().tolist())

            if not x.empty:
                has_any_data = True
                fig.add_trace(
                    go.Scatter(
                        x=x,
                        y=y,
                        mode="lines+markers",
                        name=s,
                        line=dict(color=color_map.get(s), width=2),
                        marker=dict(size=5),
                        hovertemplate=f"File: {s}<br>Cycle: %{{x}}<br>{info['pretty']}: %{{y}}<extra></extra>",
                    )
                )

        if is_log:
            yaxis_config = dict(
                type="log",
                tickmode="array",
                tickvals=tick_vals,
                ticktext=tick_text,
                exponentformat="power",
                title_text=f"|{info['pretty']}|",
                gridcolor="#E5E5E5",
                minor=dict(showgrid=False),
                zeroline=False,
            )
            if all_y_vals:
                lmin, lmax = np.log10(min(all_y_vals)), np.log10(max(all_y_vals))
                if (lmax - lmin) < 1.0:
                    mid = (lmin + lmax) / 2
                    yaxis_config["range"] = [mid - 0.55, mid + 0.55]
            fig.update_yaxes(**yaxis_config)
        else:
            fig.update_yaxes(
                type="linear",
                title_text=info["pretty"],
                gridcolor="#E5E5E5",
                zeroline=True,
                zerolinecolor="gray",
                autorange=True,
            )

        fig.update_xaxes(title_text="Cycle Number", gridcolor="#E5E5E5")

        fig.update_layout(
            title=f"Endurance Performance – {info['pretty']}",
            width=900,
            height=600,
            template="plotly_white",
            showlegend=True,
            meta={"param_id": param},
        )

        if not has_any_data:
            fig.add_annotation(
                text="No data",
                xref="paper",
                yref="paper",
                x=0.5,
                y=0.5,
                showarrow=False,
            )

        figures.append(fig)

    return figures
