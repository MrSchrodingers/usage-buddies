"""The popup, laid out for real, and asked whether anything fell off the edge.

Every other test over `main.qml` in this repository reads it as text, and so
does qmllint. Both of them passed the day a sixth button in the popup header
pushed the header row's minimum width past the popup's own: a RowLayout does
not shrink below the sum of its children's minimums, so the row overflowed the
column, and the Flickable around it holds `contentWidth` at its own width and
clips rather than scrolling sideways. Every row in the popup came out cut off
at the same x. It was found by opening the popup and looking at it.

This loads the same file into a real QtQuick scene, renders it, and measures
where the items landed. The Plasma and Kirigami modules it imports do not
resolve outside a Plasma session, so `tests/qmlstubs/` stands in for them; the
doubles are geometry only, and `DataSource` in particular runs nothing, because
main.qml uses it to drive the collector and the companion control script.

Two things are worth knowing before trusting a green run here:

  * The doubles are what make the measurements mean anything, and a double that
    reports zero width would make every layout fit. `test_the_doubles_measure`
    and `test_the_rendered_popup_is_not_empty` are the guards against that, and
    they run first.
  * `test_the_harness_still_catches_the_header_that_did_not_fit` renders the
    version of main.qml from before the fix and requires this harness to
    reject it. Without that, a harness that had quietly stopped measuring
    would look exactly like a widget that fits.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
STUBS = REPO / "tests" / "qmlstubs"
RENDER = STUBS / "harness" / "render_popup.py"
MEASURE = STUBS / "harness" / "measure_scene.py"
DOUBLES_PROBE = STUBS / "harness" / "DoublesProbe.qml"
MAIN_QML = REPO / "plasmoid" / "contents" / "ui" / "main.qml"
ICONS = REPO / "plasmoid" / "contents" / "icons"

# The commit that fixed the overflow. Its parent is the version that showed it,
# and re-rendering that parent is how this file proves it can still fail.
FIX_COMMIT = "fdc0466"
BROKEN_REVISION = FIX_COMMIT + "^:plasmoid/contents/ui/main.qml"

# The UI font, pinned rather than inherited.
#
# Everything in the popup is sized in Kirigami grid units, and a grid unit is
# the height of one line of this font, so the machine's font settings would
# otherwise decide whether the widget fits. 13 px is a 10-point font at 96 dpi
# and puts the grid unit at 18, which is where this harness reproduces what was
# seen on a real desktop: the pre-fix header overflows there. It is a model of
# a stock desktop, not a measurement of one — see tests/qmlstubs/README.md for
# which numbers in the doubles are modelled and which are measured.
FONT_PX = 13

# The header at its widest, which is the state the overflow was found in: the
# companion switched on adds the focus button, and a Tollens install adds the
# harness button, for six in the row. Both are reachable from the config dialog
# and from having Tollens installed; neither is exotic.
#
# usageData is shaped like the collector's output (see test_weekly_rows.py for
# the same payload against the live endpoint). It is here because the widths in
# the header come from the text in it — the plan name, the state pill — and an
# empty payload would measure a popup nobody sees.
SCENARIO = {
    "config": {"buddyMode": "chatty"},
    "properties": {
        "tollens": {"present": True, "enforced": True, "activated": True},
        "usageData": {
            "rateLimits": {
                "plan": "Max (20x)", "source": "api",
                "session": {"percentUsed": 61.0, "resetsInMinutes": 143,
                            "windowHours": 5,
                            "resetsAt": "2026-09-02T23:30:00+00:00"},
                "weeklyAll": {"percentUsed": 47.0,
                              "resetsLabel": "Fri 04:59 AM",
                              "resetsAt": "2026-09-05T04:59:59+00:00"},
                "weeklyFable": {"percentUsed": 12.0, "modelName": "Fable",
                                "resetsLabel": "Fri 04:59 AM",
                                "resetsAt": "2026-09-05T04:59:59+00:00"},
                "weeklyScoped": {"percentUsed": 12.0, "modelName": "Fable",
                                 "resetsLabel": "Fri 04:59 AM",
                                 "resetsAt": "2026-09-05T04:59:59+00:00"},
            },
            "dumbness": {"score": 42, "level": "slow"},
            "serviceStatus": {"indicator": "none",
                              "description": "All Systems Operational",
                              "active_incidents": []},
            "today": {"totalTokens": 1781115342, "totalCost": 12.5},
            "streak": {"days": 9},
            "compaction": {"count": 11},
            "burnRate": {"total_per_hour": 372436672},
            "lifetime": {"totalSessions": 1284,
                         "firstSession": "2025-11-04T12:00:00Z",
                         "longestSession": {"duration": 9000000},
                         "peakHours": {"14": 76, "16": 60}},
            "settings": {"pluginCount": 7},
            "claudeCodeVersion": "2.0.31",
        },
    },
}

# Layout rounding: Qt lays out on fractional pixels and rounds when it assigns
# geometry, so a half pixel over is arithmetic, not an overflow.
EPS = 0.5

needs_qt = pytest.mark.skipif(importlib.util.find_spec("PySide6") is None,
                              reason="PySide6 missing")


# ── running the scene ────────────────────────────────────────────────────────

def _child_env():
    """Offscreen, whatever the rest of the suite left in the environment.

    test_companion_actions imports with QT_QPA_PLATFORM set to xcb, and that
    reaches a subprocess through os.environ. On a machine with no display the
    renderer would then fail to start, which would look like a layout problem.
    """
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_QUICK_BACKEND"] = "software"
    env["QT_SCALE_FACTOR"] = "1"
    env.pop("QT_FONT_DPI", None)
    env.pop("QT_SCREEN_SCALE_FACTORS", None)
    return env


def _run(script, args):
    proc = subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, text=True, env=_child_env(),
                          cwd=str(REPO), timeout=300)
    if proc.returncode != 0 or not proc.stdout.strip():
        detail = proc.stdout.strip() or "(no stdout)"
        raise AssertionError(
            "%s failed (exit %d)\n%s\n%s"
            % (script.name, proc.returncode, detail, proc.stderr.strip()))
    result = json.loads(proc.stdout)
    if not result.get("ok"):
        raise AssertionError("%s: %s\n%s"
                             % (script.name, result.get("error"),
                                "\n".join(result.get("errors", []))))
    return result


_RENDERS = {}


def render(qml, width="preferred", font_px=FONT_PX, scenario=None):
    """Render one popup and return its item tree. Cached per distinct scene."""
    scenario = scenario if scenario is not None else SCENARIO
    key = (str(qml), width, font_px, json.dumps(scenario, sort_keys=True))
    if key not in _RENDERS:
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as fh:
            json.dump(scenario, fh)
            scenario_path = fh.name
        try:
            _RENDERS[key] = _run(RENDER, [
                "--qml", str(qml), "--font-px", str(font_px),
                "--width", str(width), "--scenario", scenario_path,
                "--stubs", str(STUBS)])
        finally:
            os.unlink(scenario_path)
    return _RENDERS[key]


@pytest.fixture(scope="module")
def popup():
    """The current popup at the width it asks the panel for."""
    return render(MAIN_QML)


# ── reading the item tree ────────────────────────────────────────────────────

def shown(node):
    """Visible and not painted out.

    QQuickItem.visible is already the effective one — false if any ancestor is
    hidden — so a card on the page that is not showing does not have to fit.
    """
    return node["visible"] and node["opacity"] > 0.01


def where(scene, node):
    """A readable path, since QML ids do not survive into the scene graph."""
    by_index = {n["i"]: n for n in scene["nodes"]}
    parts = []
    while node is not None and node["parent"] >= 0:
        label = node["cls"].split("_QMLTYPE_")[0]
        if node.get("text"):
            label += "[%r]" % node["text"][:28]
        parts.append(label)
        node = by_index[node["parent"]]
    return "/".join(reversed(parts)) or "(root)"


def flickable(scene):
    flicks = [n for n in scene["nodes"] if n["cls"] == "QQuickFlickable"]
    assert flicks, "the popup has no Flickable; the harness is measuring something else"
    return flicks[0]


def overflowing_layout_children(scene):
    """Items placed by a layout that ended up outside it.

    A layout positions its own children, so one sticking out is always a defect
    — it is drawn over whatever sits next to it. Items placed by anchors are
    not checked: main.qml deliberately overhangs a corner or two with them.
    """
    by_index = {n["i"]: n for n in scene["nodes"]}
    out = []
    for node in scene["nodes"]:
        if not shown(node) or not node["parentIsLayout"]:
            continue
        parent = by_index[node["parent"]]
        if node["x"] + node["w"] > parent["w"] + EPS or node["x"] < -EPS:
            out.append((node, parent))
    return out


def clipped_by_flickable(scene):
    """Items the popup's Flickable cuts off.

    contentWidth is bound to the Flickable's own width, so it never scrolls
    sideways: anything past that edge is not off-screen-but-reachable, it is
    gone. This is the exact shape of the defect this file exists for.
    """
    flick = flickable(scene)
    limit = flick["contentWidth"]
    return [n for n in scene["nodes"]
            if shown(n) and (n["absR"] > limit + EPS or n["absL"] < -EPS)]


def texts(scene):
    return [n for n in scene["nodes"]
            if n.get("isText") and shown(n) and n.get("text", "").strip()]


def buttons(scene):
    return [n for n in scene["nodes"]
            if shown(n) and n["cls"].split("_QMLTYPE_")[0] in
            ("ToolButton", "Button")]


# ── the doubles have to measure before anything else means anything ──────────

@needs_qt
def test_the_doubles_measure():
    """A double that reports zero width makes every layout fit.

    That is the failure mode this whole file dies of silently, so it is checked
    directly: text has to get wider when there is more of it, and a button has
    to be at least as wide as the icon drawn inside it.
    """
    values = _run(MEASURE, ["--qml", str(DOUBLES_PROBE),
                            "--font-px", str(FONT_PX),
                            "--stubs", str(STUBS)])["values"]

    assert values["shortLabelWidth"] > 0, values
    assert values["labelHeight"] > 0, values
    assert values["longLabelWidth"] > values["shortLabelWidth"] * 2, (
        "a label with far more text is not measurably wider: the Label double "
        "is not measuring text. %r" % values)
    assert values["emptyLabelWidth"] == 0, values

    assert values["iconWidth"] > 0 and values["iconHeight"] > 0, values
    assert values["iconButtonWidth"] >= values["smallMediumIcon"], (
        "a tool button came out narrower than the icon it draws: %r" % values)
    assert values["iconButtonHeight"] > 0, values
    assert values["textButtonWidth"] > values["iconButtonWidth"], (
        "adding a label did not widen the button: %r" % values)
    assert values["bareButtonWidth"] > 0, values

    # The font actually reached the theme double. If it had not, every label in
    # main.qml would be sized off pixelSize -1.
    assert values["defaultFontPixelSize"] == FONT_PX, values
    assert values["gridUnit"] > 0 and values["smallSpacing"] > 0, values


@needs_qt
def test_the_rendered_popup_is_not_empty(popup):
    """Guards the other direction: a scene that loaded but rendered nothing.

    Every geometry assertion below is over a list of items. An empty list
    passes all of them, so the size of that list is checked before they are
    trusted.
    """
    assert popup["renderedWidth"] == popup["declared"]["preferredWidth"]
    assert popup["renderedWidth"] > 0 and popup["renderedHeight"] > 0
    assert len(popup["nodes"]) > 100, (
        "only %d items in the popup; it did not really render"
        % len(popup["nodes"]))
    assert len(texts(popup)) > 20, (
        "only %d visible labels with text" % len(texts(popup)))
    assert len(buttons(popup)) >= 6, (
        "only %d buttons in the popup; the header is not at its widest and "
        "the overflow this file is about would not be reachable"
        % len(buttons(popup)))
    # And it was measured, not just built: a scene where every double reported
    # zero would still have all of the items counted above.
    assert flickable(popup)["w"] == popup["renderedWidth"], (
        "the popup's Flickable is %.1f wide inside a %.1f-wide popup; the "
        "scene was not arranged" % (flickable(popup)["w"],
                                    popup["renderedWidth"]))
    assert max(n["w"] for n in texts(popup)) > popup["gridUnit"], (
        "the widest label in the popup is under one grid unit; nothing is "
        "measuring text")


# ── the harness has to be able to fail ───────────────────────────────────────

@needs_qt
def test_the_harness_still_catches_the_header_that_did_not_fit(tmp_path):
    """Renders the version from before fdc0466 and requires this to reject it.

    A harness that cannot reproduce the defect it was written for is
    decoration, and the way it stops reproducing it is silent — a double that
    stops measuring, a scenario that stops reaching the widest header. So the
    broken revision is checked out of git and put through the same checks,
    which have to report the same shape of failure the screenshot showed: the
    rows of the popup running past the Flickable's edge, all at the same x.
    """
    if shutil.which("git") is None:
        pytest.skip("git missing, cannot fetch %s" % BROKEN_REVISION)
    probe = subprocess.run(["git", "cat-file", "-e", BROKEN_REVISION],
                           cwd=str(REPO), capture_output=True)
    if probe.returncode != 0:
        pytest.skip("%s is not in this clone (shallow?), so the harness "
                    "cannot be shown to fail" % BROKEN_REVISION)

    broken = tmp_path / "contents" / "ui" / "main.qml"
    broken.parent.mkdir(parents=True)
    broken.write_bytes(subprocess.run(
        ["git", "show", BROKEN_REVISION], cwd=str(REPO),
        capture_output=True, check=True).stdout)
    # The QML resolves icons as ../icons/, and an Image that fails to load
    # measures zero — which would make the copy narrower than the original.
    (tmp_path / "contents" / "icons").symlink_to(ICONS)

    scene = render(broken)
    cut = clipped_by_flickable(scene)
    assert cut, (
        "the pre-fix header no longer overflows in this harness. Either the "
        "doubles stopped measuring or the scenario stopped opening the header "
        "at its widest — until that is understood, a green run over the "
        "current main.qml means nothing.")

    # The symptom was not one item hanging over the edge, it was the whole
    # popup laid out too wide and cut at one x.
    edges = {round(n["absR"], 1) for n in cut}
    assert len(edges) < len(cut), (
        "expected many items sharing one over-wide right edge, got %d items "
        "at %d distinct edges" % (len(cut), len(edges)))
    assert overflowing_layout_children(scene), (
        "the pre-fix header row no longer sticks out of the column it is in")


# ── what the current popup has to satisfy ────────────────────────────────────

@needs_qt
def test_nothing_in_the_popup_is_clipped_by_the_flickable(popup):
    """The exact defect: content wider than the view, in a view that clips.

    popupFlick keeps contentWidth at its own width, so there is no sideways
    scrolling to reach what does not fit. Anything past that edge is cut off.
    """
    cut = clipped_by_flickable(popup)
    limit = flickable(popup)["contentWidth"]
    assert not cut, (
        "%d item(s) cut off by the popup's Flickable at %.0f px "
        "(grid unit %s, font %s px):\n%s"
        % (len(cut), limit, popup["gridUnit"], popup["fontPx"],
           "\n".join("  %.1f..%.1f (%.1f px over) %s"
                     % (n["absL"], n["absR"], n["absR"] - limit,
                        where(popup, n))
                     for n in cut[:12])))


@needs_qt
def test_no_layout_child_sticks_out_of_its_layout(popup):
    """Narrower than clipping, and it catches the same defect one step earlier.

    A RowLayout squeezed below the sum of its children's minimums lays them out
    at those minimums anyway, so they run past its right edge and over whatever
    is beside them. That happens before anything reaches the Flickable's edge,
    which is why this is checked separately.
    """
    bad = overflowing_layout_children(popup)
    assert not bad, (
        "%d item(s) placed outside the layout that owns them "
        "(grid unit %s, font %s px):\n%s"
        % (len(bad), popup["gridUnit"], popup["fontPx"],
           "\n".join("  %s is %.1f wide at x=%.1f inside a %.1f-wide parent "
                     "(%.1f px over)"
                     % (where(popup, n), n["w"], n["x"], p["w"],
                        n["x"] + n["w"] - p["w"])
                     for n, p in bad[:12])))


@needs_qt
def test_every_visible_label_and_button_has_a_size(popup):
    """Nothing that is meant to be read came out with no room to be read in.

    Only labels with text and buttons are checked. A zero-width item is normal
    elsewhere in this file — the header's spacer is an `Item` with fillWidth and
    nothing in it, and it is zero whenever the row has no slack.
    """
    empty = [n for n in texts(popup) + buttons(popup)
             if n["w"] <= 0 or n["h"] <= 0]
    assert not empty, (
        "%d visible item(s) with no size:\n%s"
        % (len(empty),
           "\n".join("  %.1fx%.1f %s" % (n["w"], n["h"], where(popup, n))
                     for n in empty[:12])))


@needs_qt
def test_no_label_is_truncated_without_declaring_elide(popup):
    """A label that is cut but never asked to elide loses text with no ellipsis.

    Text.truncated is Qt's own answer to "did this fit", so this is not a
    remeasurement of the label — it is the label reporting. Labels that set
    elide, or that wrap, are doing it on purpose and are left alone.
    """
    lost = [n for n in texts(popup)
            if n["truncated"] and not n["elided"] and not n["wrapped"]]
    assert not lost, (
        "%d label(s) cut off without eliding:\n%s"
        % (len(lost),
           "\n".join("  %r needs %.1f px, has %.1f: %s"
                     % (n["text"][:40], n["contentWidth"], n["w"],
                        where(popup, n))
                     for n in lost[:12])))


@needs_qt
def test_the_header_fits_at_the_declared_minimum_width():
    """The popup at Layout.minimumWidth, which is a width the user can drag to.

    The preferred width is the easy case. A popup is resizable down to the
    minimum it declares, so the header has to survive that width too — which is
    the general form of the defect that was fixed: something in the row with no
    minimum of its own setting the row's.
    """
    narrow = render(MAIN_QML, width="minimum")
    bad = overflowing_layout_children(narrow)
    assert not bad, (
        "at the declared minimum width of %.0f px, %d item(s) are placed "
        "outside the layout that owns them:\n%s"
        % (narrow["declared"]["minimumWidth"], len(bad),
           "\n".join("  %s is %.1f wide inside a %.1f-wide parent"
                     % (where(narrow, n), n["w"], p["w"])
                     for n, p in bad[:12])))
