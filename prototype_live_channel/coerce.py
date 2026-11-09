"""Repair measurement columns that arrived as text.

One non-numeric cell -- `#REF!`, a stray unit, a comma as decimal separator --
anywhere in a column is enough to make `pl.concat(..., how="diagonal_relaxed")`
promote that column to String for *every* file in the import. DuckDB stores it
as VARCHAR, pandas reads it back as an Arrow string, and the first `.abs()` in
`transforms.py` raises

    ArrowNotImplementedError: Function 'abs_checked' has no kernel matching
    input types (large_string)

So one bad cell in one device's reset file takes down a whole stack, while that
device on its own imports fine -- a single-file import has nothing to be
promoted against.

The converter already guards exactly this, for exactly one column:
`SheetProcessor.fix_norm_cond` strips `#REF` out of NORM_COND and casts back to
Float64. The other eighteen measurement columns are unguarded.

Rather than change the converter, this repairs the table afterwards. Each
affected column is cast back to DOUBLE with TRY_CAST, so unparseable cells
become NULL -- which is what the pipeline's own `.notna()` filters already
expect -- and what had to be discarded is reported, because silently dropping
measured values is worse than crashing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import duckdb

# Columns of `cycles` that hold text because they are meant to.
KNOWN_TEXT = frozenset(
    {
        "source_file",
        "stack_id",
        "device_id",
        "device_row",
        "measurement_type",
        "file_path",
        "ID",
    }
)

MAX_EXAMPLES = 4
MAX_FILES = 6


@dataclass
class Repair:
    """What one column lost on its way back to being numeric."""

    column: str
    values: int = 0
    discarded: int = 0
    examples: list[str] = field(default_factory=list)
    devices: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    repaired: bool = False

    @property
    def total_files(self) -> int:
        return len(self.files)


def text_columns(conn) -> list[str]:
    """Columns of `cycles` holding text that nothing is supposed to hold."""
    rows = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'cycles' AND data_type = 'VARCHAR'
        ORDER BY ordinal_position
        """
    ).fetchall()
    return [name for (name,) in rows if name not in KNOWN_TEXT]


def inspect(conn, column: str) -> Repair:
    """Count and name what TRY_CAST would not be able to parse."""
    col = f'"{column}"'
    bad = f"{col} IS NOT NULL AND TRY_CAST({col} AS DOUBLE) IS NULL"

    values, discarded = conn.execute(
        f"""
        SELECT count({col}),
               count({col}) - count(TRY_CAST({col} AS DOUBLE))
        FROM cycles
        """
    ).fetchone()

    examples = [
        value
        for (value,) in conn.execute(
            f"SELECT DISTINCT {col} FROM cycles WHERE {bad} ORDER BY 1 LIMIT {MAX_EXAMPLES}"
        ).fetchall()
    ]
    # device_row || device_col, not device_id: the rest of the dashboard names
    # devices "B2", and selection highlighting matches on that form.
    devices = [
        device
        for (device,) in conn.execute(
            "SELECT DISTINCT device_row || CAST(device_col AS VARCHAR) "
            f"FROM cycles WHERE {bad} AND device_row IS NOT NULL ORDER BY 1"
        ).fetchall()
    ]
    files = [
        path
        for (path,) in conn.execute(
            f"SELECT DISTINCT file_path FROM cycles WHERE {bad} ORDER BY 1"
        ).fetchall()
    ]

    return Repair(
        column=column,
        values=int(values),
        discarded=int(discarded),
        examples=examples,
        devices=devices,
        files=files,
    )


def repair_cycles(db_file: Path) -> list[Repair]:
    """Cast every text measurement column of `cycles` back to DOUBLE.

    Returns one `Repair` per column that was text, whether or not it could be
    repaired. A column in which nothing at all parses as a number is left
    alone: it is not a measurement column, and nulling it whole would destroy
    information rather than recover any.
    """
    found: list[Repair] = []
    with duckdb.connect(str(db_file)) as conn:
        for column in text_columns(conn):
            report = inspect(conn, column)
            if report.discarded < report.values:
                conn.execute(
                    f'ALTER TABLE cycles ALTER COLUMN "{column}" '
                    f'TYPE DOUBLE USING TRY_CAST("{column}" AS DOUBLE)'
                )
                report.repaired = True
            found.append(report)
    return found


def _locate(file_path: str) -> str:
    """`B2/03 endurance reset.xlsx` -- enough to find it in the folder tree."""
    path = Path(file_path)
    return f"{path.parent.name}/{path.name}" if path.parent.name else path.name


def describe(report: Repair) -> str:
    """One sentence saying what happened to a column, for the error box."""
    if not report.repaired:
        return (
            f"{report.column} holds text in all {report.values:,} rows and was "
            "left as it is; nothing in it reads as a number."
        )
    shown = ", ".join(repr(e) for e in report.examples)
    more = (
        f" and {report.total_files - MAX_FILES} more"
        if report.total_files > MAX_FILES
        else ""
    )
    # The bare file name is the same for every device, so the device folder
    # it sits in is the part that actually locates it.
    where = ", ".join(_locate(f) for f in report.files[:MAX_FILES])
    return (
        f"{report.column}: {report.discarded:,} of {report.values:,} values "
        f"could not be read as numbers ({shown}) and were dropped. "
        f"From: {where}{more}."
    )
