from __future__ import annotations
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from .utils import has_valid_data


def _cdf_xy(values: pd.Series, is_log: bool) -> tuple[np.ndarray, np.ndarray]:
    """
    Return sorted x and cumulative probability in percent.
    If is_log is True, applies absolute magnitude and filters out <= 0.
    """
    v = pd.to_numeric(values, errors="coerce").dropna()

    if is_log:
        v = v.abs()
        v = v[v > 0]

    v = v.to_numpy()

    if v.size == 0:
        return np.array([]), np.array([])

    x = np.sort(v)
    y = (np.arange(1, x.size + 1) / x.size) * 100.0
    return x, y


def build_cdf_figs(cdf_table: "pd.DataFrame", sets: list[str]) -> list[go.Figure]:
    """
    Creates a list of CDF Figure objects, one for each parameter.
    Each figure shows individual curves per source file PLUS a unified
    'All Data' curve aggregating all sets into one dataset.
    """
    if not has_valid_data(cdf_table, sets):
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

    cols = px.colors.sample_colorscale("Viridis", max(len(sets), 2))
    color_map = {s: cols[i] for i, s in enumerate(sets)}

    tick_vals = [10.0**i for i in range(-15, 16)]
    tick_text = [f"1e{i}" if i != 0 else "1" for i in range(-15, 16)]

    figures = []

    for param, info in param_map.items():
        if param not in cdf_table.columns:
            continue

        fig = go.Figure()
        is_log = info["scale"] == "log"
        has_any_data = False
        all_x_vals = []

        # Individual curves per source file
        for s in sets:
            df_s = cdf_table[cdf_table["source_file"] == s]
            x, y = _cdf_xy(df_s[param], is_log=is_log)

            if x.size > 0:
                has_any_data = True
                all_x_vals.extend(x)
                fig.add_trace(
                    go.Scatter(
                        x=x,
                        y=y,
                        mode="lines+markers",
                        name=s,
                        marker=dict(size=4),
                        line=dict(color=color_map.get(s), width=1.5),
                        opacity=0.6,
                        legendgroup=s,
                        hovertemplate="%{x}<br>%{y:.1f}%<extra></extra>",
                    )
                )

        # Unified "All Data" curve — all sets combined into one dataset
        x_all, y_all = _cdf_xy(cdf_table[param], is_log=is_log)
        if x_all.size > 0:
            has_any_data = True
            all_x_vals.extend(x_all)
            fig.add_trace(
                go.Scatter(
                    x=x_all,
                    y=y_all,
                    mode="lines",
                    name="All Data (unified)",
                    line=dict(color="black", width=2.5),
                    legendgroup="unified",
                    hovertemplate="All<br>%{x}<br>%{y:.1f}%<extra></extra>",
                )
            )

        if is_log:
            xaxis_kwargs = dict(
                type="log",
                tickmode="array",
                tickvals=tick_vals,
                ticktext=tick_text,
                title_text=f"|{info['pretty']}|",
                exponentformat="power",
                showgrid=True,
                gridcolor="#E5E5E5",
                zeroline=False,
                minor=dict(showgrid=False),
            )

            if all_x_vals:
                lmin = np.log10(min(all_x_vals))
                lmax = np.log10(max(all_x_vals))
                if (lmax - lmin) < 1.0:
                    mid = (lmin + lmax) / 2
                    xaxis_kwargs["range"] = [mid - 0.55, mid + 0.55]
                else:
                    pad = (lmax - lmin) * 0.05
                    xaxis_kwargs["range"] = [lmin - pad, lmax + pad]

            fig.update_xaxes(**xaxis_kwargs)
        else:
            fig.update_xaxes(
                type="linear",
                title_text=info["pretty"],
                showgrid=True,
                gridcolor="#E5E5E5",
                zeroline=True,
                zerolinecolor="gray",
                autorange=True,
            )

        fig.update_yaxes(
            title_text="Probability (%)",
            range=[-2, 102],
            showgrid=True,
            gridcolor="#E5E5E5",
        )

        fig.update_layout(
            title=f"CDF – {info['pretty']} ({info['scale'].capitalize()} Scale)",
            width=900,
            height=600,
            template="plotly_white",
            showlegend=True,
            meta={"param_id": param},
        )

        if not has_any_data:
            fig.add_annotation(
                text="No valid data found for this scale type",
                xref="paper",
                yref="paper",
                x=0.5,
                y=0.5,
                showarrow=False,
                font=dict(color="red", size=14),
            )

        figures.append(fig)

    return figures
