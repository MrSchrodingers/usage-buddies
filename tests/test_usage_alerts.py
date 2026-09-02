"""Threshold alerts fire while there is still something to do about it.

The only events were at 100%, which is the point where the decision to slow
down has already been made for you. These fire at 75% and 90%, and the hard
part is not firing them again: this runs every 30 seconds, so a naive
comparison produces a toast twice a minute for hours.
"""
import pytest


def _ids(events):
    """Events carry scope and percentage now, so the message can name the quota."""
    return [e["id"] if isinstance(e, dict) else e for e in events]


def _data(session=None, weekly=None):
    # source=api: alerts only fire on measured data. The local_estimate branch
    # saturates at 100% for heavy users and used to announce an exhausted quota.
    rl = {"source": "api"}
    if session is not None:
        rl["session"] = session
    if weekly is not None:
        rl["weeklyAll"] = weekly
    return {"rateLimits": rl}


def _sess(pct, resets="2026-09-01T00:00:00Z"):
    return {"percentUsed": pct, "resetsAt": resets}


def test_warn_fires_once_when_crossing(collector):
    prev = {"measured": True, "session": {"percentUsed": 70, "resetsAt": "2026-09-01T00:00:00Z", "fired": []}}
    events, snap = collector.detect_usage_transitions(prev, _data(session=_sess(76)))
    assert "sessionWarn" in _ids(events)
    assert collector.USAGE_WARN_AT in snap["session"]["fired"]


def test_warn_does_not_repeat_every_run(collector):
    """30s timer: a threshold that re-fires is a toast twice a minute."""
    state = {"measured": True, "session": {"percentUsed": 70, "resetsAt": "2026-09-01T00:00:00Z", "fired": []}}
    fired_total = 0
    for pct in (76, 77, 78, 79, 80, 81):
        events, state = collector.detect_usage_transitions(state, _data(session=_sess(pct)))
        fired_total += _ids(events).count("sessionWarn")
    assert fired_total == 1, f"warn fired {fired_total} times across one window"


def test_alert_suppresses_warn_when_both_cross_at_once(collector):
    """Jumping straight past both thresholds must not stack two toasts saying
    the same thing."""
    prev = {"measured": True, "session": {"percentUsed": 10, "resetsAt": "2026-09-01T00:00:00Z", "fired": []}}
    events, snap = collector.detect_usage_transitions(prev, _data(session=_sess(95)))
    assert _ids(events).count("sessionAlert") == 1
    assert "sessionWarn" not in _ids(events)
    # both are recorded, so neither fires later in the same window
    assert set(snap["session"]["fired"]) == {collector.USAGE_WARN_AT, collector.USAGE_ALERT_AT}


def test_new_window_rearms_the_thresholds(collector):
    """Without re-arming, a quota warned about once is never warned about again.

    prev_pct is kept at 2 on purpose. The reset branch also clears `fired`, but
    only when the previous window had more than 5% used — with 80% there, this
    test passes even with the re-arm removed, which is how the first version of
    it proved nothing.
    """
    state = {"measured": True, "session": {"percentUsed": 2,
                         "resetsAt": "2026-09-01T00:00:00Z",
                         "fired": [collector.USAGE_WARN_AT]}}
    events, state = collector.detect_usage_transitions(
        state, _data(session=_sess(3, "2026-09-01T05:00:00Z")))
    assert "sessionReset" not in _ids(events), (
        "the reset branch fired and would clear `fired` on its own; "
        "this test would then pass without any re-arm logic"
    )
    assert state["session"]["fired"] == [], "thresholds not re-armed for the new window"
    events, state = collector.detect_usage_transitions(
        state, _data(session=_sess(78, "2026-09-01T05:00:00Z")))
    assert "sessionWarn" in _ids(events)


def test_thresholds_do_not_fire_at_or_past_100(collector):
    """sessionEnded already covers that; a warn alongside it is noise."""
    prev = {"measured": True, "session": {"percentUsed": 50, "resetsAt": "2026-09-01T00:00:00Z", "fired": []}}
    events, _ = collector.detect_usage_transitions(prev, _data(session=_sess(100)))
    assert "sessionEnded" in _ids(events)
    assert "sessionWarn" not in _ids(events) and "sessionAlert" not in events


def test_weekly_scope_has_its_own_thresholds(collector):
    prev = {"measured": True, "weeklyAll": {"percentUsed": 70, "resetsAt": "2026-09-05T00:00:00Z", "fired": []}}
    events, _ = collector.detect_usage_transitions(prev, _data(weekly=_sess(91, "2026-09-05T00:00:00Z")))
    assert "weeklyAlert" in _ids(events)


def test_every_event_id_has_defaults(collector):
    """A fired event with no defaults entry is silently dropped by
    notify_usage_event()."""
    prev = {"measured": True, "session": {"percentUsed": 10, "resetsAt": "2026-09-01T00:00:00Z", "fired": []},
            "weeklyAll": {"percentUsed": 10, "resetsAt": "2026-09-05T00:00:00Z", "fired": []}}
    events, _ = collector.detect_usage_transitions(
        prev, _data(session=_sess(95), weekly=_sess(95, "2026-09-05T00:00:00Z")))
    assert events, "no events produced; test proves nothing"
    for event_id in _ids(events):
        assert event_id in collector.USAGE_EVENT_DEFAULTS, f"{event_id} has no defaults"


@pytest.mark.parametrize("field", ["sound", "winSound", "urgency", "title", "body"])
def test_new_defaults_are_complete(collector, field):
    for event_id in ("sessionWarn", "sessionAlert", "weeklyWarn", "weeklyAlert"):
        assert collector.USAGE_EVENT_DEFAULTS[event_id].get(field), f"{event_id}.{field}"


# ── the bar and the toast are drawn from one number ────────────────────────
#
# What used to be here compared two literals: `USAGE_WARN_AT = 75` against
# `readonly property real warnAt: 75`. That is a check on the defaults and
# nothing else. The moment the pair became configurable it would have gone on
# passing while the widget painted 75 and the collector announced 60 — and both
# ways of getting that wrong are silent. The bar goes red and no notification
# arrives, or a notification arrives about a bar that is still amber.
#
# The property that actually matters is that there is one number. The collector
# resolves the pair once, fires its notifications on it, and publishes it in
# widget-data.json; the widget paints from what was published. These check that
# chain end to end, with a pair that is not the default, using the real code on
# both sides rather than a transcription of it.

import json
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
QML = REPO / "plasmoid" / "contents" / "ui" / "main.qml"
COLLECTOR_SRC = REPO / "scripts" / "usage-buddies-collector.py"

needs_node = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node not installed")


def _qml_function(name):
    """The whole `function name(...) {...}` out of main.qml, by counting braces.

    Anchoring on indentation would truncate at the first flush line, and a
    truncated body still parses as JavaScript often enough for the failure to
    look like a logic bug.
    """
    text = QML.read_text()
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


def _resolve_in_node(published, configured):
    """main.qml's own threshold resolution, run on real values."""
    src = "\n".join(_qml_function(n) for n in
                    ("cleanThreshold", "thresholdPair", "resolveThresholds"))
    prog = (src + "\nprocess.stdout.write(JSON.stringify(resolveThresholds("
            + json.dumps(published) + ", " + json.dumps(configured) + ")));")
    r = subprocess.run([shutil.which("node"), "-e", prog],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.fixture
def configured(collector, tmp_path, monkeypatch):
    """A collector pointed at a config of its own, never the real one."""
    monkeypatch.setattr(collector, "CONFIG_FILE",
                        tmp_path / "widget-config.json")
    return collector


@needs_node
def test_the_extractor_lifts_the_real_resolution(collector):
    """Every check below runs on text pulled out of main.qml. If that pulled
    out the wrong span, the numbers would still be self-consistent."""
    body = _qml_function("resolveThresholds")
    assert "thresholdPair(published)" in body, body
    assert "thresholdPair(configured)" in body, body
    # And it is this file's code rather than a reimplementation that drifted:
    # main.qml's own comment came along with it.
    assert "Published first, always" in body, body


@needs_node
def test_the_widget_paints_the_pair_the_collector_fired_on(configured):
    """One number, crossing the language boundary.

    Configure 63/81, then follow it: out of the config file, through the
    collector's resolution, into the block it publishes, and out of the
    widget's own resolution run against that block. And the alert path has to
    be firing on the same pair, not on 75 — a payload carrying 63 while the
    notification still waits for 75 is the exact defect this replaces.
    """
    assert configured.set_usage_thresholds(63, 81) == (63, 81)
    cfg = configured.load_config()

    published = configured.thresholds_payload(cfg)
    assert published == {"warn": 63, "alert": 81}, published

    painted = _resolve_in_node(published, None)
    assert painted == {"warn": 63, "alert": 81}, (
        "the widget resolved %r from the pair the collector published %r"
        % (painted, published))

    # The alert side of the same pair. 64% is over the configured warning and
    # well under the default one, so a collector still holding 75 stays silent.
    events, _ = configured.detect_usage_transitions(
        {"measured": True, "session": {"percentUsed": 60,
                                       "resetsAt": "2026-09-01T00:00:00Z",
                                       "fired": []}},
        _data(session=_sess(64)),
        configured.usage_thresholds(cfg))
    assert "sessionWarn" in _ids(events), (
        "64%% raised nothing with the warning configured at %s" % published["warn"])


def test_the_production_alert_path_resolves_from_the_config(configured,
                                                            monkeypatch):
    """process_usage_events() is what main() calls, and it is where the pair
    could quietly go on being the module constant."""
    configured.set_usage_thresholds(63, 81)
    cfg = configured.load_config()

    fired = []
    monkeypatch.setattr(configured, "notify_usage_event",
                        lambda ev, config: fired.append(ev["id"]))
    monkeypatch.setattr(configured, "_load_events_state",
                        lambda: {"measured": True,
                                 "session": {"percentUsed": 60,
                                             "resetsAt": "2026-09-01T00:00:00Z",
                                             "fired": []}})
    monkeypatch.setattr(configured, "_save_events_state", lambda snap: None)

    configured.process_usage_events(_data(session=_sess(64)), cfg)
    assert "sessionWarn" in fired, (
        "the configured warning at 63%% did not fire at 64%%; fired=%r" % fired)


def test_what_is_published_is_what_build_widget_data_writes():
    """The one link above that is textual rather than executed: that the block
    the tests read is the block the collector puts in the file. Checked here
    rather than by running the collection, which needs the network and the
    browser cookies."""
    src = COLLECTOR_SRC.read_text()
    assert '"thresholds": thresholds_payload(config),' in src, (
        "build_widget_data no longer publishes thresholds_payload(); the "
        "checks above are then measuring a function nothing calls")


@needs_node
def test_an_installation_that_configured_nothing_is_unchanged(collector):
    """Three places carry the default pair — main.xml, the collector, and the
    widget's last-resort fallback — and they have to be the same pair, or
    'unchanged' means three different things depending on which one answers.
    """
    import xml.etree.ElementTree as ET
    kcfg = ET.parse(REPO / "plasmoid" / "contents" / "config" / "main.xml").getroot()
    defaults = {}
    for entry in kcfg.iter():
        if not entry.tag.endswith("entry"):
            continue
        for child in entry:
            if child.tag.endswith("default"):
                defaults[entry.get("name")] = (child.text or "").strip()

    assert defaults.get("usageWarnAt") == str(collector.USAGE_WARN_AT), defaults
    assert defaults.get("usageAlertAt") == str(collector.USAGE_ALERT_AT), defaults
    assert collector.usage_thresholds({}) == (collector.USAGE_WARN_AT,
                                              collector.USAGE_ALERT_AT)
    assert _resolve_in_node(None, None) == {"warn": collector.USAGE_WARN_AT,
                                            "alert": collector.USAGE_ALERT_AT}
