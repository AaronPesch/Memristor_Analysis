from __future__ import annotations
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from .utils import gradient_colors, has_valid_data


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


_TICK_VALS = [10.0**i for i in range(-15, 16)]
_TICK_TEXT = [f"1e{i}" if i != 0 else "1" for i in range(-15, 16)]


def combined_cdf_fig(
    group_dfs: list[tuple[str, "pd.DataFrame"]],
    all_df: "pd.DataFrame",
    color_map: dict,
    specs: list[tuple[str, str, str | None]],
    param_id: str,
    title: str,
    x_title: str,
    is_log: bool,
    meta_extra: dict | None = None,
) -> go.Figure:
    """Combined CDF: two parameters overlaid, one solid + one dashed curve per group.

    specs: list of (column, label, dash) e.g. [("VSET","V_set",None), ("V_reset","V_reset","dot")].
    Curves of the same group share a legendgroup; only the first shows in the legend,
    so a single legend click (togglegroup) filters that group. Values are absolute.
    """
    fig = go.Figure()
    all_x: list[float] = []

    def _xy(sub, col):
        series = sub[col] if is_log else pd.to_numeric(sub[col], errors="coerce").abs()
        return _cdf_xy(series, is_log=is_log)

    for name, sub in group_dfs:
        for i, (col, label, dash) in enumerate(specs):
            x, y = _xy(sub, col)
            if x.size == 0:
                continue
            all_x.extend(x)
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=y,
                    mode="lines",
                    name=name,
                    line=dict(color=color_map.get(name), width=1.5, dash=dash),
                    opacity=0.7,
                    legendgroup=name,
                    showlegend=(i == 0),
                    hovertemplate=f"{label}<br>%{{x}}<br>%{{y:.1f}}%<extra></extra>",
                )
            )

    for i, (col, label, dash) in enumerate(specs):
        x, y = _xy(all_df, col)
        if x.size == 0:
            continue
        all_x.extend(x)
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="lines",
                name="All Data (unified)",
                line=dict(color="black", width=2.5, dash=dash),
                legendgroup="unified",
                showlegend=(i == 0),
                hovertemplate=f"All {label}<br>%{{x}}<br>%{{y:.1f}}%<extra></extra>",
            )
        )

    if is_log:
        fig.update_xaxes(
            type="log",
            tickmode="array",
            tickvals=_TICK_VALS,
            ticktext=_TICK_TEXT,
            title_text=x_title,
            exponentformat="power",
            showgrid=True,
            gridcolor="#E5E5E5",
            zeroline=False,
            minor=dict(showgrid=False),
            autorange=True,
        )
    else:
        fig.update_xaxes(
            type="linear",
            title_text=x_title,
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
        title=title,
        width=900,
        height=600,
        template="plotly_white",
        showlegend=True,
        legend=dict(groupclick="togglegroup"),
        meta={"param_id": param_id, **(meta_extra or {})},
    )

    if all_x:
        note = " / ".join(
            f"{'solid' if d is None else 'dashed'} = {lab}" for _, lab, d in specs
        )
        fig.add_annotation(
            text=note,
            xref="paper",
            yref="paper",
            x=0.5,
            y=1.06,
            showarrow=False,
            font=dict(size=11),
        )
    else:
        fig.add_annotation(
            text="No valid data found",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
        )

    return fig


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
        "Memory_window": {"pretty": "Memory Window", "scale": "log"},
    }

    cols = gradient_colors(max(len(sets), 1))
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

    # Combined comparison figures (per-set, filterable legend)
    group_dfs = [(s, cdf_table[cdf_table["source_file"] == s]) for s in sets]
    if {"VSET", "V_reset"}.issubset(cdf_table.columns):
        figures.append(
            combined_cdf_fig(
                group_dfs,
                cdf_table,
                color_map,
                [("VSET", "V_set", None), ("V_reset", "V_reset", "dot")],
                "V_set_vs_V_reset",
                "CDF – |V_set| vs |V_reset|",
                "|Voltage| (V)",
                is_log=False,
            )
        )
    if {"R_HRS", "R_LRS"}.issubset(cdf_table.columns):
        figures.append(
            combined_cdf_fig(
                group_dfs,
                cdf_table,
                color_map,
                [("R_HRS", "R_HRS", None), ("R_LRS", "R_LRS", "dot")],
                "R_HRS_vs_R_LRS",
                "CDF – |R_HRS| vs |R_LRS| (Log Scale)",
                "|Resistance| (Ω)",
                is_log=True,
            )
        )

    return figures
