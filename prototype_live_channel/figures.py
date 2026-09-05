"""Figure builders -- the analogue of your existing src/app/plotting/fig_*.py.

Note what does NOT happen here: no write_html, no sidecar .json, no output_dir.
A builder returns a plotly Figure; the transport is somebody else's problem.
"""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from data import COLS, PARAMS, ROWS

ACCENT = "#4c8dff"
MUTED_LIGHT = "#c8ccd4"
MUTED_DARK = "#4a4f59"

THEME = {
    False: dict(paper="#ffffff", plot="#f6f7f9", font="#1b1d22", grid="#dde0e6"),
    True: dict(paper="#1b1d22", plot="#23262c", font="#e7e9ec", grid="#3a3f48"),
}


def _positive(*arrays) -> bool:
    """A log axis is only meaningful if every value is > 0. V_reset is not."""
    return all(
        a.size == 0 or float(np.min(a)) > 0
        for a in (np.asarray(x, dtype=float) for x in arrays)
    )


def _style(
    fig: go.Figure, dark: bool, title: str, log_y: bool, *, log_x: bool = False
) -> go.Figure:
    """Apply theme + the uirevision keys that make Plotly.react non-destructive.

    uirevision is the mechanism that keeps the user's zoom, pan and legend state
    across a data update. Keeping x and y revisions separate means a log/linear
    toggle rescales only the y-axis and leaves the x-zoom alone.
    """
    t = THEME[dark]
    fig.update_layout(
        title=dict(text=title, font=dict(size=13)),
        paper_bgcolor=t["paper"],
        plot_bgcolor=t["plot"],
        font=dict(color=t["font"], size=11),
        margin=dict(l=62, r=16, t=40, b=44),
        showlegend=False,
        uirevision="keep",
        hovermode="closest",
    )
    fig.update_xaxes(
        gridcolor=t["grid"],
        zerolinecolor=t["grid"],
        linecolor=t["grid"],
        uirevision=f"x-{log_x}",
        type="log" if log_x else "linear",
    )
    fig.update_yaxes(
        gridcolor=t["grid"],
        zerolinecolor=t["grid"],
        linecolor=t["grid"],
        uirevision=f"y-{log_y}",
        type="log" if log_y else "linear",
    )
    return fig


def spatial_map(rows, selected: set[str], param: str, dark: bool) -> go.Figure:
    """Stack map. Built from scattergl markers rather than a heatmap, because
    markers support click and box-select -- this plot is a selection control."""
    label, unit, _ = PARAMS[param]
    x = [r[1] + 1 for r in rows]
    y = [r[0] + 1 for r in rows]
    ids = [r[2] for r in rows]
    val = np.asarray([r[3] for r in rows], dtype=float)

    # Resistances span decades, V_set/V_reset do not -- and V_reset is negative,
    # so log10 is only safe when the data allows it.
    use_log = _positive(val)
    color = np.log10(val) if use_log else val
    cbar_label = f"log10<br>{label}" if use_log else label

    fig = go.Figure(
        go.Scattergl(
            x=x,
            y=y,
            mode="markers",
            marker=dict(
                size=30,
                symbol="square",
                color=color,
                colorscale="Viridis",
                showscale=True,
                colorbar=dict(
                    title=dict(text=cbar_label, font=dict(size=10)), thickness=12
                ),
                line=dict(
                    width=[3 if i in selected else 0 for i in ids],
                    color=ACCENT,
                ),
            ),
            customdata=ids,
            hovertemplate="%{customdata}<br>"
            + cbar_label.replace("<br>", " ")
            + ": %{marker.color:.3g}<extra></extra>",
        )
    )
    fig.update_layout(dragmode="select")
    fig.update_xaxes(title="Column", dtick=1, range=[0.4, COLS + 0.6])
    fig.update_yaxes(title="Row", dtick=1, range=[0.4, ROWS + 0.6], scaleanchor="x")
    return _style(fig, dark, f"Stack map - median {label} [{unit}]", log_y=False)


def correlation(rows, selected: set[str], dark: bool) -> go.Figure:
    """|V_set| vs |V_reset|, one point per cycle. Unselected devices stay
    visible but dimmed -- that is what makes cross-filtering readable."""
    dev = np.asarray([r[0] for r in rows])
    xs = np.asarray([r[1] for r in rows], dtype=float)
    ys = np.asarray([r[2] for r in rows], dtype=float)
    mask = np.isin(dev, list(selected)) if selected else np.ones(len(dev), dtype=bool)

    muted = MUTED_DARK if dark else MUTED_LIGHT
    fig = go.Figure()
    if selected and (~mask).any():
        fig.add_trace(
            go.Scattergl(
                x=xs[~mask],
                y=ys[~mask],
                mode="markers",
                marker=dict(size=4, color=muted, opacity=0.45),
                hoverinfo="skip",
            )
        )
    fig.add_trace(
        go.Scattergl(
            x=xs[mask],
            y=ys[mask],
            mode="markers",
            marker=dict(size=5, color=ACCENT, opacity=0.75),
            customdata=dev[mask],
            hovertemplate="%{customdata}<br>|V_set| %{x:.2f} V<br>|V_reset| %{y:.2f} V<extra></extra>",
        )
    )
    fig.update_layout(dragmode="lasso")
    fig.update_xaxes(title="|V_set| [V]")
    fig.update_yaxes(title="|V_reset| [V]")
    return _style(fig, dark, "Correlation - lasso to filter", log_y=False)


def cdf(
    all_vals: np.ndarray, sel_vals: np.ndarray, param: str, dark: bool, log_x: bool
) -> go.Figure:
    """Selection against the full stack, so the effect of a filter is obvious."""
    label, unit, _ = PARAMS[param]
    log_x = log_x and _positive(all_vals, sel_vals)
    muted = MUTED_DARK if dark else MUTED_LIGHT
    fig = go.Figure()

    def add(values, color, width, name):
        if values.size == 0:
            return
        v = np.sort(values)
        p = np.arange(1, v.size + 1) / v.size * 100
        fig.add_trace(
            go.Scattergl(
                x=v,
                y=p,
                mode="lines",
                name=name,
                line=dict(color=color, width=width),
                hovertemplate=name + "<br>%{x:.3g}<br>%{y:.1f} %<extra></extra>",
            )
        )

    add(all_vals, muted, 2, "all devices")
    add(sel_vals, ACCENT, 2.5, "selection")
    fig.update_xaxes(title=f"{label} [{unit}]")
    fig.update_yaxes(title="Cumulative [%]", range=[0, 100])
    return _style(fig, dark, f"CDF - {label}", log_y=False, log_x=log_x)


def endurance(rows, param: str, dark: bool, log_y: bool) -> go.Figure:
    """Mean per cycle with a 10-90 % band. The range slider is a filter input."""
    label, unit, _ = PARAMS[param]
    cyc = [r[0] for r in rows]
    mean = [r[1] for r in rows]
    lo = [r[2] for r in rows]
    hi = [r[3] for r in rows]
    log_y = log_y and _positive(lo)

    band = "rgba(76,141,255,0.18)"
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=cyc + cyc[::-1],
            y=hi + lo[::-1],
            fill="toself",
            fillcolor=band,
            line=dict(width=0),
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scattergl(
            x=cyc,
            y=mean,
            mode="lines",
            line=dict(color=ACCENT, width=2),
            hovertemplate="Cycle %{x}<br>%{y:.3g}<extra></extra>",
        )
    )
    fig.update_xaxes(title="Cycle", rangeslider=dict(visible=True, thickness=0.10))
    fig.update_yaxes(title=f"{label} [{unit}]")
    return _style(fig, dark, f"Endurance - {label} (drag the slider)", log_y=log_y)
