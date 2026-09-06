"""The plotting pipeline, minus the file system.

This is `src/app/plotting/run.py` with one change: where run.py calls
`fig.write_html(...)` and `fig.to_json()` into an output directory, this
returns the figures. Same Config, same load_all(), same twelve fig_* builders,
untouched.

That is the whole claim of the prototype -- the builders never knew how they
were transported, so they did not have to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import plotly.graph_objects as go

from app.core.modes import Mode
from app.plotting.config import Config
from app.plotting.fig_boxplots import build_boxplots_figs
from app.plotting.fig_boxplots_stack import build_stack_level_boxplots
from app.plotting.fig_cdf import build_cdf_figs
from app.plotting.fig_cdf_stack import build_stack_level_cdf_figs
from app.plotting.fig_characteristic import build_characteristic_figs
from app.plotting.fig_correlation import build_correlation_scatter_figs
from app.plotting.fig_correlation_matrix import build_correlation_matrix_figs
from app.plotting.fig_correlation_matrix_stack import (
    build_stack_level_correlation_matrix_figs,
)
from app.plotting.fig_correlation_stack import build_stack_level_correlation_figs
from app.plotting.fig_endurance import build_endurance_figs
from app.plotting.fig_spatial_map_stack import build_stack_level_spatial_maps
from app.plotting.pipeline import LoadedData, load_all

import fig_yield


@dataclass
class Category:
    """One top-level tab: a named group of figures, keyed by param_id."""

    key: str
    label: str
    figures: dict[str, go.Figure] = field(default_factory=dict)

    @property
    def param_ids(self) -> list[str]:
        return list(self.figures)


def _collect(key: str, label: str, figs: list[go.Figure]) -> Category:
    """Key figures by the param_id the builders already put in fig.layout.meta."""
    out = Category(key=key, label=label)
    for i, fig in enumerate(figs):
        meta = fig.layout.meta or {}
        out.figures[meta.get("param_id") or f"{key}_{i}"] = fig
    return out


def build_device_categories(data: LoadedData) -> list[Category]:
    return [
        _collect(
            "characteristic_plots",
            "Characteristic",
            build_characteristic_figs(
                data.raw_characteristic, data.sets, raw_by_reset=data.raw_reset
            ),
        ),
        _collect(
            "endurance_performance",
            "Endurance",
            build_endurance_figs(data.end_df, data.sets),
        ),
        _collect(
            "boxplots", "Boxplots", build_boxplots_figs(data.box_table, data.sets)
        ),
        _collect("cdfs", "CDF", build_cdf_figs(data.cdf_table, data.sets)),
        _collect(
            "correlation_plots",
            "Correlation",
            build_correlation_scatter_figs(data.scatter_df, data.sets),
        ),
        _collect(
            "correlation_matrices",
            "Correlation Matrix",
            build_correlation_matrix_figs(
                scatter_df=data.scatter_df,
                sets=data.sets,
                devices=data.devices,
                stack_id=data.stack_id,
            ),
        ),
    ]


def build_stack_categories(data: LoadedData) -> list[Category]:
    return [
        _collect(
            "boxplots_stack_level",
            "Boxplots",
            build_stack_level_boxplots(
                box_table=data.box_table,
                stack_id=data.stack_id,
                devices=data.devices,
                leakage_i_by_device=data.leakage_i_by_device,
                v_read=data.v_read,
            ),
        ),
        _collect(
            "cdfs_stack_level",
            "CDF",
            build_stack_level_cdf_figs(
                cdf_table=data.cdf_table,
                stack_id=data.stack_id,
                devices=data.devices,
                leakage_i_by_device=data.leakage_i_by_device,
                v_read=data.v_read,
            ),
        ),
        _collect(
            "correlation_plots_stack_level",
            "Correlation",
            build_stack_level_correlation_figs(
                scatter_df=data.scatter_df,
                stack_id=data.stack_id,
                devices=data.devices,
                forming_v_by_device=data.forming_v_by_device,
                leakage_i_by_device=data.leakage_i_by_device,
                first_v_reset=data.first_v_reset,
                v_read=data.v_read,
            ),
        ),
        _collect(
            "correlation_matrices_stack_level",
            "Correlation Matrix",
            build_stack_level_correlation_matrix_figs(
                scatter_df=data.scatter_df,
                stack_id=data.stack_id,
                devices=data.devices,
                forming_v_by_device=data.forming_v_by_device,
                leakage_i_by_device=data.leakage_i_by_device,
                first_v_reset=data.first_v_reset,
                v_read=data.v_read,
            ),
        ),
        _collect(
            "spatial_maps_stack_level",
            "Stack Map",
            build_stack_level_spatial_maps(
                box_table=data.box_table,
                stack_id=data.stack_id,
                devices=data.devices,
            ),
        ),
        # Not in main -- FEATURES.md lists it, the code never had it.
        _collect(
            "yield_map_stack_level",
            "Yield Map",
            fig_yield.build_yield_maps(
                box_table=data.box_table,
                stack_id=data.stack_id,
                devices=data.devices,
            ),
        ),
    ]


def build_categories(cfg: Config, data: LoadedData) -> list[Category]:
    if cfg.mode is Mode.DEVICE:
        return build_device_categories(data)
    return build_stack_categories(data)


def load_and_build(cfg: Config) -> tuple[LoadedData, list[Category]]:
    data = load_all(cfg)
    return data, [c for c in build_categories(cfg, data) if c.figures]
