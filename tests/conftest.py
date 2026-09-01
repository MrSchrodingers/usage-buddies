import importlib.util
import os
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


@pytest.fixture(autouse=True)
def _cache_of_our_own(tmp_path_factory, monkeypatch):
    """No test writes into the cache the running programs use.

    A Companion built in a test publishes a presence file, and buddy_peers
    resolves that directory from XDG_CACHE_HOME on every call — so the suite
    was leaving files named after the pytest pid in
    ~/.cache/usage-buddies/peers/, on the same machine and in the same
    directory a real companion reads. They expire, so nothing broke; it is
    still the suite reaching into the user's state to do it.

    Set for every test rather than for the ones known to publish today,
    because the next one to build a Companion inherits the isolation instead
    of the leak. Tests that need a specific cache still pass their own
    XDG_CACHE_HOME to the subprocess they run, which wins over this.
    """
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("cache")))
