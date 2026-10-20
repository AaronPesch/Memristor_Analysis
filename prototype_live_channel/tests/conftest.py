"""Shared fixtures for the prototype's tests.

Everything is built from the synthetic fixtures in `tools/make_fixtures.py`, so
the suite runs on any machine and in CI without measurement data. Point
MEMRISTOR_TEST_DATA at a real stack folder to additionally exercise the tests
marked `realdata`; without it they skip.
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

import pytest

PROTOTYPE = Path(__file__).resolve().parent.parent
REPO = PROTOTYPE.parent
for path in (str(PROTOTYPE), str(REPO / "src")):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.core.modes import Mode  # noqa: E402
from app.plotting.config import Config  # noqa: E402
from app.plotting.pipeline import load_all  # noqa: E402

CYCLES = 12  # enough for distributions, small enough to stay quick


def pytest_configure(config):
    config.addinivalue_line("markers", "realdata: needs MEMRISTOR_TEST_DATA")
    config.addinivalue_line("markers", "gui: builds a Qt window and a web view")
    config.addinivalue_line("markers", "slow: renders images through kaleido")


@pytest.fixture(scope="session")
def synthetic_stack(tmp_path_factory) -> Path:
    """A generated stack folder in the layout the importer expects."""
    sys.path.insert(0, str(PROTOTYPE / "tools"))
    import make_fixtures

    root = tmp_path_factory.mktemp("fixtures")
    rng_root = root / "data"
    import numpy as np

    rng = np.random.default_rng(11)
    for row in make_fixtures.ROWS:
        for col in make_fixtures.COLS:
            make_fixtures.build_device(rng_root, row, col, CYCLES, rng)
    return rng_root / make_fixtures.STACK_ID


@pytest.fixture(scope="session")
def stack_db(synthetic_stack, tmp_path_factory) -> Path:
    """The synthetic stack imported through the real BatchConverter."""
    from app.converter.batch import BatchConverter
    from app.converter.convert_path_to_glob import path_to_glob

    db = tmp_path_factory.mktemp("db") / "stack.duckdb"
    BatchConverter(db).convert(path_to_glob(synthetic_stack, Mode.STACK))
    return db


def _load(db: Path, mode: Mode):
    cfg = Config(db_file=db, output_dir=db.parent, mode=mode)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return cfg, load_all(cfg)


@pytest.fixture(scope="session")
def stack_data(stack_db):
    """LoadedData for the synthetic stack."""
    _cfg, data = _load(stack_db, Mode.STACK)
    return data


@pytest.fixture(scope="session")
def stack_categories(stack_db):
    import live_pipeline

    cfg, data = _load(stack_db, Mode.STACK)
    return data, live_pipeline.build_stack_categories(data)


@pytest.fixture(scope="session")
def real_stack() -> Path:
    """A real measurement folder, or skip."""
    raw = os.environ.get("MEMRISTOR_TEST_DATA")
    if not raw:
        pytest.skip("set MEMRISTOR_TEST_DATA to a stack folder to run this")
    path = Path(raw)
    if not path.is_dir():
        pytest.skip(f"MEMRISTOR_TEST_DATA is not a directory: {path}")
    return path
