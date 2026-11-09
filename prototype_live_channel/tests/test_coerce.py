"""One non-numeric cell used to take down a whole stack.

A colleague's 626-file import died on

    ArrowNotImplementedError: Function 'abs_checked' has no kernel matching
    input types (large_string)

while the same devices imported fine one at a time. The cause is the
combination of `pl.concat(..., how="diagonal_relaxed")` in the converter, which
promotes a column to String as soon as one file disagrees about its type, and
the unguarded `.abs()` calls in `app/plotting/transforms.py`. A single device
has nothing to be promoted against, which is why only the stack broke.

These tests pin down the mechanism, the crash, and the repair.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import duckdb
import pytest

import coerce
import dashboard_data
from app.converter.batch import BatchConverter
from app.converter.convert_path_to_glob import path_to_glob
from app.core.modes import Mode
from app.plotting.config import Config
from app.plotting.pipeline import load_all

BAD_VALUE = "#REF!"


def _taint(workbook: Path, column: str, value: str = BAD_VALUE) -> None:
    """Rewrite one workbook so a single cell of `column` holds text."""
    import fastexcel
    import xlsxwriter

    reader = fastexcel.read_excel(workbook)
    sheets = {
        name: reader.load_sheet_by_name(name).to_polars() for name in reader.sheet_names
    }

    book = xlsxwriter.Workbook(str(workbook))
    for name, frame in sheets.items():
        sheet = book.add_worksheet(name)
        for c, head in enumerate(frame.columns):
            sheet.write(0, c, head)
        for r, row in enumerate(frame.rows()):
            for c, cell in enumerate(row):
                if name == "Run1" and r == 0 and frame.columns[c] == column:
                    sheet.write_string(r + 1, c, value)
                else:
                    sheet.write_number(r + 1, c, float(cell))
    book.close()


def _column_type(db: Path, column: str) -> str:
    with duckdb.connect(str(db), read_only=True) as conn:
        return conn.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'cycles' AND column_name = ?",
            [column],
        ).fetchone()[0]


@pytest.fixture(scope="session")
def tainted_stack(synthetic_stack, tmp_path_factory) -> Path:
    """A copy of the synthetic stack with one text cell in one IRESET column."""
    root = tmp_path_factory.mktemp("tainted")
    stack = root / synthetic_stack.name
    shutil.copytree(synthetic_stack, stack)
    _taint(stack / "B2" / "03 endurance reset.xlsx", "IRESET")
    return stack


@pytest.fixture(scope="session")
def tainted_db(tainted_stack, tmp_path_factory) -> Path:
    db = tmp_path_factory.mktemp("tainted_db") / "stack.duckdb"
    BatchConverter(db).convert(path_to_glob(tainted_stack, Mode.STACK))
    return db


@pytest.fixture
def repairable_db(tainted_db, tmp_path) -> Path:
    """A writable copy, so every test repairs from the same starting point."""
    db = tmp_path / "repairable.duckdb"
    shutil.copy(tainted_db, db)
    return db


# ── the mechanism ────────────────────────────────────────────────────────────


def test_one_text_cell_promotes_the_whole_column(tainted_db):
    """16 devices, one bad cell, and every device's IRESET becomes text."""
    assert _column_type(tainted_db, "IRESET") == "VARCHAR"


def test_a_clean_import_keeps_its_columns_numeric(stack_db):
    assert _column_type(stack_db, "IRESET") == "DOUBLE"


def test_the_untouched_columns_stay_numeric(tainted_db):
    """Promotion is per column -- it does not spread."""
    assert _column_type(tainted_db, "VRESET") == "DOUBLE"


def test_the_pipeline_dies_on_the_text_column(tainted_db):
    """The colleague's crash, reproduced end to end."""
    cfg = Config(db_file=tainted_db, output_dir=tainted_db.parent, mode=Mode.STACK)
    with pytest.raises(Exception, match="abs_checked"):
        load_all(cfg)


# ── the repair ───────────────────────────────────────────────────────────────


def test_a_clean_database_needs_no_repair(stack_db, tmp_path):
    db = tmp_path / "clean.duckdb"
    shutil.copy(stack_db, db)
    assert coerce.repair_cycles(db) == []


def test_repair_makes_the_column_numeric_again(repairable_db):
    coerce.repair_cycles(repairable_db)
    assert _column_type(repairable_db, "IRESET") == "DOUBLE"


def test_repair_lets_the_pipeline_finish(repairable_db):
    coerce.repair_cycles(repairable_db)
    cfg = Config(
        db_file=repairable_db, output_dir=repairable_db.parent, mode=Mode.STACK
    )
    data = load_all(cfg)
    assert len(data.devices) == 16


def test_repair_reports_what_it_dropped(repairable_db):
    (report,) = coerce.repair_cycles(repairable_db)
    assert report.column == "IRESET"
    assert report.repaired
    assert report.discarded == 1
    assert report.values > 1
    assert report.examples == [BAD_VALUE]


def test_repair_names_the_device_and_the_file(repairable_db):
    (report,) = coerce.repair_cycles(repairable_db)
    assert report.devices == ["B2"]
    # The bare file name is shared by every device, so the folder must be there.
    assert "B2/03 endurance reset.xlsx" in coerce.describe(report)
    assert BAD_VALUE in coerce.describe(report)


def test_repair_keeps_the_good_values(repairable_db):
    """Only the unparseable cell goes; every other value survives the cast."""
    before = coerce.repair_cycles(repairable_db)[0]
    with duckdb.connect(str(repairable_db), read_only=True) as conn:
        kept = conn.execute("SELECT count(IRESET) FROM cycles").fetchone()[0]
    assert kept == before.values - before.discarded


def test_repair_is_idempotent(repairable_db):
    coerce.repair_cycles(repairable_db)
    assert coerce.repair_cycles(repairable_db) == []


def test_intended_text_columns_are_left_alone(repairable_db):
    coerce.repair_cycles(repairable_db)
    for column in ("device_id", "source_file", "stack_id", "measurement_type"):
        assert _column_type(repairable_db, column) == "VARCHAR"


def test_a_column_of_pure_text_is_not_nulled(repairable_db):
    """Nothing in it parses, so it is not a measurement column.

    Casting would replace every value with NULL and destroy information
    instead of recovering any, so the column is reported and left alone.
    """
    with duckdb.connect(str(repairable_db)) as conn:
        conn.execute("ALTER TABLE cycles ADD COLUMN note VARCHAR")
        conn.execute("UPDATE cycles SET note = 'checked'")

    reports = {r.column: r for r in coerce.repair_cycles(repairable_db)}
    assert not reports["note"].repaired
    assert _column_type(repairable_db, "note") == "VARCHAR"
    assert "left as it is" in coerce.describe(reports["note"])


# ── what the user is told ────────────────────────────────────────────────────


def test_dropped_values_reach_the_data_quality_panel(repairable_db):
    repairs = coerce.repair_cycles(repairable_db)
    (finding,) = dashboard_data.findings_from_repairs(repairs)
    assert finding.severity == "warning"
    assert "IRESET" in finding.title
    assert finding.devices == ["B2"]


def test_an_unrepairable_column_is_an_error(repairable_db):
    with duckdb.connect(str(repairable_db)) as conn:
        conn.execute("ALTER TABLE cycles ADD COLUMN note VARCHAR")
        conn.execute("UPDATE cycles SET note = 'checked'")

    severities = {
        finding.title.split(":")[0]: finding.severity
        for finding in dashboard_data.findings_from_repairs(
            coerce.repair_cycles(repairable_db)
        )
    }
    assert severities["note"] == "error"


def test_a_clean_import_adds_no_findings(stack_db, tmp_path):
    db = tmp_path / "clean.duckdb"
    shutil.copy(stack_db, db)
    assert dashboard_data.findings_from_repairs(coerce.repair_cycles(db)) == []


# ── the gap that hid all of this ─────────────────────────────────────────────


def test_the_fixtures_pair_set_with_reset(stack_data):
    """build_endurance_table finds a set file's reset partner by renaming it.

    The fixtures used to write `03 endurance set` beside `04 endurance reset`,
    so the partner was never found, I_LRS was always NaN, and no test ever
    reached the `.abs()` that the colleague's import died on.
    """
    table = stack_data.box_table
    assert "I_LRS" in table.columns
    assert table["I_LRS"].notna().any(), "I_LRS is empty -- set/reset never paired"
