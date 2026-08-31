"""Every asset the provider table names must exist and be renderable.

A `"mascot": "rex.svg"` pointing at a missing file renders nothing at all, in
silence — Image just stays blank. The Codex provider shipped with `"mascot": ""`
for exactly that reason, which collapsed the whole mascot column.
"""
import re
import shutil
import subprocess
import xml.dom.minidom
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
QML = REPO / "plasmoid" / "contents" / "ui" / "main.qml"
ICONS = REPO / "plasmoid" / "contents" / "icons"


def _providers():
    """Asset names each provider row declares, parsed out of the brand table."""
    src = QML.read_text()
    block = src[src.index("readonly property var providers:"):
                src.index("readonly property var brand:")]
    out = {}
    for name, body in re.findall(r'"(\w+)":\s*\{(.*?)\}', block, re.S):
        fields = dict(re.findall(r'"(\w+)":\s*"([^"]*)"', body))
        out[name] = fields
    return out


def test_the_table_has_both_providers():
    p = _providers()
    assert set(p) >= {"claude", "codex"}, p.keys()


@pytest.mark.parametrize("provider", ["claude", "codex"])
def test_provider_declares_a_logo_and_a_mascot(provider):
    fields = _providers()[provider]
    assert fields.get("logo"), f"{provider} has no logo"
    assert fields.get("mascot"), (
        f"{provider} has no mascot; the header column collapses for it"
    )


@pytest.mark.parametrize("provider", ["claude", "codex"])
def test_declared_assets_exist(provider):
    fields = _providers()[provider]
    for key in ("logo", "mascot"):
        name = fields[key]
        assert (ICONS / name).is_file(), f"{provider}.{key} -> {name} missing from icons/"


@pytest.mark.parametrize("provider", ["claude", "codex"])
def test_declared_assets_are_wellformed_svg(provider):
    fields = _providers()[provider]
    for key in ("logo", "mascot"):
        path = ICONS / fields[key]
        if path.suffix != ".svg":
            continue
        xml.dom.minidom.parse(str(path))


@pytest.mark.skipif(shutil.which("rsvg-convert") is None, reason="rsvg-convert not installed")
@pytest.mark.parametrize("provider", ["claude", "codex"])
def test_declared_assets_actually_render(provider, tmp_path):
    """Well-formed XML is not the same as a drawable image: an SVG with no
    visible geometry parses fine and renders an empty box."""
    from PIL import Image
    for key in ("logo", "mascot"):
        path = ICONS / fields_of(provider)[key]
        if path.suffix != ".svg":
            continue
        out = tmp_path / f"{provider}-{key}.png"
        r = subprocess.run(["rsvg-convert", "-h", "64", str(path), "-o", str(out)],
                           capture_output=True)
        assert r.returncode == 0, r.stderr.decode()
        im = Image.open(out).convert("RGBA")
        data = getattr(im, "get_flattened_data", im.getdata)()
        opaque = sum(1 for px in data if px[3] > 8)
        assert opaque > 200, (
            f"{provider}.{key} renders almost nothing ({opaque} visible pixels)"
        )


def fields_of(provider):
    return _providers()[provider]


def test_mascot_state_sprites_are_complete():
    """Each animated state is a 6-frame loop; a missing frame shows as a gap."""
    for state in ("fire", "halo", "rain", "skull", "smart", "sun"):
        for frame in range(6):
            f = ICONS / f"{state}-{frame}.png"
            assert f.is_file(), f"missing animation frame {f.name}"
