"""One version, declared in five places, must agree.

They already drifted: the plasmoid and tauri-app said 1.0.0 while win-widget
said 0.1.0, so "which version am I running" had two answers depending on which
file you opened.
"""
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _plasmoid():
    return json.loads((REPO / "plasmoid" / "metadata.json").read_text())["KPlugin"]["Version"]


def _package_json(rel):
    return json.loads((REPO / rel).read_text())["version"]


def _cargo(rel):
    m = re.search(r'^version\s*=\s*"([^"]+)"',
                  (REPO / rel).read_text(), re.M)
    assert m, f"no version in {rel}"
    return m.group(1)


SOURCES = {
    "plasmoid/metadata.json": _plasmoid,
    "tauri-app/package.json": lambda: _package_json("tauri-app/package.json"),
    "tauri-app/src-tauri/Cargo.toml": lambda: _cargo("tauri-app/src-tauri/Cargo.toml"),
    "win-widget/package.json": lambda: _package_json("win-widget/package.json"),
    "win-widget/src-tauri/Cargo.toml": lambda: _cargo("win-widget/src-tauri/Cargo.toml"),
}


def test_every_manifest_declares_the_same_version():
    got = {name: read() for name, read in SOURCES.items()}
    assert len(set(got.values())) == 1, f"versions disagree: {got}"


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_version_is_semver(name):
    v = SOURCES[name]()
    assert re.fullmatch(r"\d+\.\d+\.\d+", v), f"{name} declares {v!r}"


def test_changelog_documents_the_current_version():
    """A release nobody wrote down is one nobody can reason about later."""
    version = _plasmoid()
    changelog = (REPO / "CHANGELOG.md").read_text()
    assert f"## {version}" in changelog, f"CHANGELOG.md has no section for {version}"
