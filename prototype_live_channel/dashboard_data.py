"""Facts for the overview tab: import profile, key figures, data quality.

Deliberately separate from the rendering, so the checks can be tested without a
window. Nothing here touches `src/app` -- it reads the same LoadedData the
builders get, plus the database and the source folder.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

DEVICE_RE = re.compile(r"^([A-Za-z]+)(\d+)$")

# (column, label, unit) -- the parameters worth a summary row.
STAT_PARAMS = [
    ("VSET", "V_set", "V"),
    ("V_reset", "V_reset", "V"),
    ("R_LRS", "R_LRS", "Ohm"),
    ("R_HRS", "R_HRS", "Ohm"),
    ("Memory_window", "Memory Window", "R_HRS/R_LRS"),
    ("I_reset_max", "I_reset_max", "A"),
    ("V_forming", "V_forming", "V"),
    ("I_leakage_pristine", "I_leakage", "A"),
]

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


@dataclass
class Finding:
    """One data-quality observation."""

    severity: str  # error | warning | info
    title: str
    detail: str
    devices: list[str] = field(default_factory=list)


@dataclass
class Stat:
    label: str
    unit: str
    n: int
    median: float
    mean: float
    std: float
    cv: float  # coefficient of variation, std / |mean|
    p10: float
    p90: float
    minimum: float
    maximum: float

    @property
    def cv_is_meaningful(self) -> bool:
        """Resistances span decades, so a single outlier can push the CV past
        1000 % and say nothing about the bulk of the devices. Above this the
        table points at p10-p90 instead."""
        return self.cv == self.cv and self.cv < 1.0


@dataclass
class Overview:
    stack_id: str
    mode: str
    source: str
    devices: list[str]
    n_sets: int
    n_resets: int
    v_read: float
    db_rows: int
    db_tables: list[str]
    cycles_total: int
    measurement_types: dict[str, int]
    stats: list[Stat]
    findings: list[Finding]

    @property
    def worst_severity(self) -> str | None:
        if not self.findings:
            return None
        return min(self.findings, key=lambda f: SEVERITY_ORDER[f.severity]).severity


# ── statistics ───────────────────────────────────────────────────────────────


def _stat_for(
    box_table: pd.DataFrame, column: str, label: str, unit: str
) -> Stat | None:
    if column not in box_table.columns:
        return None
    values = pd.to_numeric(box_table[column], errors="coerce").dropna().abs()
    if values.empty:
        return None
    mean = float(values.mean())
    std = float(values.std(ddof=1)) if values.size > 1 else 0.0
    return Stat(
        label=label,
        unit=unit,
        n=int(values.size),
        median=float(values.median()),
        mean=mean,
        std=std,
        # The point of the CV: spread relative to level, so R_HRS in ohms and
        # V_set in volts become comparable.
        cv=(std / abs(mean)) if mean else float("nan"),
        p10=float(values.quantile(0.10)),
        p90=float(values.quantile(0.90)),
        minimum=float(values.min()),
        maximum=float(values.max()),
    )


def build_stats(box_table: pd.DataFrame) -> list[Stat]:
    out = []
    for column, label, unit in STAT_PARAMS:
        stat = _stat_for(box_table, column, label, unit)
        if stat is not None:
            out.append(stat)
    return out


# ── data quality ─────────────────────────────────────────────────────────────


def find_duplicate_files(source: Path) -> list[Finding]:
    """Devices whose measurement files are byte-identical copies of each other.

    This is the check that would have caught T25098 immediately: 26 of its 30
    devices carried the same files, which made every device-to-device
    comparison meaningless while the plots looked perfectly healthy.

    Reported per device cluster, not per file name -- one copied device shows up
    in every one of its files, and nine findings saying the same thing bury the
    one that matters.
    """
    fingerprints: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for path in source.rglob("*.xlsx"):
        if path.name.startswith("~$"):
            continue
        digest = hashlib.md5(path.read_bytes()).hexdigest()
        fingerprints[path.parent.name].append((path.name, digest))

    if not fingerprints:
        return []

    # One fingerprint per device: every file it holds, by name and content.
    by_fingerprint: dict[str, list[str]] = defaultdict(list)
    for device, files in fingerprints.items():
        key = hashlib.md5(repr(sorted(files)).encode()).hexdigest()
        by_fingerprint[key].append(device)

    findings = []
    clustered: set[str] = set()
    for devices in sorted(by_fingerprint.values(), key=len, reverse=True):
        if len(devices) < 2:
            continue
        clustered.update(devices)
        n_files = len(fingerprints[devices[0]])
        findings.append(
            Finding(
                severity="error",
                title=f"{len(devices)} devices hold identical measurement data",
                detail=(
                    f"All {n_files} files are byte-identical copies across these "
                    "devices, so any comparison between them carries no "
                    "information. Distributions and yield over this group "
                    "describe a single device."
                ),
                devices=sorted(devices),
            )
        )

    # Devices not fully cloned may still share individual files.
    partial: set[str] = set()
    for name_digest, owners in _by_file(fingerprints).items():
        if len(owners) > 1 and not set(owners) <= clustered:
            partial.update(o for o in owners if o not in clustered)
    if partial:
        findings.append(
            Finding(
                severity="warning",
                title=f"{len(partial)} further device(s) share individual files",
                detail="Not a full copy, but some measurements are duplicated.",
                devices=sorted(partial),
            )
        )
    return findings


def _by_file(
    fingerprints: dict[str, list[tuple[str, str]]],
) -> dict[tuple[str, str], list[str]]:
    owners: dict[tuple[str, str], list[str]] = defaultdict(list)
    for device, files in fingerprints.items():
        for name, digest in files:
            owners[(name, digest)].append(device)
    return owners


def find_position_gaps(devices: list[str]) -> list[Finding]:
    unplaced = [d for d in devices if not DEVICE_RE.match(d)]
    if not unplaced:
        return []
    return [
        Finding(
            severity="warning",
            title=f"{len(unplaced)} device(s) have no grid position",
            detail=(
                "The folder name does not match <letters><digits>, so these do "
                "not appear on the stack map or the yield map."
            ),
            devices=sorted(unplaced),
        )
    ]


def find_coverage_gaps(conn, devices: list[str]) -> list[Finding]:
    """Devices missing a measurement type that most others have."""
    rows = conn.execute(
        """
        SELECT device_row || CAST(device_col AS VARCHAR) AS device, measurement_type
        FROM cycles
        WHERE device_row IS NOT NULL
        GROUP BY 1, 2
        """
    ).fetchall()
    have: dict[str, set[str]] = defaultdict(set)
    for device, kind in rows:
        have[device].add(kind)

    counts = Counter(kind for kinds in have.values() for kind in kinds)
    findings = []
    for kind, present in sorted(counts.items()):
        if present >= len(devices):
            continue
        missing = sorted(d for d in devices if kind not in have.get(d, set()))
        if not missing:
            continue
        findings.append(
            Finding(
                severity="warning",
                title=f"{len(missing)} device(s) without '{kind}' data",
                detail=f"{present} of {len(devices)} devices carry this measurement type.",
                devices=missing,
            )
        )
    return findings


def find_cycle_imbalance(conn) -> list[Finding]:
    rows = conn.execute(
        """
        SELECT device_row || CAST(device_col AS VARCHAR) AS device,
               count(DISTINCT cycle_number) AS cycles
        FROM cycles
        WHERE measurement_type = 'endurance_set' AND device_row IS NOT NULL
        GROUP BY 1
        """
    ).fetchall()
    if len(rows) < 2:
        return []
    counts = {device: n for device, n in rows}
    typical = int(np.median(list(counts.values())))
    odd = sorted(d for d, n in counts.items() if n != typical)
    if not odd:
        return []
    examples = ", ".join(f"{d} ({counts[d]})" for d in odd[:6])
    return [
        Finding(
            severity="info",
            title=f"{len(odd)} device(s) deviate from the usual {typical} cycles",
            detail=f"Distributions over these devices rest on fewer or more points. {examples}",
            devices=odd,
        )
    ]


def parse_import_warnings(log: str) -> list[Finding]:
    """Pull the warnings BatchConverter prints but never returns.

    `convert()` hands back only the database path; the per-file warnings are
    collected in `_print_summary` and written to stdout, where a GUI user never
    sees them. Capturing the output is the only way to surface them without
    changing the converter.
    """
    lines = [ln.strip() for ln in log.splitlines()]
    collected = [ln[2:].strip() for ln in lines if ln.startswith("- ")]
    if not collected:
        return []
    shown = "; ".join(collected[:3])
    more = f" (+{len(collected) - 3} more)" if len(collected) > 3 else ""
    return [
        Finding(
            severity="warning",
            title=f"{len(collected)} warning(s) during import",
            detail=f"{shown}{more}",
        )
    ]


# ── assembly ─────────────────────────────────────────────────────────────────


def collect(
    data, db_file: Path, source: Path, mode: str, import_log: str = ""
) -> Overview:
    with duckdb.connect(str(db_file), read_only=True) as conn:
        tables = sorted(r[0] for r in conn.execute("SHOW TABLES").fetchall())
        db_rows = conn.execute("SELECT count(*) FROM cycles").fetchone()[0]
        cycles_total = conn.execute(
            "SELECT count(*) FROM (SELECT DISTINCT source_file, cycle_number FROM cycles)"
        ).fetchone()[0]
        measurement_types = dict(
            conn.execute(
                "SELECT measurement_type, count(*) FROM cycles GROUP BY 1 ORDER BY 1"
            ).fetchall()
        )

        findings: list[Finding] = []
        findings += parse_import_warnings(import_log)
        if source.exists():
            findings += find_duplicate_files(source)
        findings += find_position_gaps(data.devices)
        findings += find_coverage_gaps(conn, data.devices)
        findings += find_cycle_imbalance(conn)

    findings.sort(key=lambda f: SEVERITY_ORDER[f.severity])

    return Overview(
        stack_id=data.stack_id,
        mode=mode,
        source=str(source),
        devices=list(data.devices),
        n_sets=len(data.sets),
        n_resets=len(data.resets),
        v_read=float(data.v_read),
        db_rows=int(db_rows),
        db_tables=tables,
        cycles_total=int(cycles_total),
        measurement_types=measurement_types,
        stats=build_stats(data.box_table),
        findings=findings,
    )
