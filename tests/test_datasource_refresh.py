"""Every polled DataSource has to release its source, or it reads once.

Plasma's executable DataSource runs a connected source and holds it. The
widget re-reads by calling connectSource with the same command string on a
timer, and connecting a string that is already connected does nothing — so a
source that is never disconnected is read exactly once, at startup, and the
number on screen never changes again.

It does not look broken. The countdown next to the figure ticks on its own
timer and keeps moving, so the widget looks alive while showing a percentage
from whenever the panel last started.

Found by watching plasmashell's children: the tollens and session probes,
which disconnect, ran every 20-30 seconds; the main data loader, which did
not, never ran a second time.
"""
import re
from pathlib import Path

import pytest

QML = Path(__file__).resolve().parents[1] / "plasmoid" / "contents" / "ui" / "main.qml"


def _datasources(text):
    """Each P5Support.DataSource block, by id, with its body."""
    out = {}
    for m in re.finditer(r"P5Support\.DataSource\s*\{", text):
        start = m.end()
        depth, i = 1, start
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        body = text[start:i - 1]
        name = re.search(r"\bid:\s*(\w+)", body)
        out[name.group(1) if name else f"anonymous@{start}"] = body
    return out


def _block(text, marker):
    """The braced body following a marker, matched by counting braces.

    A regex anchored on the closing brace's indentation looked equivalent and
    was not: it silently failed to match every handler written on one line,
    and reported three sources as broken that were fine. Brace counting has no
    opinion about layout.
    """
    at = text.find(marker)
    if at == -1:
        return None
    start = text.find("{", at)
    if start == -1:
        return None
    depth, i = 1, start + 1
    while i < len(text) and depth:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return text[start + 1:i - 1]


def test_the_qml_declares_the_sources_this_test_watches():
    """Guard against the test quietly watching nothing after a refactor."""
    sources = _datasources(QML.read_text())
    assert len(sources) >= 3, f"only found {list(sources)}"
    assert "dataLoader" in sources


@pytest.mark.parametrize("name", list(_datasources(QML.read_text())))
def test_a_reconnecting_source_disconnects_on_delivery(name):
    body = _datasources(QML.read_text())[name]

    # Only sources that re-read matter: one connected once and left alone is
    # a different, legitimate pattern.
    reconnects = "connectSource(" in body
    if not reconnects:
        pytest.skip(f"{name} never reconnects")

    handler = _block(body, "onNewData:")
    assert handler is not None, f"{name}: no onNewData handler found"
    assert "disconnectSource(" in handler, (
        f"{name} reconnects the same source but never disconnects it; "
        "it will read once at startup and then never again")
