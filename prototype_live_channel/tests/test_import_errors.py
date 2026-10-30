"""What the user is told when an import produces nothing usable.

Two very different causes end in the same message -- the selected folder held no
measurement files, or the files could not be read at all. Only the converter's
per-file output separates them, and that output used to be discarded on the
failure path, which left a report stating the symptom and nothing else.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import xlsxwriter

import channel
from app.core.modes import Mode

ROWS = "[1/3] 03 endurance set.xlsx: 6,420 rows (0.41s)"
META = "[2/3] 01 notes.xlsx: metadata only (0.02s)"
ERROR = "[3/3] 02 reset.xlsx: ERROR - Fatal error: could not open file"


# ── reading the converter output ─────────────────────────────────────────────


def test_counts_each_outcome():
    text = channel.diagnose_import("\n".join([ROWS, META, ERROR]))
    assert "3 file(s) read: 1 with cycle data, 1 metadata only, 1 unreadable." in text


def test_nothing_to_say_about_an_empty_log():
    assert channel.diagnose_import("") == ""
    assert channel.diagnose_import("BATCH PROCESSING: 3 Excel files\n") == ""


def test_a_healthy_import_gets_no_hints():
    text = channel.diagnose_import(ROWS)
    assert "1 with cycle data" in text
    assert "Run1" not in text
    assert "OneDrive" not in text


# ── the two causes, told apart ───────────────────────────────────────────────


def test_no_run_sheets_points_at_the_folder():
    text = channel.diagnose_import("\n".join([META, META]))
    assert "Run1, Run2" in text
    assert "not the one holding the measurements" in text
    assert "OneDrive" not in text


def test_unreadable_files_point_at_placeholders():
    text = channel.diagnose_import("\n".join([ERROR, ERROR]))
    assert "OneDrive" in text
    assert "Always keep on this device" in text
    assert "could not open file" in text


def test_failing_files_are_named_but_capped():
    log = "\n".join(f"[{i}/9] file{i}.xlsx: ERROR - broken" for i in range(1, 10))
    text = channel.diagnose_import(log)
    assert "file1.xlsx" in text
    assert "and 4 more" in text


def test_lines_the_converter_did_not_write_are_ignored():
    noise = "Combining data from 7 files...\nCreated 'cycles' table with 5 rows\n"
    assert channel.diagnose_import(noise + ROWS).startswith("1 file(s) read")


# ── the report the dialog actually shows ─────────────────────────────────────


@pytest.fixture
def folder_without_measurements(tmp_path):
    """One spreadsheet with no Run sheets -- what picking the wrong folder looks
    like to the importer."""
    folder = tmp_path / "not_a_device"
    folder.mkdir()
    book = xlsxwriter.Workbook(str(folder / "01 notes.xlsx"))
    book.add_worksheet("Tabelle1").write(0, 0, "something")
    book.close()
    return folder


def test_the_failure_report_explains_itself(
    folder_without_measurements, tmp_path, monkeypatch
):
    monkeypatch.setattr(channel, "DB_FILE", tmp_path / "empty.duckdb")
    worker = channel.ImportWorker(folder_without_measurements, Mode.DEVICE)

    reports: list[str] = []
    worker.failed.connect(reports.append)
    worker.finished.connect(lambda *_: reports.append("UNEXPECTED SUCCESS"))
    worker.run()

    assert len(reports) == 1, reports
    report = reports[0]

    # The guard in the worker reports this before load_all gets to complain
    # about an empty database, and says it in terms of the selected folder.
    assert "added no measurement data from the selected folder" in report
    # What is new: the cause, the evidence, and the traceback, in that order.
    assert "What the import produced:" in report
    assert "0 with cycle data, 1 metadata only" in report
    assert "Import log:" in report
    assert "01 notes.xlsx" in report
    assert report.index("What the import produced:") < report.index("Traceback")


def test_the_first_line_is_the_headline(
    folder_without_measurements, tmp_path, monkeypatch
):
    """on_import_failed shows splitlines()[0] as the dialog's main text."""
    monkeypatch.setattr(channel, "DB_FILE", tmp_path / "empty.duckdb")
    worker = channel.ImportWorker(folder_without_measurements, Mode.DEVICE)
    reports: list[str] = []
    worker.failed.connect(reports.append)
    worker.run()

    assert reports[0].splitlines()[0].strip()
    assert "Traceback" not in reports[0].splitlines()[0]


# ── when nothing was found at all ────────────────────────────────────────────


def test_a_folder_with_no_spreadsheets_lists_what_is_there(tmp_path):
    folder = tmp_path / "D12"
    folder.mkdir()
    (folder / "calendar.pdf").write_bytes(b"%PDF-1.4")

    text = channel.diagnose_selection(folder, Mode.DEVICE)
    assert "0 .xlsx file(s) directly" in text
    assert "no Excel files anywhere below" in text
    assert "calendar.pdf" in text


def test_a_stack_folder_picked_for_a_device_import_says_so(tmp_path):
    """The most common mistake: a device import only looks at the top level."""
    stack = tmp_path / "STACK#1"
    for device in ("A1", "A2"):
        (stack / device).mkdir(parents=True)
        (stack / device / "03 endurance set.xlsx").write_bytes(b"x")

    text = channel.diagnose_selection(stack, Mode.DEVICE)
    assert "2 in subfolders" in text
    assert "Ctrl+Shift+O" in text
    assert "A1" in text and "A2" in text


def test_a_correct_device_folder_gets_no_complaint(tmp_path):
    folder = tmp_path / "A1"
    folder.mkdir()
    (folder / "03 endurance set.xlsx").write_bytes(b"x")

    text = channel.diagnose_selection(folder, Mode.DEVICE)
    assert "1 .xlsx file(s) directly" in text
    assert "no Excel files anywhere" not in text
    assert "Ctrl+Shift+O" not in text


def test_temporary_excel_files_are_not_counted(tmp_path):
    folder = tmp_path / "A1"
    folder.mkdir()
    (folder / "~$03 endurance set.xlsx").write_bytes(b"x")

    text = channel.diagnose_selection(folder, Mode.DEVICE)
    assert "0 .xlsx file(s) directly" in text


def test_a_vanished_or_wrong_path_is_named(tmp_path):
    assert "does not exist" in channel.diagnose_selection(tmp_path / "gone", Mode.STACK)

    a_file = tmp_path / "sheet.xlsx"
    a_file.write_bytes(b"x")
    assert "is a file, not a folder" in channel.diagnose_selection(a_file, Mode.DEVICE)


def test_the_report_falls_back_to_the_folder_when_nothing_was_read(
    tmp_path, monkeypatch
):
    """No files found means no per-file log, so the folder is what gets
    explained -- this is the 'No Excel files found matching' case."""
    folder = tmp_path / "D12"
    folder.mkdir()
    (folder / "calendar.pdf").write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(channel, "DB_FILE", tmp_path / "empty.duckdb")

    worker = channel.ImportWorker(folder, Mode.DEVICE)
    reports: list[str] = []
    worker.failed.connect(reports.append)
    worker.run()

    report = reports[0]
    assert "No Excel files found matching" in report
    assert "What the selected folder contains:" in report
    assert "calendar.pdf" in report
    assert "What the import produced:" not in report


# ── an unreadable file does not announce itself as an error ──────────────────

# This is what the converter really prints for a file it cannot open: the
# per-file line says "metadata only", because ExcelFileProcessor catches the
# exception and the converter only sees zero rows. The cause appears at the end,
# in the warnings block. Reading only the per-file lines gives the opposite
# advice to the right one.
UNREADABLE_LOG = r"""\
[1/2] 03 endurance set.xlsx: metadata only (0.01s)
[2/2] 04 endurance reset.xlsx: metadata only (0.01s)

Warnings (2):
  - Fatal error: calamine error: Xlsx error: Zip error: invalid Zip archive
Context:
    0: Could not open workbook at C:\data\A1\03 endurance set.xlsx
    1: could not load excel file at C:\data\A1\03 endurance set.xlsx
  - Fatal error: calamine error: Xlsx error: Zip error: invalid Zip archive
Context:
    0: Could not open workbook at C:\data\A1\04 endurance reset.xlsx
    1: could not load excel file at C:\data\A1\04 endurance reset.xlsx
"""


def test_unreadable_files_are_not_counted_as_metadata():
    text = channel.diagnose_import(UNREADABLE_LOG)
    assert "0 with cycle data, 0 metadata only, 2 unreadable" in text


def test_unreadable_files_get_the_placeholder_hint_not_the_folder_hint():
    text = channel.diagnose_import(UNREADABLE_LOG)
    assert "OneDrive" in text
    assert "Run1, Run2" not in text, "this is not a wrong-folder problem"
    assert "03 endurance set.xlsx: could not be opened" in text


def test_a_real_metadata_only_file_still_gets_the_folder_hint():
    """The same per-file line, without a warnings block behind it."""
    text = channel.diagnose_import("[1/1] 01 notes.xlsx: metadata only (0.01s)")
    assert "0 with cycle data, 1 metadata only, 0 unreadable" in text
    assert "Run1, Run2" in text
    assert "OneDrive" not in text


def test_a_mixed_import_separates_the_two():
    log = UNREADABLE_LOG + "[3/3] 01 notes.xlsx: metadata only (0.01s)\n"
    text = channel.diagnose_import(log)
    assert "3 file(s) read: 0 with cycle data, 1 metadata only, 2 unreadable" in text
    assert "OneDrive" in text and "Run1, Run2" in text


# ── an import that contributes nothing must not pass off older data ──────────


def _valid_device(tmp_path, name="A1"):
    """A device folder the importer accepts, via the fixture generator."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    import numpy as np

    import make_fixtures

    staging = tmp_path / f"staging_{name}"
    make_fixtures.build_device(
        staging, name[0], int(name[1:]), 4, np.random.default_rng(3)
    )
    return staging / make_fixtures.STACK_ID / name


def test_rows_from_counts_only_the_selected_folder(tmp_path, monkeypatch):
    device = _valid_device(tmp_path)
    db = tmp_path / "db.duckdb"
    monkeypatch.setattr(channel, "DB_FILE", db)

    worker = channel.ImportWorker(device, Mode.DEVICE)
    worker.run()

    mine, total = channel.rows_from(db, device)
    assert mine > 0 and mine == total

    elsewhere, still_total = channel.rows_from(db, tmp_path / "somewhere_else")
    assert elsewhere == 0
    assert still_total == total


def test_rows_from_handles_a_database_that_is_not_there(tmp_path):
    assert channel.rows_from(tmp_path / "nope.duckdb", tmp_path) == (0, 0)


def test_a_second_import_that_parses_nothing_is_refused(tmp_path, monkeypatch):
    """The regression this guards: BatchConverter only replaces the cycles
    table when something parsed, so an import where nothing did leaves the
    previous one in place. The app then reported success and plotted the older
    measurements."""
    db = tmp_path / "db.duckdb"
    monkeypatch.setattr(channel, "DB_FILE", db)

    device = _valid_device(tmp_path)
    first = channel.ImportWorker(device, Mode.DEVICE)
    outcomes: list[str] = []
    first.finished.connect(lambda *_: outcomes.append("ok"))
    first.failed.connect(lambda m: outcomes.append("failed: " + m))
    first.run()
    assert outcomes == ["ok"], outcomes
    before, _ = channel.rows_from(db, device)
    assert before > 0

    empty = tmp_path / "nothing_useful"
    empty.mkdir()
    book = xlsxwriter.Workbook(str(empty / "01 notes.xlsx"))
    book.add_worksheet("Tabelle1").write(0, 0, "x")
    book.close()

    second = channel.ImportWorker(empty, Mode.DEVICE)
    reports: list[str] = []
    second.failed.connect(reports.append)
    second.finished.connect(lambda *_: reports.append("UNEXPECTED SUCCESS"))
    second.run()

    assert len(reports) == 1 and "UNEXPECTED SUCCESS" not in reports[0]
    assert "added no measurement data" in reports[0]
    assert "earlier import" in reports[0], "say that the old data is still loaded"
    # The old rows are still there -- that is the point; they are just not
    # presented as the new import.
    assert channel.rows_from(db, device)[0] == before


def test_a_good_import_replaces_the_previous_one(tmp_path, monkeypatch):
    db = tmp_path / "db.duckdb"
    monkeypatch.setattr(channel, "DB_FILE", db)

    first = _valid_device(tmp_path, "A1")
    channel.ImportWorker(first, Mode.DEVICE).run()
    second = _valid_device(tmp_path, "B2")
    worker = channel.ImportWorker(second, Mode.DEVICE)
    outcomes: list[str] = []
    worker.finished.connect(lambda *_: outcomes.append("ok"))
    worker.failed.connect(lambda m: outcomes.append("failed: " + m.splitlines()[0]))
    worker.run()

    assert outcomes == ["ok"], outcomes
    assert channel.rows_from(db, second)[0] > 0
    assert channel.rows_from(db, first)[0] == 0, "the earlier import is gone"
