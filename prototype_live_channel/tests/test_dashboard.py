"""Overview: key figures, the data-quality checks, and the rendered panel."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import dashboard_data
import dashboard_view


# ── key figures ──────────────────────────────────────────────────────────────


def test_stats_cover_the_expected_parameters(stack_data):
    stats = dashboard_data.build_stats(stack_data.box_table)
    labels = {s.label for s in stats}
    # V_reset and I_reset_max are deliberately not asserted: the synthetic
    # fixtures produce no valid per-device values for them, so they are absent
    # here and present on real measurements. Checking them would encode a
    # weakness of the fixtures as a requirement.
    assert {"V_set", "R_LRS", "R_HRS", "Memory Window"} <= labels
    for stat in stats:
        assert stat.n > 0
        assert stat.minimum <= stat.p10 <= stat.median <= stat.p90 <= stat.maximum


def test_cv_is_flagged_as_useless_when_outliers_dominate():
    """A CV past 100 % says nothing about the bulk on a decade-spanning
    parameter, and the table must mark it rather than present it as a figure."""
    import pandas as pd

    frame = pd.DataFrame({"R_HRS": [1e4] * 20 + [1e9]})
    stat = dashboard_data._stat_for(frame, "R_HRS", "R_HRS", "Ohm")
    assert stat.cv > 1.0
    assert stat.cv_is_meaningful is False

    tight = pd.DataFrame({"VSET": [1.2, 1.25, 1.18, 1.22, 1.21]})
    assert (
        dashboard_data._stat_for(tight, "VSET", "V_set", "V").cv_is_meaningful is True
    )


# ── data quality ─────────────────────────────────────────────────────────────


def _device_tree(root: Path, devices: dict[str, dict[str, bytes]]) -> Path:
    stack = root / "STACK#1"
    for device, files in devices.items():
        folder = stack / device
        folder.mkdir(parents=True, exist_ok=True)
        for name, payload in files.items():
            (folder / name).write_bytes(payload)
    return stack


def test_identical_devices_are_reported_as_one_cluster(tmp_path):
    """The check that would have caught a stack of copied measurement files.

    Reported per device cluster: one copied device appears in every one of its
    files, and a finding per file name buries the one that matters.
    """
    same = {"01 set.xlsx": b"AAA", "02 reset.xlsx": b"BBB"}
    stack = _device_tree(
        tmp_path,
        {
            "A1": dict(same),
            "A2": dict(same),
            "A3": dict(same),
            "B1": {"01 set.xlsx": b"CCC", "02 reset.xlsx": b"DDD"},
        },
    )

    findings = dashboard_data.find_duplicate_files(stack)
    clusters = [f for f in findings if f.severity == "error"]
    assert len(clusters) == 1, [f.title for f in findings]
    assert clusters[0].devices == ["A1", "A2", "A3"]
    assert "identical" in clusters[0].title


def test_distinct_devices_raise_nothing(tmp_path):
    stack = _device_tree(
        tmp_path,
        {
            "A1": {"01 set.xlsx": b"one"},
            "A2": {"01 set.xlsx": b"two"},
        },
    )
    assert dashboard_data.find_duplicate_files(stack) == []


def test_partially_shared_files_are_a_warning_not_an_error(tmp_path):
    stack = _device_tree(
        tmp_path,
        {
            "A1": {"01 set.xlsx": b"shared", "02 reset.xlsx": b"a"},
            "A2": {"01 set.xlsx": b"shared", "02 reset.xlsx": b"b"},
        },
    )
    findings = dashboard_data.find_duplicate_files(stack)
    assert [f.severity for f in findings] == ["warning"]
    assert set(findings[0].devices) == {"A1", "A2"}


def test_devices_without_a_grid_position_are_reported():
    findings = dashboard_data.find_position_gaps(["A1", "B2", "Temp_373K", "spare"])
    assert len(findings) == 1
    assert findings[0].devices == ["Temp_373K", "spare"]
    assert findings[0].severity == "warning"
    assert dashboard_data.find_position_gaps(["A1", "B2"]) == []


def test_import_warnings_are_lifted_out_of_the_converter_output():
    """BatchConverter prints its per-file warnings and returns only the db path,
    so the overview has to read them back off stdout."""
    log = (
        "BATCH PROCESSING: 3 files\n"
        "Warnings (2):\n"
        "  - no valid I_LRS values found in reset file for X\n"
        "  - something else went wrong\n"
    )
    findings = dashboard_data.parse_import_warnings(log)
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert "2 warning(s)" in findings[0].title
    assert "no valid I_LRS" in findings[0].detail
    assert dashboard_data.parse_import_warnings("nothing to report\n") == []


def test_findings_are_ordered_worst_first(stack_data, stack_db, synthetic_stack):
    overview = dashboard_data.collect(stack_data, stack_db, synthetic_stack, "stack")
    order = [dashboard_data.SEVERITY_ORDER[f.severity] for f in overview.findings]
    assert order == sorted(order)
    if overview.findings:
        assert overview.worst_severity == overview.findings[0].severity


# ── rendering ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def overview(stack_data, stack_db, synthetic_stack):
    return dashboard_data.collect(stack_data, stack_db, synthetic_stack, "stack")


def test_panel_renders_in_both_themes(overview):
    for dark in (False, True):
        html = dashboard_view.render(overview, dark=dark)
        assert "<style>" in html and "Data quality" in html
        assert "Key figures per parameter" in html
        assert html.count("<tr") >= len(overview.stats)


def test_panel_is_english_only(overview):
    """The interface is English; German crept into the overview once already."""
    html = dashboard_view.render(overview, dark=False)
    text = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    visible = re.sub(r"<[^>]+>", " ", text)
    attributes = " ".join(re.findall(r'title="([^"]*)"', html))
    assert not re.search(r"[ÄÖÜäöüß]", visible + attributes)
    for word in ("Datenqualität", "Kennzahlen", "Zyklen", "Einheit", "Warnung"):
        assert word not in html


def test_device_names_are_clickable(overview):
    html = dashboard_view.render(overview, dark=False)
    assert "data-device=" in html
    for finding in overview.findings:
        for device in finding.devices[:14]:
            assert f'data-device="{device}"' in html
