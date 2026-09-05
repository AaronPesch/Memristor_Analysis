"""Synthetic RRAM measurement data, held in an in-process DuckDB.

This stands in for the real import pipeline. The point of the demo is that the
database is queried *while the user interacts* -- not once, up front, to write
a pile of HTML files.
"""

from __future__ import annotations

import time

import duckdb
import numpy as np

ROWS, COLS = 6, 6
N_CYCLES = 200

# param key -> (label, unit, log-scale by default)
PARAMS: dict[str, tuple[str, str, bool]] = {
    "r_hrs": ("R_HRS", "Ohm", True),
    "r_lrs": ("R_LRS", "Ohm", True),
    "memory_window": ("Memory Window", "R_HRS / R_LRS", True),
    "v_set": ("V_set", "V", False),
    "v_reset": ("V_reset", "V", False),
}

# A few devices that degrade over cycling, so filtering them out is visible.
WEAK_DEVICES = {(0, 4), (1, 5), (4, 0), (5, 1), (5, 5)}


def device_id(row: int, col: int) -> str:
    return f"R{row + 1}C{col + 1}"


def build_connection(seed: int = 7) -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB holding one synthetic stack."""
    rng = np.random.default_rng(seed)
    cyc = np.arange(1, N_CYCLES + 1)
    chunks: dict[str, list[np.ndarray]] = {
        k: []
        for k in (
            "device",
            "drow",
            "dcol",
            "cycle",
            "v_set",
            "v_reset",
            "r_lrs",
            "r_hrs",
        )
    }

    for r in range(ROWS):
        for c in range(COLS):
            # Spatial gradient across the stack: HRS and V_set rise towards the
            # top-right corner. This is what makes the spatial map worth looking at.
            grad = 0.35 * (r / (ROWS - 1)) + 0.55 * (c / (COLS - 1))
            weak = (r, c) in WEAK_DEVICES

            r_hrs = np.exp(rng.normal(np.log(1.0e5 * (1 + 0.9 * grad)), 0.22, N_CYCLES))
            r_lrs = np.exp(rng.normal(np.log(5.0e3 * (1 + 0.2 * grad)), 0.13, N_CYCLES))
            v_set = rng.normal(1.15 + 0.30 * grad, 0.085, N_CYCLES)
            v_reset = rng.normal(-0.95 - 0.20 * grad, 0.075, N_CYCLES)

            if weak:
                # Window collapses as cycling proceeds.
                decay = np.exp(-cyc / 90.0)
                r_hrs *= 0.18 + 0.82 * decay
                v_set += 0.22 * (1 - decay)

            chunks["device"].append(np.full(N_CYCLES, device_id(r, c)))
            chunks["drow"].append(np.full(N_CYCLES, r))
            chunks["dcol"].append(np.full(N_CYCLES, c))
            chunks["cycle"].append(cyc)
            chunks["v_set"].append(v_set)
            chunks["v_reset"].append(v_reset)
            chunks["r_lrs"].append(r_lrs)
            chunks["r_hrs"].append(r_hrs)

    # Hand DuckDB whole columns, not rows. Row-by-row INSERT of these 7 200
    # rows takes ~57 s; this takes ~6 ms.
    columns = {name: np.concatenate(parts) for name, parts in chunks.items()}
    con = duckdb.connect()
    con.register("generated", columns)
    con.execute(
        """
        CREATE TABLE cycles AS SELECT
            device::VARCHAR AS device, drow::INTEGER AS drow, dcol::INTEGER AS dcol,
            cycle::INTEGER AS cycle, v_set, v_reset, r_lrs, r_hrs
        FROM generated
        """
    )
    con.unregister("generated")
    return con


def _expr(param: str) -> str:
    """SQL expression for a parameter (memory window is derived)."""
    if param == "memory_window":
        return "(r_hrs / r_lrs)"
    return param


class Store:
    """Every method here runs a fresh query. Nothing is precomputed to disk."""

    def __init__(self, seed: int = 7) -> None:
        self.con = build_connection(seed)
        self.last_query_ms = 0.0
        self.devices = [device_id(r, c) for r in range(ROWS) for c in range(COLS)]

    def _run(self, sql: str, args: list | None = None) -> list[tuple]:
        t0 = time.perf_counter()
        out = self.con.execute(sql, args or []).fetchall()
        self.last_query_ms += (time.perf_counter() - t0) * 1000
        return out

    def begin_timing(self) -> None:
        self.last_query_ms = 0.0

    def _cycle_clause(self, cycles: tuple[int, int]) -> tuple[str, list]:
        return "cycle BETWEEN ? AND ?", [int(cycles[0]), int(cycles[1])]

    def spatial(self, param: str, cycles: tuple[int, int]) -> list[tuple]:
        """Median parameter value per physical device position."""
        where, args = self._cycle_clause(cycles)
        return self._run(
            f"""SELECT drow, dcol, device, median({_expr(param)}) AS val
                FROM cycles WHERE {where}
                GROUP BY drow, dcol, device ORDER BY drow, dcol""",
            args,
        )

    def scatter(self, cycles: tuple[int, int]) -> list[tuple]:
        """One point per cycle: V_set against V_reset."""
        where, args = self._cycle_clause(cycles)
        return self._run(
            f"""SELECT device, abs(v_set), abs(v_reset) FROM cycles
                WHERE {where} ORDER BY device, cycle""",
            args,
        )

    def values(
        self, param: str, devices: list[str], cycles: tuple[int, int]
    ) -> np.ndarray:
        """Flat parameter values, optionally restricted to a device selection."""
        where, args = self._cycle_clause(cycles)
        if devices:
            placeholders = ", ".join("?" * len(devices))
            where += f" AND device IN ({placeholders})"
            args = args + list(devices)
        rows = self._run(f"SELECT {_expr(param)} FROM cycles WHERE {where}", args)
        return np.asarray([r[0] for r in rows], dtype=float)

    def endurance(self, param: str, devices: list[str]) -> list[tuple]:
        """Mean parameter value per cycle, plus the spread across devices."""
        args: list = []
        where = "TRUE"
        if devices:
            placeholders = ", ".join("?" * len(devices))
            where = f"device IN ({placeholders})"
            args = list(devices)
        return self._run(
            f"""SELECT cycle, avg({_expr(param)}), quantile_cont({_expr(param)}, 0.1),
                       quantile_cont({_expr(param)}, 0.9)
                FROM cycles WHERE {where} GROUP BY cycle ORDER BY cycle""",
            args,
        )
