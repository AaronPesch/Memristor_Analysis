from __future__ import annotations

from dataclasses import dataclass
import pandas as pd
import duckdb


@dataclass(frozen=True)
class MemristorRepository:
    """
    Data access layer: SQL -> pandas DataFrames.
    No plotting, no transforms (groupby/apply/merge) beyond what SQL returns.
    """

    conn: duckdb.DuckDBPyConnection

    def get_stack_id(self) -> str | None:
        row = self.conn.execute(
            "SELECT DISTINCT stack_id FROM cycles LIMIT 1"
        ).fetchone()
        return row[0] if row else None

    def list_devices(self) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT device_row || CAST(device_col AS VARCHAR) AS device
            FROM cycles
            WHERE device_row IS NOT NULL
            ORDER BY device
            """
        ).fetchall()
        return [r[0] for r in rows]

    def list_endurance_sets(self, endurance_like: str = "%endurance_set%") -> list[str]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT source_file
            FROM cycles
            WHERE source_file ILIKE ?
            ORDER BY source_file
            """,
            [endurance_like],
        ).fetchall()
        return [r[0] for r in rows]

    def list_endurance_resets(
        self, endurance_reset_like: str = "%endurance_reset%"
    ) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT source_file
            FROM cycles
            WHERE source_file ILIKE ?
            ORDER BY source_file
            """,
            [endurance_reset_like],
        ).fetchall()
        return [r[0] for r in rows]

    def load_endurance_cycles_for_set(self, source_file: str) -> pd.DataFrame:
        """
        Raw data from endurance set files:
        cycle_number, Time, AV, AI, VSET, ILRS, IHRS
        """
        return self.conn.execute(
            """
            SELECT cycle_number, Time, AV, AI, VSET, ILRS, IHRS
            FROM cycles
            WHERE source_file = ?
            ORDER BY cycle_number, Time
            """,
            [source_file],
        ).df()

    def load_endurance_cycles_for_reset(self, source_file: str) -> pd.DataFrame:
        return self.conn.execute(
            """
            SELECT cycle_number, Time, AV, AI, VRESET, IRESET, NORM_COND
            FROM cycles
            WHERE source_file = ?
            ORDER BY cycle_number, Time
            """,
            [source_file],
        ).df()

    def load_cycles_for_set(self, source_file: str) -> pd.DataFrame:
        return self.conn.execute(
            """
            SELECT cycle_number, Time, AV, AI, NORM_COND
            FROM cycles
            WHERE source_file = ?
            ORDER BY cycle_number, Time
            """,
            [source_file],
        ).df()

    def load_forming_voltage_per_device(
        self,
        devices: list[str],
        electroforming_like: str = "%electroforming%",
    ) -> dict[str, float]:
        """
        Per-device forming voltage: MAX(VFORM) from each device's forming file.
        Returns {device: V_forming}.
        """
        result = {}
        for device in devices:
            df = self.conn.execute(
                """
                SELECT MAX(VFORM) AS vf
                FROM cycles
                WHERE source_file ILIKE ?
                  AND device_row || CAST(device_col AS VARCHAR) = ?
                """,
                [electroforming_like, device],
            ).df()
            if not df.empty:
                val = df["vf"].iloc[0]
                if not pd.isna(val):
                    result[device] = float(val)
        return result

    def load_leakage_current_per_device(
        self,
        devices: list[str],
        leakage_like: str = "%leakage%",
    ) -> dict[str, float]:
        """
        Per-device leakage current: MAX(ILEAKAGE) from each device's leakage file.
        Reads the pre-computed ILEAKAGE column directly.
        Returns {device: I_leakage_pristine}.
        """
        result = {}
        for device in devices:
            df = self.conn.execute(
                """
                SELECT MAX(ILEAKAGE) AS il
                FROM cycles
                WHERE source_file ILIKE ?
                  AND device_row || CAST(device_col AS VARCHAR) = ?
                """,
                [leakage_like, device],
            ).df()
            if not df.empty:
                val = df["il"].iloc[0]
                if not pd.isna(val):
                    result[device] = float(val)
        return result

    def load_v_read(self, leakage_like: str = "%leakage%") -> float:
        """
        Read voltage = ABS(AV) from the row where ILEAKAGE is set.
        Reads directly from the leakage file so V_read is not hardcoded.
        """
        df = self.conn.execute(
            """
            SELECT ABS(AV) AS v_read
            FROM cycles
            WHERE source_file ILIKE ?
              AND ILEAKAGE IS NOT NULL
            LIMIT 1
            """,
            [leakage_like],
        ).df()
        if df.empty or pd.isna(df["v_read"].iloc[0]):
            return 0.2  # fallback
        return float(df["v_read"].iloc[0])

    def load_first_v_reset(
        self, endurance_reset_like: str = "%endurance_reset%"
    ) -> dict[str, float]:
        """
        1st V_reset per device = VRESET from the very first reset cycle of the device.
        "First" = MIN(source_file) to get the earliest file, then MIN(cycle_number)
        within that file. Reads the pre-computed VRESET column directly.
        Returns: {device: first_v_reset}
        """
        df = self.conn.execute(
            """
            WITH device_first_file AS (
                SELECT device_row || CAST(device_col AS VARCHAR) AS device,
                       MIN(source_file) AS first_file
                FROM cycles
                WHERE source_file ILIKE ?
                GROUP BY device
            ),
            device_first_cycle AS (
                SELECT dff.device,
                       dff.first_file,
                       MIN(c.cycle_number) AS first_cn
                FROM cycles c
                JOIN device_first_file dff ON c.source_file = dff.first_file
                GROUP BY dff.device, dff.first_file
            )
            SELECT dfc.device,
                   MAX(c.VRESET) AS first_v_reset
            FROM cycles c
            JOIN device_first_cycle dfc
              ON c.source_file = dfc.first_file
             AND c.cycle_number = dfc.first_cn
            WHERE c.VRESET IS NOT NULL
            GROUP BY dfc.device
            """,
            [endurance_reset_like],
        ).df()

        if df.empty:
            return {}

        return {
            row["device"]: float(row["first_v_reset"])
            for _, row in df.iterrows()
            if not pd.isna(row["first_v_reset"]) and row["device"] is not None
        }

    def load_forming_voltage_global(
        self, electroforming_like: str = "%electroforming%"
    ) -> float | None:
        df = self.conn.execute(
            """
            SELECT MAX(VFORM) AS V_forming_global
            FROM cycles
            WHERE source_file ILIKE ?
            """,
            [electroforming_like],
        ).df()

        if df.empty:
            return None

        val = df["V_forming_global"].iloc[0]
        return None if pd.isna(val) else float(val)

    def load_classic_cycle_params_for_sets(
        self, sets: list[str], v_read: float = 0.2
    ) -> pd.DataFrame:
        """
        Per (source_file, cycle_number) classic params used by CDF/boxplots.
        R_LRS = v_read / I_LRS, R_HRS = v_read / I_HRS as per spec.
        """
        if not sets:
            return pd.DataFrame(
                columns=["source_file", "cycle_number", "VSET", "R_LRS", "R_HRS"]
            )

        return self.conn.execute(
            """
            SELECT source_file,
                   cycle_number,
                   MAX(VSET)                                               AS VSET,
                   MAX(ILRS)                                               AS I_LRS,
                   MAX(IHRS)                                               AS I_HRS,
                   ? / NULLIF(MAX(CAST(ILRS AS DOUBLE)), 0.0)             AS R_LRS,
                   ? / NULLIF(MAX(CAST(IHRS AS DOUBLE)), 0.0)             AS R_HRS
            FROM cycles
            WHERE source_file IN (SELECT * FROM UNNEST(?))
            GROUP BY source_file, cycle_number
            ORDER BY source_file, cycle_number
            """,
            [v_read, v_read, sets],
        ).df()
