"""The header must survive every page.

Wrapping the provider cards to hide them on the harness page swallowed the
header with them, and the header is where the back button lives — so switching
page removed the only way back, with no keyboard escape and no persisted state
to reset. Trapping the user is the worst class of UI defect: every other flaw
they can look past.
"""
import re
from pathlib import Path

import pytest

QML = Path(__file__).resolve().parents[1] / "plasmoid" / "contents" / "ui" / "main.qml"


def _lines():
    return QML.read_text().split("\n")


def _index_of(needle):
    for i, line in enumerate(_lines()):
        if needle in line:
            return i
    raise AssertionError(f"{needle!r} not found in main.qml")


def _block_end(start):
    """Line index closing the QML block opened at or after `start`."""
    lines = _lines()
    depth, opened = 0, False
    for i in range(start, len(lines)):
        depth += lines[i].count("{") - lines[i].count("}")
        if lines[i].count("{"):
            opened = True
        if opened and depth == 0:
            return i
    raise AssertionError("unterminated block")


def test_header_is_not_inside_the_page_zero_wrapper():
    """The regression, stated positionally: the header must come before the
    wrapper that is hidden on page 1."""
    header = _index_of("── Header with mascot ──")
    wrapper = _index_of("id: providerPage")
    assert header < wrapper, (
        "the header sits inside providerPage, which is hidden on page 1 — "
        "switching page removes the back button"
    )


def test_the_page_wrapper_does_not_contain_the_header():
    """Belt and braces: even if ordering changed, the header must not fall
    within the wrapper's block."""
    wrapper = _index_of("id: providerPage")
    start = wrapper
    while "{" not in _lines()[start]:
        start -= 1
    end = _block_end(start)
    header = _index_of("── Header with mascot ──")
    assert not (start <= header <= end), "header is inside the hidden wrapper"


def test_page_toggle_can_return_to_zero():
    """The button must toggle, not only advance."""
    body = QML.read_text()
    assert "root.page = root.page === 0 ? 1 : 0" in body, (
        "no toggle back to page 0 found"
    )


def test_page_toggle_only_exists_with_tollens():
    body = QML.read_text()
    idx = body.index("root.page = root.page === 0 ? 1 : 0")
    window = body[max(0, idx - 600):idx]
    assert "visible: root.hasTollens" in window, (
        "the page button is not gated on Tollens being present"
    )


def test_harness_page_is_gated_on_both_presence_and_page():
    body = QML.read_text()
    assert "active: root.hasTollens && root.page === 1" in body


def test_page_defaults_to_zero():
    """Not persisted, so a reload always lands on the usage page — the escape
    hatch if a future change breaks navigation again."""
    body = QML.read_text()
    assert re.search(r"property int page:\s*0", body), "page does not default to 0"


def test_header_comes_before_every_page():
    """The header moved out of the wrapper but landed after the harness Loader,
    so on the harness page it rendered at the bottom of the popup — under the
    content it is supposed to head."""
    header = _index_of("── Header with mascot ──")
    harness = _index_of("sourceComponent: harnessPage")
    wrapper = _index_of("id: providerPage")
    assert header < harness, "header renders after the harness page content"
    assert header < wrapper, "header renders after the provider cards"


def test_language_toggle_lives_in_the_header():
    """Two languages is a toggle, not a setting. Making someone open Configure
    to read the widget in their own language is a worse trade than a button."""
    body = QML.read_text()
    assert "id: langBtn" in body, "no language button"
    header = _index_of("── Header with mascot ──")
    button = _index_of("id: langBtn")
    end = _block_end(header + 1)
    assert header < button < end, "language button is not inside the header"


def test_language_toggle_reaches_both_languages():
    body = QML.read_text()
    assert 'root.lang === "pt" ? "en" : "pt"' in body, "toggle does not swap both ways"
    assert 'Plasmoid.configuration.language = "auto"' in body, "no way back to auto"
