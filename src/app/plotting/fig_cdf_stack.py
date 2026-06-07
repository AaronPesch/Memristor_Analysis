from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go
from .fig_cdf import _cdf_xy
from .utils import gradient_colors, has_valid_data, find_device_sets, log_axis_config


def build_stack_level_cdf_figs(
    cdf_table: "pd.DataFrame",
    stack_id: str,
    devices: list[str],
    leakage_i_by_device: "dict[str, float] | None" = None,
    v_read: float = 0.2,
) -> list[go.Figure]:
    """
    Stack-Level CDFs: one curve per device (aggregated) PLUS a unified
    'All Devices' curve combining the entire stack into one dataset.
    """
    if not has_valid_data(cdf_table, devices):
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

    # Build per-device R_pristine scalar dict
    r_pristine_by_device: dict[str, float] = {}
    if leakage_i_by_device:
        for device, il in leakage_i_by_device.items():
            if il is not None and abs(il) > 0:
                r_pristine_by_device[device] = v_read / abs(il)

    if "R_pristine" not in param_map and r_pristine_by_device:
        param_map["R_pristine"] = {"pretty": "R_pristine (Ω)", "scale": "log"}

    cols = gradient_colors(max(len(devices), 1))
    color_map = {d: cols[i] for i, d in enumerate(devices)}

    figures = []

    for param, info in param_map.items():
        if param != "R_pristine" and param not in cdf_table.columns:
            continue

        fig = go.Figure()
        is_log = info["scale"] == "log"
        has_any_data = False
        all_x_vals = []

        is_scalar_param = param == "R_pristine"

        # One curve per device (aggregated across all its sets)
        for device in devices:
            if is_scalar_param:
                val = r_pristine_by_device.get(device)
                if val is None:
                    continue
                import numpy as np

                x = np.array([val])
                y = np.array([100.0])
            else:
                device_sets = find_device_sets(cdf_table, device, stack_id=stack_id)
                df_device = cdf_table[cdf_table["source_file"].isin(device_sets)]
                x, y = _cdf_xy(df_device[param], is_log=is_log)

            if x.size > 0:
                has_any_data = True
                all_x_vals.extend(x)
                fig.add_trace(
                    go.Scatter(
                        x=x,
                        y=y,
                        mode="lines+markers",
                        name=device,
                        marker=dict(size=4),
                        line=dict(color=color_map.get(device), width=2),
                        opacity=0.8,
                        legendgroup=device,
                        hovertemplate="%{x}<br>%{y:.1f}%<extra></extra>",
                    )
                )

        # Unified "All Devices" curve — entire stack as one dataset
        if is_scalar_param:
            import numpy as np

            all_scalar = sorted(r_pristine_by_device.values())
            x_all = np.array(all_scalar)
            y_all = (np.arange(1, len(x_all) + 1) / len(x_all)) * 100.0
        else:
            x_all, y_all = _cdf_xy(cdf_table[param], is_log=is_log)

        if x_all.size > 0:
            has_any_data = True
            all_x_vals.extend(x_all)
            fig.add_trace(
                go.Scatter(
                    x=x_all,
                    y=y_all,
                    mode="lines",
                    name="All Devices (unified)",
                    line=dict(color="black", width=2.5),
                    legendgroup="unified",
                    hovertemplate="All<br>%{x}<br>%{y:.1f}%<extra></extra>",
                )
            )

        if is_log:
            xaxis_kwargs = dict(
                type="log",
                title_text=f"|{info['pretty']}|",
                exponentformat="power",
                showgrid=True,
                gridcolor="#E5E5E5",
                zeroline=False,
                minor=dict(showgrid=False),
            )
            xaxis_kwargs.update(log_axis_config(all_x_vals))
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
            title=f"Stack {stack_id} – CDF {info['pretty']} ({info['scale'].capitalize()} Scale)",
            width=900,
            height=600,
            template="plotly_white",
            showlegend=True,
            meta={"param_id": param, "level": "stack", "stack_id": stack_id},
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
