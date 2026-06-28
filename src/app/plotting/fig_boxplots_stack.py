from __future__ import annotations
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from .utils import gradient_colors, has_valid_data, find_device_sets


def build_stack_level_boxplots(
    box_table: pd.DataFrame,
    stack_id: str,
    devices: list[str],
    leakage_i_by_device: "dict[str, float] | None" = None,
    v_read: float = 0.2,
) -> list[go.Figure]:
    """
    Stack-Level Boxplots: one box per device (aggregated) PLUS a unified
    'All Devices' box combining the entire stack into one dataset.
    """
    if not has_valid_data(box_table, devices):
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

    tick_vals = [10.0**i for i in range(-15, 16)]
    tick_text = [f"1e{i}" if i != 0 else "1" for i in range(-15, 16)]

    figures = []

    for param, info in param_map.items():
        if param != "R_pristine" and param not in box_table.columns:
            continue

        fig = go.Figure()
        is_log = info["scale"] == "log"
        has_any_data = False
        all_vals_for_param = []

        is_scalar_param = param == "R_pristine"

        # One box per device (aggregated across all its sets)
        for device in devices:
            if is_scalar_param:
                # R_pristine: single scalar value per device
                val = r_pristine_by_device.get(device)
                if val is None:
                    continue
                vals = pd.Series([val])
            else:
                if param not in box_table.columns:
                    continue
                device_sets = find_device_sets(box_table, device, stack_id=stack_id)
                df_device = box_table[box_table["source_file"].isin(device_sets)]
                vals = pd.to_numeric(df_device[param], errors="coerce").dropna()
                if is_log:
                    vals = vals.abs()
                    vals = vals[vals > 0]

            if not vals.empty:
                has_any_data = True
                all_vals_for_param.extend(vals.tolist())

            fig.add_trace(
                go.Box(
                    y=vals,
                    name=device,
                    width=0.3,
                    marker_color=color_map.get(device),
                    line=dict(width=2),
                    fillcolor=color_map.get(device),
                    opacity=0.7,
                    boxpoints=False,
                    boxmean=False,
                    legendgroup=device,
                )
            )

        # Unified "All Devices" box — entire stack as one dataset
        if is_scalar_param:
            all_scalar_vals = pd.Series(list(r_pristine_by_device.values()))
            all_vals = (
                all_scalar_vals[all_scalar_vals > 0] if is_log else all_scalar_vals
            )
        else:
            if param not in box_table.columns:
                continue
            all_vals = pd.to_numeric(box_table[param], errors="coerce").dropna()
            if is_log:
                all_vals = all_vals.abs()
                all_vals = all_vals[all_vals > 0]

        if not all_vals.empty:
            has_any_data = True
            fig.add_trace(
                go.Box(
                    y=all_vals,
                    name="All Devices (unified)",
                    width=0.3,
                    marker_color="black",
                    line=dict(width=2.5, color="black"),
                    fillcolor="rgba(0,0,0,0.15)",
                    boxpoints=False,
                    boxmean=False,
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
            title_text="Device",
            showgrid=True,
            gridcolor="#E5E5E5",
            showticklabels=False,
        )

        fig.update_layout(
            title=f"Stack {stack_id} – {info['pretty']} ({info['scale'].capitalize()} Scale)",
            width=max(900, (len(devices) + 1) * 70),
            height=600,
            template="plotly_white",
            showlegend=True,
            boxmode="group",
            boxgap=0.1,
            meta={"param_id": param, "level": "stack", "stack_id": stack_id},
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
