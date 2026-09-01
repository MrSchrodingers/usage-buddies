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


# ── scope ──────────────────────────────────────────────────────────────────
#
# Verified against Qt rather than recalled. A three-level Item tree, run under
# `qml`:
#
#     root property, unqualified    -> ROOT-OK
#     middle property, unqualified  -> ReferenceError: fromMiddle is not defined
#     middle property, qualified    -> MIDDLE-OK
#
# So a bare name reaches the object it is written in and the root of its
# component, and nothing in between. `Component { ... }` starts a new
# component, which makes its single child a root — that is why the harness
# page's properties are legitimately readable from everything nested under it,
# and an earlier version of this check called five of them broken.


def _strip_literals(text):
    """Blank out string contents and comments.

    Without this the check matched property names occurring inside strings —
    `"../icons/"` was read as a bare use of a property called `icons` — and
    reported most of the file.
    """
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r'"(?:[^"\\]|\\.)*"', '""', text)
    return re.sub(r"'(?:[^'\\]|\\.)*'", "''", text)


# `[ \t]*`, not `\s*`: \s matches the newline before the header too, so a
# header preceded by a blank line came out one column deeper than it is and
# its properties were then looked for at the wrong indent. That silently
# under-reported on the real file and made the planted case undetectable.
HEADER = re.compile(r"^([ \t]*)(?:([A-Z][\w.]*)|(\w[\w.]*[ \t]+on[ \t]+\w+))[ \t]*\{[ \t]*$", re.M)


def _blocks(text):
    """Object headers with their indent, type and body span."""
    out = []
    for m in HEADER.finditer(text):
        indent = len(m.group(1))
        start = m.end()
        depth, i = 1, start
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        out.append({"indent": indent, "type": (m.group(2) or m.group(3)),
                    "start": start, "end": i - 1})
    return out


def test_the_scope_check_can_still_see_a_planted_violation():
    """A checker this fiddly has to prove it is looking. Two earlier versions
    passed while watching nothing: one matched inside string literals and
    reported the whole file, the other counted the document root — the one
    scope QML actually provides — as an offender."""
    planted = """
Item {
    id: outer
    property bool flag: false
    Rectangle {
        color: flag ? "red" : "blue"
    }
}
"""
    assert _violations(planted), "the check no longer detects the bug it exists for"
    clean = planted.replace("color: flag ?", "color: outer.flag ?")
    assert not _violations(clean), "the check fires on correct code"


def _violations(text):
    text = _strip_literals(text)
    blocks = _blocks(text)
    bad = []
    for b in blocks:
        body = text[b["start"]:b["end"]]
        # A Component's child is the root of its own component, so properties
        # declared on it are in scope everywhere below.
        if b["type"] == "Component":
            continue
        ident = re.search(r"^\s*id:\s*(\w+)", body, re.M)
        if not ident:
            continue
        # Only this block's own declarations: the body contains its children's
        # too, and attributing those here blamed the wrong object.
        own = set(re.findall(r"^ {%d}(?:readonly )?property \w[\w.<>]* (\w+)"
                             % (b["indent"] + 4), body, re.M))
        if not own:
            continue
        parent_is_component = any(
            o["type"] == "Component" and o["start"] <= b["start"] and b["end"] <= o["end"]
            and o["indent"] == b["indent"] - 4 for o in blocks)
        if parent_is_component:
            continue
        for child in _blocks(body):
            if child["indent"] <= b["indent"]:
                continue
            inner = body[child["start"]:child["end"]]
            for prop in own:
                # Three legitimate shadows, each of which this reported as a
                # bug before it knew about them: the child redeclaring the
                # property, a local `var` of the same name inside a binding,
                # and a function that happens to share the name.
                shadowed = (
                    re.search(r"^\s*(?:readonly )?property \w+ %s\b" % prop, inner, re.M)
                    or re.search(r"\bvar\s+%s\s*=" % prop, inner)
                    or re.search(r"\bfunction\s+%s\s*\(" % prop, inner))
                if shadowed:
                    continue
                if re.search(r"(?<![\w.])%s\b" % prop, inner):
                    bad.append(f"{ident.group(1)}.{prop} read bare inside a nested "
                               f"{child['type']}")
    return sorted(set(bad))


def test_no_nested_object_reads_an_enclosing_property_unqualified():
    """QML resolves a bare name against the object it is written in and the
    root of its component — never against the object that merely encloses it.

    So `NumberAnimation { duration: sweptIn ? 800 : 1100 }` inside a Canvas
    that declares `sweptIn` does not see it. It is not a build error: the name
    comes back undefined, the expression quietly takes the falsy branch, and
    the only trace is a ReferenceError in the shell's log. That one made the
    progress ring animate as though it had already drawn itself in, every
    time the popup opened.
    """
    offenders = _violations(QML.read_text())
    assert not offenders, "unqualified reads of an enclosing property:\n  " + \
        "\n  ".join(offenders)


def test_no_source_gates_its_data_on_the_exit_code_key():
    """`data["exit code"]` is a string key with a space in it. If the engine
    ever spells it differently the comparison becomes undefined === 0, which
    is false — so every read is thrown away in silence while the source keeps
    cycling, and the widget shows whatever it had when the panel started for
    as long as the panel stays up. It looks like a slow refresh, and there is
    no warning anywhere.

    Output that parses into the shape we want is the thing actually needed,
    and it does not depend on a key name."""
    text = QML.read_text()
    offenders = [line.strip() for line in text.splitlines()
                 if "exit code" in line and not line.lstrip().startswith("//")]
    assert not offenders, "data gated on the exit-code key:\n  " + "\n  ".join(offenders)
