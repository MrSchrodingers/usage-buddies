"""The panel mode that decides for itself what to show.

Six fixed modes were chosen once and never revisited, so the mode picked on a
calm afternoon is still a weekly bar during an outage. The adaptive mode shows
whichever of them matters now — and by doing that acquires two failure modes
that a fixed mode cannot have:

  * it can flicker. A metric sitting on its threshold changes the answer on
    every refresh, and a panel item that changes its face every thirty seconds
    is worse than one that is merely out of date.
  * it can resize. Panel items are laid out in a row, so anything that changes
    width shoves every icon to its right along the panel — and this is the one
    mode that changes its content with nobody touching it.

The decision is pure JavaScript over plain values inside main.qml, and this
file lifts those functions out of the real file and runs a few hundred
simulated refreshes through them in node — the same technique
tests/test_widget_sections.py uses, and for the same reason: a binding
expression can only be checked by reading it.

The width is not arguable from source at all, so it is measured: the compact
representation is loaded into a real QtQuick scene through the doubles in
tests/qmlstubs/ and asked how wide it came out in each state. The positive
control for that instrument is the `full` mode, which *does* change width when
a service incident appears — if the harness cannot see that, its report that
the adaptive mode holds one width means nothing.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
QML = REPO / "plasmoid" / "contents" / "ui" / "main.qml"
KCFG = REPO / "plasmoid" / "contents" / "config" / "main.xml"
STUBS = REPO / "tests" / "qmlstubs"
MEASURE = STUBS / "harness" / "measure_scene.py"

# Same font as tests/test_qml_layout.py, and pinned for the same reason: every
# size in the widget is a multiple of a grid unit, which is the height of one
# line of this font.
FONT_PX = 13

needs_node = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node not installed")
needs_qt = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("PySide6") is None,
    reason="PySide6 missing")


# ── lifting the decision out of main.qml ───────────────────────────────────

PURE = ("adaptiveUrgency", "adaptiveRank", "adaptiveDesired", "adaptiveHolds",
        "pickAdaptive", "pickAdaptiveScope")


def _function_source(text, name):
    """The whole `function name(...) {...}`, matched by counting braces.

    Anchoring on indentation would silently truncate at the first flush line,
    and a truncated body still parses as JavaScript often enough for the
    failure to look like a logic bug rather than a broken extractor.
    """
    at = text.find("function %s(" % name)
    assert at != -1, "function %s not found in main.qml" % name
    start = text.index("{", at)
    depth, i = 1, start + 1
    while i < len(text) and depth:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    assert depth == 0, "unterminated body for %s" % name
    return text[at:i]


def _const(name):
    """A tuning constant, read from main.qml rather than copied into here.

    A second copy of these numbers in this file would agree with itself
    forever: the hysteresis could be set to zero in the widget and every test
    below would go on passing against the value it remembered.
    """
    m = re.search(r"readonly property (?:real|int) %s: (\d+)" % name,
                  QML.read_text())
    assert m, "%s is not declared in main.qml any more" % name
    return int(m.group(1))


DEADBAND = _const("adaptiveDeadband")
DWELL_MS = _const("adaptiveDwellMs")
ETA_ENTER = _const("adaptiveEtaEnterMin")
ETA_HOLD = _const("adaptiveEtaHoldMin")
PACE_TOLERANCE = _const("paceTolerance")
REFRESH_MS = _const("refreshInterval")


@pytest.fixture(scope="session")
def js(tmp_path_factory):
    """The real function bodies plus a signal builder, as a JS module."""
    src = QML.read_text()
    parts = [_function_source(src, name) for name in PURE]
    parts.append("""
// Signals shaped the way adaptiveSignals() shapes them. The tuning constants
// come from main.qml through the test, not from here.
function mk(o) {
  o = o || {};
  var session = o.session === undefined ? 10 : o.session;
  var weekly = o.weekly === undefined ? 0 : o.weekly;
  var warnAt = o.warnAt === undefined ? 75 : o.warnAt;
  var alertAt = o.alertAt === undefined ? 90 : o.alertAt;
  var worst = Math.max(session, weekly);
  // The zone the widget's own usageZone() would return for the worst quota,
  // ignoring pace unless the caller sets paceGap explicitly.
  var zone = o.zone;
  if (zone === undefined) {
    zone = worst >= alertAt ? "alert"
         : worst >= warnAt ? "warn"
         : (o.paceGap !== undefined && o.paceGap > PACE_TOLERANCE) ? "warn"
         : "calm";
  }
  return {
    incident: o.incident === undefined ? "none" : o.incident,
    worstZone: zone,
    pcts: { session: session, weekly: weekly },
    worstScope: weekly > session ? "weekly" : "session",
    worstPct: worst,
    paceGap: o.paceGap === undefined ? -1 : o.paceGap,
    paceTolerance: PACE_TOLERANCE,
    etaMinutes: o.eta === undefined ? -1 : o.eta,
    warnAt: warnAt, alertAt: alertAt,
    deadband: DEADBAND, dwellMs: DWELL_MS,
    etaEnterMin: ETA_ENTER, etaHoldMin: ETA_HOLD
  };
}

// One run of the panel over a sequence of refreshes, counting how often it
// changed its face. `seq` is a list of mk() overrides, one per refresh.
function run(seq, startState) {
  var state = startState || "normal";
  var heldAt = 0;
  var t = 0;
  var changes = 0;
  var seen = [state];
  for (var i = 0; i < seq.length; i++) {
    var out = pickAdaptive(state, heldAt, t, mk(seq[i]));
    if (out.state !== state) { changes++; state = out.state; }
    heldAt = out.heldAt;
    seen.push(state);
    t += REFRESH_MS;
  }
  return { changes: changes, state: state, seen: seen };
}
""")
    parts.append("module.exports = { %s, mk, run };"
                 % ", ".join(PURE))
    path = tmp_path_factory.mktemp("adaptivejs") / "adaptive.js"
    preamble = ("const PACE_TOLERANCE=%d, DEADBAND=%d, DWELL_MS=%d, "
                "ETA_ENTER=%d, ETA_HOLD=%d, REFRESH_MS=%d;\n"
                % (PACE_TOLERANCE, DEADBAND, DWELL_MS, ETA_ENTER, ETA_HOLD,
                   REFRESH_MS))
    path.write_text(preamble + "\n\n".join(parts))
    return path


@pytest.fixture(scope="session")
def call(js):
    node = shutil.which("node")

    def run(expr):
        prog = ("const F = require(%s); Object.assign(globalThis, F); "
                "process.stdout.write(JSON.stringify(%s));"
                % (json.dumps(str(js)), expr))
        r = subprocess.run([node, "-e", prog], capture_output=True, text=True,
                           env=os.environ)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)
    return run


# ── the instrument, before anything it reports is believed ─────────────────

@needs_node
def test_the_extractor_lifts_the_real_functions(call):
    """Everything below runs on text pulled out of main.qml by brace counting.
    If that pulled out the wrong span or a stale copy, the results would still
    be internally consistent and every assertion would pass."""
    assert call('adaptiveDesired(mk({incident: "major"}))') == "incident"
    assert call('adaptiveDesired(mk({}))') == "normal"
    # And it is this file's code rather than a reimplementation: main.qml's own
    # comment came with it.
    body = _function_source(QML.read_text(), "pickAdaptive")
    assert "Rising is immediate, falling is held" in body, body


def test_the_constants_were_read_and_are_not_zero():
    """A hysteresis of zero would let every test below pass while the panel
    blinked: the sequences would simply never change state twice."""
    assert DEADBAND > 0, DEADBAND
    assert DWELL_MS >= 2 * REFRESH_MS, (DWELL_MS, REFRESH_MS)
    assert ETA_HOLD > ETA_ENTER > 0, (ETA_ENTER, ETA_HOLD)
    assert REFRESH_MS == 30000, REFRESH_MS


# ── the order ──────────────────────────────────────────────────────────────

@needs_node
@pytest.mark.parametrize("overrides,want", [
    ({"incident": "major", "session": 95}, "incident"),
    ({"incident": "critical", "session": 95}, "incident"),
    # A degraded service is not an outage: work continues, so a spent quota
    # outranks it.
    ({"incident": "minor", "session": 95}, "quota"),
    ({"incident": "minor", "eta": 30}, "incident"),
    ({"incident": "minor"}, "incident"),
    ({"session": 95}, "quota"),
    ({"weekly": 95}, "quota"),
    ({"eta": 30}, "eta"),
    ({"session": 80}, "eta"),
    ({"paceGap": PACE_TOLERANCE + 5}, "eta"),
    ({"eta": ETA_ENTER + 60}, "normal"),
    ({}, "normal"),
])
def test_the_priority_order(call, overrides, want):
    got = call("adaptiveDesired(mk(%s))" % json.dumps(overrides))
    assert got == want, "%s -> %s, wanted %s" % (overrides, got, want)


@needs_node
def test_escalation_does_not_wait_for_the_dwell(call):
    """A late warning is the one failure this widget cannot afford. The dwell
    holds the way down, never the way up."""
    got = call('pickAdaptive("normal", 0, 1, mk({session: 95})).state')
    assert got == "quota", got
    got = call('pickAdaptive("quota", 0, 1, '
               'mk({session: 95, incident: "major"})).state')
    assert got == "incident", got


@needs_node
def test_an_outage_takes_over_from_a_degraded_service_at_once(call):
    """The state name is the same either way, so this is the case a naive
    'did the state change' check would miss entirely."""
    seen = call('run([{incident: "minor"}, {incident: "major", session: 95}],'
                ' "normal")')
    assert seen["seen"][-1] == "incident", seen
    got = call('pickAdaptive("incident", 0, 1, '
               'mk({incident: "minor", session: 95})).state')
    assert got == "quota", (
        "a quota in the red did not take the panel from a merely degraded "
        "service: %s" % got)


# ── flicker ────────────────────────────────────────────────────────────────

@needs_node
def test_a_quota_sitting_on_the_threshold_does_not_make_the_panel_blink(call):
    """The defect this is about, in its simplest shape.

    A quota oscillating either side of the alert boundary answers a different
    question on every refresh. Twenty refreshes is ten minutes of real time,
    and without hysteresis it is ten face changes.
    """
    seq = [{"session": 90.1 if i % 2 == 0 else 89.9} for i in range(20)]
    out = call("run(%s)" % json.dumps(seq))
    assert out["changes"] == 1, (
        "the panel changed %d times over %d refreshes with the quota sitting "
        "on the boundary; states seen: %s"
        % (out["changes"], len(seq), out["seen"]))
    assert out["state"] == "quota", out


@needs_node
def test_the_eta_boundary_does_not_blink_either(call):
    """The ETA is a projection recomputed from a re-averaged burn rate, so
    unlike a percentage it moves in both directions between refreshes."""
    seq = [{"eta": ETA_ENTER - 1 if i % 2 == 0 else ETA_ENTER + 1}
           for i in range(20)]
    out = call("run(%s)" % json.dumps(seq))
    assert out["changes"] == 1, (out["changes"], out["seen"])
    assert out["state"] == "eta", out


@needs_node
def test_an_incident_flapping_between_refreshes_does_not_blink(call):
    """status.anthropic.com can answer 'none' once mid-incident; the panel
    must not treat that as the incident being over."""
    seq = [{"incident": "major" if i % 2 == 0 else "none"} for i in range(20)]
    out = call("run(%s)" % json.dumps(seq))
    assert out["changes"] == 1, (out["changes"], out["seen"])
    assert out["state"] == "incident", out


@needs_node
def test_a_state_whose_reason_is_really_gone_is_given_up(call):
    """Hysteresis that never releases is just a different fixed mode.

    A window reset drops the quota by tens of points at once, which clears the
    deadband immediately — so what is left holding the state is the dwell, and
    it has to expire.
    """
    still_held = call('pickAdaptive("quota", 0, %d, mk({session: 5})).state'
                      % (DWELL_MS - 1))
    assert still_held == "quota", (
        "the panel dropped the state %d ms in, before the %d ms dwell"
        % (DWELL_MS - 1, DWELL_MS))
    released = call('pickAdaptive("quota", 0, %d, mk({session: 5})).state'
                    % DWELL_MS)
    assert released == "normal", released


@needs_node
def test_the_deadband_is_what_holds_it_and_not_only_the_dwell(call):
    """Distinguishes the two mechanisms. Long after the dwell has expired, a
    quota a point under the alert boundary still holds the state; one well
    below it does not."""
    hour = 3600000
    near = call('pickAdaptive("quota", 0, %d, mk({session: 89})).state' % hour)
    assert near == "quota", (
        "with only a dwell, a quota one point under the boundary would have "
        "been given up an hour later")
    # A point past the release margin the state does go. Which state it goes
    # to is the priority order's business — 86%% is still over the warning —
    # so what is asserted is that it is no longer the alert one.
    far = call('pickAdaptive("quota", 0, %d, mk({session: %d})).state'
               % (hour, 90 - DEADBAND - 1))
    assert far != "quota", far


@needs_node
def test_the_deadband_follows_a_configured_threshold(call):
    """The margin is relative to the pair in force, not to 90."""
    held = call('pickAdaptive("quota", 0, 3600000, '
                'mk({session: 60, warnAt: 50, alertAt: 62})).state')
    assert held == "quota", held
    gone = call('pickAdaptive("quota", 0, 3600000, '
                'mk({session: %d, warnAt: 40, alertAt: 62})).state'
                % (62 - DEADBAND - 1))
    assert gone != "quota", gone


# ── which quota it describes ───────────────────────────────────────────────

@needs_node
def test_two_quotas_a_hair_apart_do_not_trade_the_icon(call):
    """One level below the state machine, and the same defect: the icon says
    which window the number belongs to, and swapping it every refresh is the
    same flicker."""
    prog = """(function () {
      var scope = "session", swaps = 0;
      for (var i = 0; i < 20; i++) {
        var s = mk({session: 60, weekly: i %% 2 === 0 ? 60.2 : 59.8});
        var next = pickAdaptiveScope(scope, s);
        if (next !== scope) { swaps++; scope = next; }
      }
      return {swaps: swaps, scope: scope};
    })()"""
    out = call(prog % ())
    assert out["swaps"] == 0, out
    assert out["scope"] == "session", out


@needs_node
def test_a_quota_that_really_is_worse_does_take_over(call):
    """The margin has to be a margin, not a lock."""
    got = call('pickAdaptiveScope("session", mk({session: 40, weekly: 95}))')
    assert got == "weekly", got


@needs_node
def test_an_unknown_incumbent_is_replaced_rather_than_kept(call):
    """First evaluation, or a scope the payload stopped reporting."""
    assert call('pickAdaptiveScope("", mk({session: 40, weekly: 95}))') == "weekly"
    assert call('pickAdaptiveScope("mars", mk({session: 40, weekly: 95}))') == "weekly"


# ── it must not become the default ─────────────────────────────────────────

def _kcfg_defaults():
    root = ET.parse(KCFG).getroot()
    out = {}
    for entry in root.iter():
        if not entry.tag.endswith("entry"):
            continue
        for child in entry:
            if child.tag.endswith("default"):
                out[entry.get("name")] = (child.text or "").strip()
    return out


def test_adaptive_is_reachable_but_is_not_what_anybody_gets_by_default():
    """Somebody who chose a mode chose it. A new mode that installs itself
    over that choice is a defect, not a feature."""
    defaults = _kcfg_defaults()
    assert defaults["displayMode"] == "full", defaults["displayMode"]

    src = QML.read_text()
    # Anchored on a mode only this list has: there is a second `modes` array
    # in the file, for the companion's chatter setting, and matching it
    # instead would have this test reporting on something else entirely.
    m = re.search(r'readonly property var modes: \[([^\]]*"weeklyBarOnly"[^\]]*)\]',
                  src)
    assert m, "the panel mode cycle is gone from main.qml"
    modes = [s.strip().strip('"') for s in m.group(1).split(",")]
    assert "adaptive" in modes, modes
    assert modes[-1] == "adaptive", (
        "adaptive was inserted into the cycle rather than appended; the order "
        "everyone has learned by clicking through it changed: %s" % modes)
    assert modes[0] == "full", modes


def test_the_mode_has_an_icon_and_a_label_in_both_languages():
    """A mode with no entry in modeIcons falls back to a generic cog, and one
    with no label shows its own identifier in the tooltip."""
    src = QML.read_text()
    assert re.search(r'"adaptive":\s*"[a-z-]+"', src), "no icon for the mode"
    assert 'root.tr("panelAdaptive")' in src, "the label is not translated"


@pytest.mark.parametrize("key", ["panelAdaptive", "adaptiveIncident",
                                 "adaptiveQuota", "adaptiveEta",
                                 "adaptiveNormal"])
def test_every_new_string_exists_in_both_languages(key):
    """tr() falls back to English and then to the key itself, so a missing
    Portuguese entry renders a bare identifier and raises nothing."""
    text = QML.read_text()
    tables = {}
    for lang in ("en", "pt"):
        at = text.index('"%s": {' % lang)
        start = text.index("{", at)
        depth, i = 1, start + 1
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        tables[lang] = dict(re.findall(
            r'"([A-Za-z0-9_]+)":\s*"((?:[^"\\]|\\.)*)"', text[start:i]))
    assert len(tables["en"]) > 100 and len(tables["pt"]) > 100, (
        "the table parser did not find the real tables")
    for lang in ("en", "pt"):
        assert key in tables[lang], "%s missing from the %s table" % (key, lang)
        assert tables[lang][key].strip(), (key, lang)
    assert tables["en"][key] != tables["pt"][key], (
        "%s is the same string in both tables; it was probably not translated"
        % key)


def test_no_emoji_in_the_new_strings():
    """A literal pictograph is the obvious one; the escape is what slips
    through review, because "\\u{1F4B0}" is plain ASCII in the file."""
    text = QML.read_text()
    for key in ("panelAdaptive", "adaptiveIncident", "adaptiveQuota",
                "adaptiveEta", "adaptiveNormal"):
        for m in re.finditer(r'"%s":\s*"([^"]*)"' % key, text):
            value = m.group(1)
            assert "\\u" not in value, (key, value)
            assert all(ord(c) < 0x2190 for c in value), (key, value)


# ── the width, measured ────────────────────────────────────────────────────
#
# Everything above is arithmetic. This is geometry, and there is no reading it
# out of the source: the compact representation is loaded into a QtQuick scene
# through the doubles in tests/qmlstubs/ and asked how wide it came out.

PROBE = '''
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami

// Written by tests/test_adaptive_panel.py. Loads the real main.qml through the
// doubles, hands it one payload, and instantiates the compact representation
// the way a panel does — then reports what the panel would have been.
Item {
    id: probe
    width: 400; height: 60

    readonly property int widgetStatus: widgetLoader.status
    readonly property int repStatus: repLoader.status
    readonly property real compactWidth: repLoader.item ? repLoader.item.Layout.preferredWidth : -1
    readonly property real compactMinimumWidth: repLoader.item ? repLoader.item.Layout.minimumWidth : -1
    readonly property int repChildren: repLoader.item ? repLoader.item.children.length : -1
    readonly property string adaptiveState: widgetLoader.item ? widgetLoader.item.adaptiveState : "?"
    readonly property string adaptiveScope: widgetLoader.item ? widgetLoader.item.adaptiveScope : "?"
    readonly property string adaptiveIcon: widgetLoader.item ? widgetLoader.item.adaptiveIcon : "?"
    readonly property real adaptivePct: widgetLoader.item ? widgetLoader.item.adaptivePct : -1
    readonly property real warnAt: widgetLoader.item ? widgetLoader.item.warnAt : -1
    readonly property real alertAt: widgetLoader.item ? widgetLoader.item.alertAt : -1
    readonly property string displayMode: widgetLoader.item ? widgetLoader.item.displayMode : "?"
    readonly property int iconSlot: Kirigami.Units.iconSizes.smallMedium
    readonly property int spacing: Kirigami.Units.smallSpacing

    Loader {
        id: widgetLoader
        source: "__MAIN_QML__"
        onLoaded: {
            Plasmoid.setConfiguration("displayMode", __MODE__);
            item.usageData = JSON.parse(__PAYLOAD__);
            repLoader.sourceComponent = item.compactRepresentation;
        }
    }

    Loader { id: repLoader; width: 300; height: 40 }
}
'''

_PROBES = {}


def _probe(tmp_path_factory, payload, mode="adaptive"):
    """Render one compact representation and return the probe's properties."""
    key = (mode, json.dumps(payload, sort_keys=True))
    if key in _PROBES:
        return _PROBES[key]
    qml = (PROBE
           .replace("__MAIN_QML__", QML.as_uri())
           .replace("__MODE__", json.dumps(mode))
           .replace("__PAYLOAD__", json.dumps(json.dumps(payload))))
    path = tmp_path_factory.mktemp("probe") / "AdaptiveProbe.qml"
    path.write_text(qml)

    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_QUICK_BACKEND"] = "software"
    env["QT_SCALE_FACTOR"] = "1"
    env.pop("QT_FONT_DPI", None)
    env.pop("QT_SCREEN_SCALE_FACTORS", None)
    proc = subprocess.run([sys.executable, str(MEASURE), "--qml", str(path),
                           "--font-px", str(FONT_PX), "--stubs", str(STUBS)],
                          capture_output=True, text=True, env=env,
                          cwd=str(REPO), timeout=300)
    assert proc.returncode == 0 and proc.stdout.strip(), (
        "the probe did not run (exit %d)\n%s\n%s"
        % (proc.returncode, proc.stdout, proc.stderr))
    result = json.loads(proc.stdout)
    assert result.get("ok"), result
    values = result["values"]
    # Loader.Ready is 1. A representation that failed to instantiate reports
    # width -1, and every width comparison below would then be comparing -1
    # with -1 and passing.
    assert values["widgetStatus"] == 1, ("main.qml did not load", values)
    assert values["repStatus"] == 1, ("the compact representation did not "
                                      "instantiate", values)
    assert values["compactWidth"] > 0, values
    _PROBES[key] = values
    return values


def _calm():
    return {"rateLimits": {"source": "api", "plan": "Max (20x)",
                           "session": {"percentUsed": 12.0, "windowHours": 5,
                                       "resetsAt": "2099-01-01T00:00:00+00:00"},
                           "weeklyAll": {"percentUsed": 9.0,
                                         "resetsAt": "2099-01-01T00:00:00+00:00"}},
            "serviceStatus": {"indicator": "none",
                              "description": "All Systems Operational",
                              "active_incidents": []}}


def _with(**changes):
    data = _calm()
    for key, value in changes.items():
        if key == "session":
            data["rateLimits"]["session"]["percentUsed"] = value
        elif key == "weekly":
            data["rateLimits"]["weeklyAll"]["percentUsed"] = value
        elif key == "incident":
            data["serviceStatus"]["indicator"] = value
        elif key == "eta":
            data["limitEta"] = {"minutesToLimit": value, "label": "45m"}
        elif key == "thresholds":
            data["thresholds"] = value
        else:
            raise AssertionError("unknown key %s" % key)
    return data


SCENARIOS = {
    "normal": _calm(),
    "quota-session": _with(session=95.0),
    "quota-weekly": _with(weekly=97.0),
    "incident": _with(incident="major"),
    "eta": _with(eta=45),
    "no-data": {},
}


@needs_qt
def test_the_panel_reaches_the_state_the_data_implies(tmp_path_factory):
    """The wiring, not the arithmetic: the state machine is driven by a
    property change handler, and a handler that reads a binding over the same
    property reads the *previous* refresh's value. That is not a hypothetical
    — it is how this was written first, and the panel sat in "normal" with a
    quota at 95% for as long as it ran.
    """
    states = {name: _probe(tmp_path_factory, payload)["adaptiveState"]
              for name, payload in SCENARIOS.items()}
    assert states["normal"] == "normal", states
    assert states["quota-session"] == "quota", states
    assert states["quota-weekly"] == "quota", states
    assert states["incident"] == "incident", states
    assert states["eta"] == "eta", states


@needs_qt
def test_the_panel_says_which_window_the_number_belongs_to(tmp_path_factory):
    session = _probe(tmp_path_factory, SCENARIOS["quota-session"])
    weekly = _probe(tmp_path_factory, SCENARIOS["quota-weekly"])
    assert session["adaptiveScope"] == "session", session
    assert weekly["adaptiveScope"] == "weekly", weekly
    assert session["adaptiveIcon"] != weekly["adaptiveIcon"], (
        "both quotas are drawn with the same icon, so the panel shows a "
        "percentage with nothing saying which window it is of")
    assert round(session["adaptivePct"]) == 95, session
    assert round(weekly["adaptivePct"]) == 97, weekly


@needs_qt
def test_the_instrument_can_see_a_panel_mode_changing_width(tmp_path_factory):
    """The positive control for the measurement below.

    `full` grows when a service incident appears — it adds a dot and the word
    "Outage". If the harness cannot see that, its report that the adaptive
    mode holds one width is a report that it is measuring nothing.
    """
    calm = _probe(tmp_path_factory, SCENARIOS["normal"], mode="full")
    outage = _probe(tmp_path_factory, SCENARIOS["incident"], mode="full")
    assert outage["compactWidth"] > calm["compactWidth"] + 1, (
        "the fixed `full` mode measured the same width with and without an "
        "incident (%s vs %s); the harness is not seeing width at all"
        % (calm["compactWidth"], outage["compactWidth"]))


@needs_qt
def test_the_adaptive_panel_holds_one_width_in_every_state(tmp_path_factory):
    """A panel item that resizes shoves every icon to its right along the
    panel, and this is the mode that changes its content on its own."""
    widths = {name: _probe(tmp_path_factory, payload)["compactWidth"]
              for name, payload in SCENARIOS.items()}
    states = {name: _probe(tmp_path_factory, payload)["adaptiveState"]
              for name, payload in SCENARIOS.items()}
    assert len(set(states.values())) >= 4, (
        "the scenarios did not reach four different states, so a constant "
        "width proves nothing: %s" % states)
    assert len(set(widths.values())) == 1, (
        "the adaptive panel changes width between states: %s" % widths)


@needs_qt
def test_the_pinned_label_is_really_measuring_text(tmp_path_factory):
    """A TextMetrics that reported zero would make the width constant for the
    wrong reason, and every check above would still pass."""
    values = _probe(tmp_path_factory, SCENARIOS["normal"])
    fixed = values["iconSlot"] + 34 + 2 * values["spacing"]
    assert values["compactWidth"] > fixed + 5, (
        "the adaptive panel is %s px wide against %s px of fixed parts; the "
        "label is contributing nothing, so its pin is not measuring"
        % (values["compactWidth"], fixed))


@needs_qt
def test_the_widget_paints_the_pair_the_collector_published(tmp_path_factory):
    """The binding, evaluated rather than read.

    tests/test_usage_alerts.py checks the same property by running the
    resolution function in node; this checks that the QML property is actually
    bound to it, which no amount of reading the file can establish.
    """
    values = _probe(tmp_path_factory,
                    _with(session=95.0, thresholds={"warn": 63, "alert": 81}))
    assert values["warnAt"] == 63, values
    assert values["alertAt"] == 81, values

    default = _probe(tmp_path_factory, SCENARIOS["normal"])
    assert default["warnAt"] == 75 and default["alertAt"] == 90, default
