from __future__ import annotations
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from .utils import gradient_colors, has_valid_data


def build_correlation_scatter_figs(
    scatter_df: "pd.DataFrame", sets: list[str]
) -> list[go.Figure]:
    """
    Creates a list of correlation scatter plots (one per pair).
    - All sets are displayed simultaneously.
    - Automatic Log/Linear scaling based on parameter type.
    - Major magnitudes only for log axes.
    """
    if not has_valid_data(scatter_df, sets):
        return []

    # 1. Define pairs and their scale types
    pairs = [
        ("V_set", "I_HRS", "V_set (V) vs I_HRS (A)"),
        ("V_set", "R_HRS", "V_set (V) vs R_HRS (Ω)"),
        ("V_reset", "I_LRS", "V_reset (V) vs I_LRS (A)"),
        ("V_reset", "R_LRS", "V_reset (V) vs R_LRS (Ω)"),
        ("V_reset", "I_reset_max", "V_reset (V) vs I_reset_max (A)"),
        ("V_set", "V_reset", "V_set (V) vs V_reset (V)"),
    ]

    def get_scale(col_name):
        return "log" if any(x in col_name for x in ["I_", "R_"]) else "linear"

    # 2. Setup Colors
    cols = gradient_colors(max(len(sets), 1))
    set_color_map = {s: cols[i] for i, s in enumerate(sets)}

    # 3. Log Ticks logic
    tick_vals = [10.0**i for i in range(-15, 16)]
    tick_text = [f"1e{i}" if i != 0 else "1" for i in range(-15, 16)]

    figures = []

    for x_col, y_col, title_text in pairs:
        fig = go.Figure()
        x_scale = get_scale(x_col)
        y_scale = get_scale(y_col)

        all_x, all_y = [], []

        for s in sets:
            df_s = scatter_df[scatter_df["source_file"] == s].copy()
            if df_s.empty:
                continue

            # Data Cleaning for Log/Linear
            for col, scale in [(x_col, x_scale), (y_col, y_scale)]:
                df_s[col] = pd.to_numeric(df_s[col], errors="coerce")
                if scale == "log":
                    df_s[col] = df_s[col].abs()
                    df_s.loc[df_s[col] <= 0, col] = np.nan

            df_plot = df_s.dropna(subset=[x_col, y_col])
            if df_plot.empty:
                continue

            all_x.extend(df_plot[x_col].tolist())
            all_y.extend(df_plot[y_col].tolist())

            fig.add_trace(
                go.Scatter(
                    x=df_plot[x_col],
                    y=df_plot[y_col],
                    mode="markers",
                    marker=dict(color=set_color_map[s], size=7, opacity=0.7),
                    name=s,
                    legendgroup=s,
                    hovertemplate=f"File: {s}<br>{x_col}: %{{x}}<br>{y_col}: %{{y}}<extra></extra>",
                )
            )

        # Configure Axes
        for axis_name, col, scale, all_vals in [
            ("xaxis", x_col, x_scale, all_x),
            ("yaxis", y_col, y_scale, all_y),
        ]:
            axis_config = dict(
                title_text=f"|{col}|" if scale == "log" else col,
                gridcolor="#E5E5E5",
                zeroline=(scale == "linear"),
                zerolinecolor="gray",
            )

            if scale == "log":
                axis_config.update(
                    dict(
                        type="log",
                        tickmode="array",
                        tickvals=tick_vals,
                        ticktext=tick_text,
                        exponentformat="power",
                        minor=dict(showgrid=False),
                    )
                )
                # Ensure at least one magnitude visible
                if all_vals:
                    lmin, lmax = np.log10(min(all_vals)), np.log10(max(all_vals))
                    if (lmax - lmin) < 1.0:
                        mid = (lmin + lmax) / 2
                        axis_config["range"] = [mid - 0.55, mid + 0.55]

            fig.update_layout({axis_name: axis_config})

        # Final Layout
        param_id = f"{x_col}_vs_{y_col}"
        fig.update_layout(
            title=f"Correlation: {title_text}",
            width=900,
            height=700,
            template="plotly_white",
            legend=dict(title="Files (Click to toggle)"),
            meta={"param_id": param_id},
        )
        figures.append(fig)

    return figures
