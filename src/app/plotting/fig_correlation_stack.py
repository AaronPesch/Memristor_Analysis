from __future__ import annotations
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from .utils import gradient_colors, has_valid_data, find_device_sets


def build_stack_level_correlation_figs(
    scatter_df: "pd.DataFrame",
    stack_id: str,
    devices: list[str],
    forming_v_by_device: "dict[str, float] | None" = None,
    leakage_i_by_device: "dict[str, float] | None" = None,
    v_read: float = 0.2,
    first_v_reset: "dict[str, float] | None" = None,
) -> list[go.Figure]:
    """
    Stack-Level: Correlation scatter plots (one per pair).
    Every device aggregates his endurance-sets.

    Single-point pairs (one point per device):
      - V_forming vs 1st V_reset
      - I_leakage_pristine vs V_forming
      - R_pristine (= V_read / I_leakage) vs V_forming
    """
    if not has_valid_data(scatter_df, devices):
        return []

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

    cols = gradient_colors(max(len(devices), 1))
    device_color_map = {d: cols[i] for i, d in enumerate(devices)}

    tick_vals = [10.0**i for i in range(-15, 16)]
    tick_text = [f"1e{i}" if i != 0 else "1" for i in range(-15, 16)]

    # V_read = 0.2 V (consistent with R_LRS / R_HRS computation)

    # Build a per-device scalar DataFrame – one row per device, one point per pair
    scalar_rows = []
    for device in devices:
        row: dict = {"device": device}
        if forming_v_by_device:
            vf = forming_v_by_device.get(device)
            if vf is not None:
                row["V_forming"] = vf
        if leakage_i_by_device:
            il = leakage_i_by_device.get(device)
            if il is not None and abs(il) > 0:
                row["I_leakage_pristine"] = abs(il)
                row["R_pristine"] = v_read / abs(il)
        if first_v_reset:
            fvr = first_v_reset.get(device)
            if fvr is not None:
                row["first_V_reset"] = fvr
        scalar_rows.append(row)
    scalar_df = pd.DataFrame(scalar_rows)

    # Only add a scalar pair when both required columns are present
    scalar_pairs: list[tuple[str, str, str]] = []
    if {"V_forming", "first_V_reset"}.issubset(scalar_df.columns):
        scalar_pairs.append(
            ("V_forming", "first_V_reset", "V_forming (V) vs 1st V_reset (V)")
        )
    if {"I_leakage_pristine", "V_forming"}.issubset(scalar_df.columns):
        scalar_pairs.append(
            (
                "I_leakage_pristine",
                "V_forming",
                "I_leakage pristine (A) vs V_forming (V)",
            )
        )
    if {"R_pristine", "V_forming"}.issubset(scalar_df.columns):
        scalar_pairs.append(
            ("R_pristine", "V_forming", "R_pristine (Ω) vs V_forming (V)")
        )

    figures = []

    for x_col, y_col, title_text in pairs + scalar_pairs:
        is_scalar_pair = (x_col, y_col, title_text) in scalar_pairs
        fig = go.Figure()
        x_scale = get_scale(x_col)
        y_scale = get_scale(y_col)

        all_x, all_y = [], []

        if is_scalar_pair:
            # One point per device from scalar_df
            df_s = scalar_df.dropna(subset=[x_col, y_col])
            for _, row in df_s.iterrows():
                device = row["device"]
                x_val = float(row[x_col])
                y_val = float(row[y_col])
                all_x.append(x_val)
                all_y.append(y_val)
                fig.add_trace(
                    go.Scatter(
                        x=[x_val],
                        y=[y_val],
                        mode="markers",
                        marker=dict(
                            color=device_color_map.get(device), size=10, opacity=0.9
                        ),
                        name=device,
                        legendgroup=device,
                        hovertemplate=(
                            f"Device: {device}<br>"
                            f"{x_col}: %{{x}}<br>"
                            f"{y_col}: %{{y}}<extra></extra>"
                        ),
                    )
                )
        else:
            for device in devices:
                device_sets = find_device_sets(scatter_df, device, stack_id=stack_id)

                # aggregate
                df_device = scatter_df[
                    scatter_df["source_file"].isin(device_sets)
                ].copy()
                if df_device.empty:
                    continue

                # data cleaning
                for col, scale in [(x_col, x_scale), (y_col, y_scale)]:
                    df_device[col] = pd.to_numeric(df_device[col], errors="coerce")
                    if scale == "log":
                        df_device[col] = df_device[col].abs()
                        df_device.loc[df_device[col] <= 0, col] = np.nan

                df_plot = df_device.dropna(subset=[x_col, y_col])
                if df_plot.empty:
                    continue

                all_x.extend(df_plot[x_col].tolist())
                all_y.extend(df_plot[y_col].tolist())

                fig.add_trace(
                    go.Scatter(
                        x=df_plot[x_col],
                        y=df_plot[y_col],
                        mode="markers",
                        marker=dict(
                            color=device_color_map[device], size=7, opacity=0.7
                        ),
                        name=device,
                        legendgroup=device,
                        hovertemplate=f"Device: {device}<br>{x_col}: %{{x}}<br>{y_col}: %{{y}}<extra></extra>",
                    )
                )

        # axis
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
                if all_vals:
                    lmin, lmax = np.log10(min(all_vals)), np.log10(max(all_vals))
                    if (lmax - lmin) < 1.0:
                        mid = (lmin + lmax) / 2
                        axis_config["range"] = [mid - 0.55, mid + 0.55]

            fig.update_layout({axis_name: axis_config})

        param_id = f"{x_col}_vs_{y_col}"
        fig.update_layout(
            title=f"Stack {stack_id} – Correlation: {title_text}",
            width=900,
            height=700,
            template="plotly_white",
            legend=dict(title="Devices (Click to toggle)"),
            meta={"param_id": param_id, "level": "stack", "stack_id": stack_id},
        )
        figures.append(fig)

    return figures
