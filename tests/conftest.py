import importlib.util
import sys
from pathlib import Path

import pytest

COLLECTOR = Path(__file__).resolve().parents[1] / "scripts" / "usage-buddies-collector.py"


def _load(name="collector_under_test"):
    spec = importlib.util.spec_from_file_location(name, COLLECTOR)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def collector():
    """Fresh import of the collector for each test."""
    return _load()
