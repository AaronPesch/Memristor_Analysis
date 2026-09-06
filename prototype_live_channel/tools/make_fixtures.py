r"""Generate synthetic measurement data in the layout the importer expects.

    <root>/<stack_id>/<device>/<NN type>.xlsx

Device folders follow ^([A-Za-z]+)(\d+)$ so the stack map can place them, and
file names follow ^(\d{2})\s+(.+)\.xlsx?$ so the measurement type is parsed.
Cycle data lives in Run1..RunN sheets; anything else becomes a metadata table.

Usage:  python tools/make_fixtures.py <output_dir> [--devices 16] [--cycles 30]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import xlsxwriter

STACK_ID = "SC20251208#4a"
ROWS = ["A", "B", "C", "D"]
COLS = [1, 2, 3, 4]
SWEEP_POINTS = 40
V_READ = 0.2


def _write(path: Path, sheets: dict[str, tuple[list[str], np.ndarray]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    book = xlsxwriter.Workbook(str(path), {"nan_inf_to_errors": True})
    for sheet_name, (headers, data) in sheets.items():
        sheet = book.add_worksheet(sheet_name)
        for c, head in enumerate(headers):
            sheet.write(0, c, head)
        for r in range(data.shape[0]):
            for c in range(data.shape[1]):
                sheet.write_number(r + 1, c, float(data[r, c]))
    book.close()


def _sweep(rng, v_peak: float, r_on: float, r_off: float, n: int) -> np.ndarray:
    """A crude bipolar I-V sweep: high resistance until v_peak, then low."""
    v = np.concatenate(
        [np.linspace(0, v_peak, n // 2), np.linspace(v_peak, 0, n - n // 2)]
    )
    switched = np.arange(v.size) >= v.size // 2
    r = np.where(switched, r_on, r_off)
    i = v / r * rng.normal(1.0, 0.03, v.size)
    return np.column_stack([np.arange(v.size, dtype=float), v, i])


def build_device(root: Path, row: str, col: int, cycles: int, rng) -> None:
    device_dir = root / STACK_ID / f"{row}{col}"

    # Spatial gradient, so the stack map shows structure rather than noise.
    grad = 0.35 * (ROWS.index(row) / (len(ROWS) - 1)) + 0.55 * (
        (col - 1) / (len(COLS) - 1)
    )
    weak = (row, col) in {("A", 4), ("D", 1), ("D", 4)}

    r_lrs = np.exp(rng.normal(np.log(5.0e3 * (1 + 0.2 * grad)), 0.13, cycles))
    r_hrs = np.exp(rng.normal(np.log(1.0e5 * (1 + 0.9 * grad)), 0.22, cycles))
    v_set = rng.normal(1.15 + 0.30 * grad, 0.085, cycles)
    v_reset = rng.normal(-0.95 - 0.20 * grad, 0.075, cycles)
    if weak:
        decay = np.exp(-np.arange(1, cycles + 1) / (cycles / 3))
        r_hrs *= 0.18 + 0.82 * decay

    i_lrs = V_READ / r_lrs
    i_hrs = V_READ / r_hrs
    i_reset = -np.abs(rng.normal(2.0e-4, 2e-5, cycles))

    # 03 endurance set -- drives characteristic, CDF, boxplots, endurance
    set_sheets = {}
    for k in range(cycles):
        sweep = _sweep(
            rng, float(v_set[k]), float(r_lrs[k]), float(r_hrs[k]), SWEEP_POINTS
        )
        n = sweep.shape[0]
        norm_cond = np.abs(sweep[:, 2]) / max(abs(float(i_lrs[k])), 1e-12)
        block = np.column_stack(
            [
                sweep,  # Time, AV, AI
                np.full(n, v_set[k]),  # VSET
                np.full(n, i_lrs[k]),  # ILRS
                np.full(n, i_hrs[k]),  # IHRS
                norm_cond,  # NORM_COND
            ]
        )
        set_sheets[f"Run{k + 1}"] = (
            ["Time", "AV", "AI", "VSET", "ILRS", "IHRS", "NORM_COND"],
            block,
        )
    _write(device_dir / "03 endurance set.xlsx", set_sheets)

    # 04 endurance reset -- drives V_reset and I_reset_max
    reset_sheets = {}
    for k in range(cycles):
        sweep = _sweep(
            rng, float(v_reset[k]), float(r_hrs[k]), float(r_lrs[k]), SWEEP_POINTS
        )
        n = sweep.shape[0]
        block = np.column_stack(
            [
                sweep,
                np.full(n, v_reset[k]),  # VRESET
                np.full(n, i_reset[k]),  # IRESET
                np.abs(sweep[:, 2]) / max(abs(float(i_lrs[k])), 1e-12),
            ]
        )
        reset_sheets[f"Run{k + 1}"] = (
            ["Time", "AV", "AI", "VRESET", "IRESET", "NORM_COND"],
            block,
        )
    _write(device_dir / "04 endurance reset.xlsx", reset_sheets)

    # 01 electroforming -- one shot, VFORM is read with MAX()
    v_form = 2.4 + 0.6 * grad + rng.normal(0, 0.05)
    n = SWEEP_POINTS
    form = _sweep(rng, float(v_form), 4.0e3, 5.0e6, n)
    _write(
        device_dir / "01 electroforming.xlsx",
        {
            "Run1": (
                ["Time", "AV", "AI", "VFORM"],
                np.column_stack([form, np.full(n, v_form)]),
            ),
            "Settings": (["compliance_A", "step_V"], np.array([[1e-3, 0.02]])),
        },
    )

    # 02 leakage -- pristine leakage current and the read voltage V_read
    i_leak = np.abs(rng.normal(1.5e-9 * (1 + 3 * grad), 2e-10, n))
    _write(
        device_dir / "02 leakage.xlsx",
        {
            "Run1": (
                ["Time", "AV", "AI", "ILEAKAGE"],
                np.column_stack(
                    [np.arange(n, dtype=float), np.full(n, V_READ), i_leak, i_leak]
                ),
            ),
        },
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("output", type=Path)
    ap.add_argument("--cycles", type=int, default=30)
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    made = 0
    for row in ROWS:
        for col in COLS:
            build_device(args.output, row, col, args.cycles, rng)
            made += 1
    print(f"wrote {made} devices x 4 files under {args.output / STACK_ID}")


if __name__ == "__main__":
    main()
