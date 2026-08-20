from __future__ import annotations

from .config import Config, load_config
from .pipeline import LoadedData, load_all

from .fig_characteristic import build_characteristic_figs
from .fig_cdf import build_cdf_figs
from .fig_boxplots import build_boxplots_figs
from .fig_endurance import build_endurance_figs
from .fig_correlation import build_correlation_scatter_figs
from .fig_correlation_stack import build_stack_level_correlation_figs
from .fig_boxplots_stack import build_stack_level_boxplots
from .fig_cdf_stack import build_stack_level_cdf_figs
from .fig_correlation_matrix import build_correlation_matrix_figs
from .fig_correlation_matrix_stack import build_stack_level_correlation_matrix_figs
from .fig_spatial_map_stack import build_stack_level_spatial_maps
from app.core.modes import Mode


def _write(fig, out_path) -> None:
    width = getattr(fig.layout, "width", None) or 900
    config = {"responsive": False} if width > 900 else {}
    fig.write_html(out_path, config=config)
    print("Wrote:", out_path)


def _write_json(fig, out_path) -> None:
    out_path.write_text(fig.to_json(), encoding="utf-8")
    print("Wrote:", out_path)


def plot_device(
    cfg: Config, data: LoadedData, stack_id: str, devices: list[str]
) -> None:
    # Characteristic (set + reset)
    def write_characteristic_figs():
        char_dir = cfg.output_dir / "characteristic_plots"
        char_dir.mkdir(parents=True, exist_ok=True)

        char_figs = build_characteristic_figs(
            data.raw_characteristic,
            data.sets,
            raw_by_reset=data.raw_reset,  # pass reset data for current plot
        )
        for fig in char_figs:
            pid = fig.layout.meta.get("param_id")
            _write(fig, char_dir / f"{pid}.html")
            _write_json(fig, char_dir / f"{pid}.json")

    write_characteristic_figs()

    # CDF
    def write_cdf_figs():
        cdf_dir = cfg.output_dir / "cdfs"
        cdf_dir.mkdir(parents=True, exist_ok=True)

        cdf_figs = build_cdf_figs(data.cdf_table, data.sets)
        for fig in cdf_figs:
            pid = fig.layout.meta.get("param_id")
            _write(fig, cdf_dir / f"{pid}.html")
            _write_json(fig, cdf_dir / f"{pid}.json")

    write_cdf_figs()

    # Boxplots
    def write_boxplot_figs():
        boxplot_dir = cfg.output_dir / "boxplots"
        boxplot_dir.mkdir(parents=True, exist_ok=True)

        figs = build_boxplots_figs(data.box_table, data.sets)
        for fig in figs:
            pid = fig.layout.meta.get("param_id")
            _write(fig, boxplot_dir / f"{pid}.html")
            _write_json(fig, boxplot_dir / f"{pid}.json")

    write_boxplot_figs()

    # Endurance performance vs cycle
    def write_endurance_figs():
        end_dir = cfg.output_dir / "endurance_performance"
        end_dir.mkdir(parents=True, exist_ok=True)

        end_figs = build_endurance_figs(data.end_df, data.sets)
        for fig in end_figs:
            pid = fig.layout.meta.get("param_id")
            _write(fig, end_dir / f"{pid}.html")
            _write_json(fig, end_dir / f"{pid}.json")

    write_endurance_figs()

    # Correlation scatter
    def write_correlation_scatter_figs():
        char_dir = cfg.output_dir / "correlation_plots"
        char_dir.mkdir(parents=True, exist_ok=True)

        correlation_figs = build_correlation_scatter_figs(data.scatter_df, data.sets)
        for fig in correlation_figs:
            pid = fig.layout.meta.get("param_id")
            _write(fig, char_dir / f"{pid}.html")
            _write_json(fig, char_dir / f"{pid}.json")

    write_correlation_scatter_figs()

    # Correlation matrix
    def write_correlation_matrix_figs():
        matrix_dir = cfg.output_dir / "correlation_matrices"
        matrix_dir.mkdir(parents=True, exist_ok=True)

        matrix_figs = build_correlation_matrix_figs(
            scatter_df=data.scatter_df,
            sets=data.sets,
            devices=devices,
            stack_id=stack_id,
        )
        for fig in matrix_figs:
            pid = fig.layout.meta.get("param_id")
            _write(fig, matrix_dir / f"{pid}.html")
            _write_json(fig, matrix_dir / f"{pid}.json")

    write_correlation_matrix_figs()


def plot_stack(
    cfg: Config, data: LoadedData, stack_id: str, devices: list[str]
) -> None:
    # CDF stack level
    def write_stack_level_cdf_figs():
        stack_cdf_dir = cfg.output_dir / "cdfs_stack_level"
        stack_cdf_dir.mkdir(parents=True, exist_ok=True)

        stack_cdf_figs = build_stack_level_cdf_figs(
            cdf_table=data.cdf_table,
            stack_id=stack_id,
            devices=devices,
            leakage_i_by_device=data.leakage_i_by_device,
            v_read=data.v_read,
        )
        for fig in stack_cdf_figs:
            pid = fig.layout.meta.get("param_id")
            _write(fig, stack_cdf_dir / f"{pid}.html")
            _write_json(fig, stack_cdf_dir / f"{pid}.json")

    write_stack_level_cdf_figs()

    # Stack level boxplots
    def write_stack_level_boxplots():
        stack_dir = cfg.output_dir / "boxplots_stack_level"
        stack_dir.mkdir(parents=True, exist_ok=True)

        stack_figs = build_stack_level_boxplots(
            box_table=data.box_table,
            stack_id=stack_id,
            devices=devices,
            leakage_i_by_device=data.leakage_i_by_device,
            v_read=data.v_read,
        )
        for fig in stack_figs:
            pid = fig.layout.meta.get("param_id")
            _write(fig, stack_dir / f"{pid}.html")
            _write_json(fig, stack_dir / f"{pid}.json")

    write_stack_level_boxplots()

    # Correlation scatter
    def write_correlation_scatter_figs():
        stack_corr_dir = cfg.output_dir / "correlation_plots_stack_level"
        stack_corr_dir.mkdir(parents=True, exist_ok=True)

        stack_corr_figs = build_stack_level_correlation_figs(
            scatter_df=data.scatter_df,
            stack_id=stack_id,
            devices=devices,
            forming_v_by_device=data.forming_v_by_device,
            leakage_i_by_device=data.leakage_i_by_device,
            first_v_reset=data.first_v_reset,
            v_read=data.v_read,
        )
        for fig in stack_corr_figs:
            pid = fig.layout.meta.get("param_id")
            _write(fig, stack_corr_dir / f"{pid}.html")
            _write_json(fig, stack_corr_dir / f"{pid}.json")

    write_correlation_scatter_figs()

    # Correlation matrix
    def write_correlation_matrix_figs():
        stack_matrix_dir = cfg.output_dir / "correlation_matrices_stack_level"
        stack_matrix_dir.mkdir(parents=True, exist_ok=True)

        stack_matrix_figs = build_stack_level_correlation_matrix_figs(
            scatter_df=data.scatter_df,
            stack_id=stack_id,
            devices=devices,
            forming_v_by_device=data.forming_v_by_device,
            leakage_i_by_device=data.leakage_i_by_device,
            first_v_reset=data.first_v_reset,
            v_read=data.v_read,
        )
        for fig in stack_matrix_figs:
            pid = fig.layout.meta.get("param_id")
            _write(fig, stack_matrix_dir / f"{pid}.html")
            _write_json(fig, stack_matrix_dir / f"{pid}.json")

    write_correlation_matrix_figs()

    # Spatial stack map
    def write_stack_level_spatial_maps():
        spatial_dir = cfg.output_dir / "spatial_maps_stack_level"
        spatial_dir.mkdir(parents=True, exist_ok=True)

        spatial_figs = build_stack_level_spatial_maps(
            box_table=data.box_table,
            stack_id=stack_id,
            devices=devices,
        )
        for fig in spatial_figs:
            pid = fig.layout.meta.get("param_id")
            _write(fig, spatial_dir / f"{pid}.html")
            _write_json(fig, spatial_dir / f"{pid}.json")

    write_stack_level_spatial_maps()


def main() -> None:
    cfg = load_config()
    data = load_all(cfg)

    stack_id = data.stack_id
    devices = data.devices

    # create plots depending on mode
    if cfg.mode is Mode.DEVICE:
        plot_device(cfg, data, stack_id, devices)
    else:  # cfg.mode is Mode.STACK
        plot_stack(cfg, data, stack_id, devices)


if __name__ == "__main__":
    main()
