"""What the user is told when an import produces nothing usable.

Two very different causes end in the same message -- the selected folder held no
measurement files, or the files could not be read at all. Only the converter's
per-file output separates them, and that output used to be discarded on the
failure path, which left a report stating the symptom and nothing else.
"""

from __future__ import annotations

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

    # The symptom, as before.
    assert "contains no data" in report
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
