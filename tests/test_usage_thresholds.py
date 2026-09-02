"""The alert thresholds became configurable, and the file they travel in has
two writers.

`~/.claude/widget-config.json` was already read and written by the collector,
which stores `org_id` there the first time it detects one. The thresholds go
through the same file, written by the widget. Neither side may drop a key it
does not recognise, and `org_id` is the one that matters: without it every
remote read in the collector fails, and it is not something the user can type
back in — it is detected from a browser cookie.

Two writers doing read-modify-write on one file is the classic lost update.
Both reads see the same content, both writes go through, and whichever
finished first is gone. It does not need a busy machine: the collector's write
happens right after a network call, which is a window measured in seconds.

What this file checks:

  * a threshold write preserves org_id and sounds, and vice versa;
  * a second writer arriving in the middle of the first one's
    read-modify-write ends up with both keys, which is only true because the
    lock is held across the read as well as the write;
  * every shape the file can hold falls back to the default pair instead of
    disabling the alert or painting an inverted one;
  * the command line the widget builds is the one the collector parses;
  * the dialog cannot be used to set the warning above the alert.
"""
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
COLLECTOR = REPO / "scripts" / "usage-buddies-collector.py"
QML = REPO / "plasmoid" / "contents" / "ui" / "main.qml"
CONFIG_QML = REPO / "plasmoid" / "contents" / "ui" / "configGeneral.qml"


@pytest.fixture
def cfg(collector, tmp_path, monkeypatch):
    """The collector, pointed at a config file of its own.

    Never the real one. There is a widget on this machine reading
    ~/.claude/widget-config.json, and a test that writes there would be
    changing the thresholds of the installation it is running on.
    """
    monkeypatch.setattr(collector, "CONFIG_FILE", tmp_path / "widget-config.json")
    return collector


def _written(collector):
    return json.loads(collector.CONFIG_FILE.read_text(encoding="utf-8"))


# ── the instrument ─────────────────────────────────────────────────────────

def test_the_fixture_really_redirects_the_config(cfg, tmp_path):
    """Every assertion below is about a file. If that file were the real one,
    they would all still pass — while rewriting the operator's config."""
    cfg.set_usage_thresholds(60, 85)
    assert cfg.CONFIG_FILE.parent == tmp_path
    assert cfg.CONFIG_FILE.exists()
    # And the lock lands beside it, not beside the real config.
    assert cfg._config_lock_path().parent == tmp_path


# ── neither writer may drop the other's keys ───────────────────────────────

def test_writing_a_threshold_keeps_org_id_and_sounds(cfg):
    """org_id is detected from a browser cookie, once. Losing it is not a
    setting reverting to a default, it is the collection stopping."""
    cfg.update_config(lambda c: c.update({
        "org_id": "e3b0c442-98fc-1c14-9afb-f4c8996fb924",
        "notifications": {"sounds": {"sessionWarn": "bell",
                                     "sessionWarnWin": "Asterisk"},
                          "enabled": True},
        "somethingAFutureVersionWrote": [1, 2, 3],
    }))

    cfg.set_usage_thresholds(63, 81)

    written = _written(cfg)
    assert written["org_id"] == "e3b0c442-98fc-1c14-9afb-f4c8996fb924"
    assert written["notifications"]["sounds"]["sessionWarn"] == "bell"
    assert written["notifications"]["sounds"]["sessionWarnWin"] == "Asterisk"
    assert written["somethingAFutureVersionWrote"] == [1, 2, 3]
    assert written["thresholds"] == {"warn": 63, "alert": 81}


def test_storing_org_id_keeps_the_thresholds(cfg):
    """The other direction, which is the one that runs on a live machine: the
    widget configures a pair, and the collector then detects an org."""
    cfg.set_usage_thresholds(63, 81)
    cfg.update_config(lambda c: c.__setitem__("org_id", "org-abc"))

    written = _written(cfg)
    assert written["thresholds"] == {"warn": 63, "alert": 81}
    assert written["org_id"] == "org-abc"


def test_a_key_under_thresholds_that_this_version_does_not_know_survives(cfg):
    """Same rule one level down. The sub-dict is merged, not replaced."""
    cfg.update_config(lambda c: c.__setitem__(
        "thresholds", {"warn": 70, "alert": 88, "hysteresis": 4}))
    cfg.set_usage_thresholds(63, 81)
    assert _written(cfg)["thresholds"] == {"warn": 63, "alert": 81,
                                           "hysteresis": 4}


def test_a_writer_arriving_mid_write_loses_nothing(cfg):
    """The lost update, staged deterministically.

    Writer A is held inside its mutation — that is, after the read and before
    the write — while writer B runs from start to finish. Without a lock held
    across all three steps, B's write lands and A's then overwrites it with
    the content A read before B existed, and B's key is gone with no error
    anywhere.

    B is checked to be still blocked while A holds the lock, which is what
    distinguishes "serialised" from "lucky ordering".
    """
    inside_a = threading.Event()
    release_a = threading.Event()

    def slow_mutation(config):
        config["from_a"] = "a"
        inside_a.set()
        assert release_a.wait(10), "the test never released writer A"

    a = threading.Thread(target=lambda: cfg.update_config(slow_mutation))
    a.start()
    assert inside_a.wait(10), "writer A never entered its mutation"

    b = threading.Thread(
        target=lambda: cfg.update_config(lambda c: c.__setitem__("from_b", "b")))
    b.start()
    b.join(0.5)
    assert b.is_alive(), (
        "the second writer completed while the first still held the config "
        "open; nothing is serialising them")

    release_a.set()
    a.join(10)
    b.join(10)
    assert not a.is_alive() and not b.is_alive()

    written = _written(cfg)
    assert written.get("from_a") == "a", written
    assert written.get("from_b") == "b", written


def test_a_mutation_that_raises_leaves_the_file_as_it_was(cfg):
    """A write that fails half way is worse than one that does not happen:
    load_config() cannot parse a truncated file and answers {}, which is
    org_id gone."""
    cfg.update_config(lambda c: c.__setitem__("org_id", "org-abc"))
    before = cfg.CONFIG_FILE.read_text(encoding="utf-8")

    def explode(config):
        config["org_id"] = "clobbered"
        raise RuntimeError("boom")

    assert cfg.update_config(explode) is None
    assert cfg.CONFIG_FILE.read_text(encoding="utf-8") == before
    assert cfg.load_config()["org_id"] == "org-abc"


def test_no_temporary_file_is_left_behind(cfg):
    """The rename is what makes the write atomic; a temp file surviving it
    means the rename did not happen."""
    cfg.set_usage_thresholds(63, 81)
    leftovers = [p.name for p in cfg.CONFIG_FILE.parent.iterdir()
                 if ".tmp" in p.name]
    assert leftovers == [], leftovers


# ── the file is untrusted text ─────────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    {"warn": "75", "alert": "90"},          # numbers as strings
    {"warn": None, "alert": None},
    {"warn": True, "alert": False},         # bool is an int in Python
    {"warn": 0, "alert": 90},               # under the floor
    {"warn": 75, "alert": 100},             # 100 can never fire
    {"warn": 75, "alert": 1e309},           # inf
    {"warn": float("nan"), "alert": 90},
    {"warn": 95, "alert": 80},              # inverted
    {"warn": 80, "alert": 80},              # equal is inverted too
    {},
    {"warn": [75], "alert": {"x": 90}},
])
def test_an_unusable_pair_falls_back_to_the_defaults(cfg, raw):
    """None of these may reach the comparison that decides whether to warn. A
    threshold of "90" compares False against every percentage, which disables
    the alert in silence — the failure mode with no symptom until the quota is
    spent."""
    got = cfg.usage_thresholds({"thresholds": raw})
    assert got == (cfg.USAGE_WARN_AT, cfg.USAGE_ALERT_AT), got


def test_a_config_that_is_not_a_dict_at_all(cfg):
    """Valid JSON, wrong shape: a hand-edited file, or a writer from another
    version."""
    cfg.CONFIG_FILE.write_text("[1, 2, 3]", encoding="utf-8")
    assert cfg.load_config() == {}
    assert cfg.usage_thresholds() == (cfg.USAGE_WARN_AT, cfg.USAGE_ALERT_AT)


def test_half_a_pair_still_uses_the_other_half(cfg):
    """A warning on its own is usable as long as it stays under the alert."""
    assert cfg.usage_thresholds({"thresholds": {"warn": 60}}) == (60, 90)
    assert cfg.usage_thresholds({"thresholds": {"alert": 95}}) == (75, 95)


def test_an_inverted_pair_is_refused_as_a_pair(cfg):
    """Falling back on one half alone is how you end up with warn above
    alert, which paints the amber zone on top of the red one."""
    warn, alert = cfg.usage_thresholds({"thresholds": {"warn": 95, "alert": 80}})
    assert warn < alert
    assert (warn, alert) == (cfg.USAGE_WARN_AT, cfg.USAGE_ALERT_AT)


def test_the_setter_refuses_an_inverted_pair_too(cfg):
    """Not only the reader. A pair stored inverted would be refused on every
    read afterwards, so the setting would look accepted and do nothing."""
    assert cfg.set_usage_thresholds(95, 80) == (cfg.USAGE_WARN_AT,
                                                cfg.USAGE_ALERT_AT)
    assert _written(cfg)["thresholds"] == {"warn": cfg.USAGE_WARN_AT,
                                           "alert": cfg.USAGE_ALERT_AT}


# ── the command line the widget builds ─────────────────────────────────────

def _pushThresholds_body():
    text = QML.read_text()
    at = text.find("function pushThresholds(")
    assert at != -1, "main.qml no longer has pushThresholds()"
    start = text.index("{", at)
    depth, i = 1, start + 1
    while i < len(text) and depth:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return text[start:i]


def test_the_widget_spells_the_flag_the_collector_parses():
    """One end is a string built in QML, the other is a startswith() in
    Python. A mismatch is silent in both directions: the collector ignores the
    argument and exits 0, and the widget never learns that the option it
    offers does nothing."""
    body = _pushThresholds_body()
    assert "--set-thresholds=" in body, body
    assert '--set-thresholds=' in COLLECTOR.read_text()


def test_the_pushed_value_cannot_carry_anything_but_digits():
    """The string is a shell command line, and the numbers in it come out of a
    text file KConfig wrote. They are rounded and range-checked in QML before
    they are interpolated, rather than after."""
    body = _pushThresholds_body()
    assert "Math.round" in body, body
    assert "cleanThreshold" in body, body
    assert re.search(r"if \(w === null \|\| a === null \|\| !\(w < a\)\) return;",
                     body), body


def test_the_collector_stores_what_that_command_line_asks_for(tmp_path):
    """End to end through the real script, in a home of its own."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    env = {**os.environ, "HOME": str(home)}
    run = subprocess.run([sys.executable, str(COLLECTOR),
                          "--set-thresholds=60,85"],
                         capture_output=True, text=True, env=env, timeout=60)
    assert run.returncode == 0, run.stderr
    stored = json.loads((home / ".claude" / "widget-config.json").read_text())
    assert stored["thresholds"] == {"warn": 60, "alert": 85}, stored


def test_a_malformed_command_line_stores_the_defaults_rather_than_failing(tmp_path):
    """It runs from a panel, where there is nowhere to show an error. Refusing
    would leave the file holding whatever it held; the defaults are at least a
    pair the widget and the notifications both agree on."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    env = {**os.environ, "HOME": str(home)}
    run = subprocess.run([sys.executable, str(COLLECTOR),
                          "--set-thresholds=abc,999"],
                         capture_output=True, text=True, env=env, timeout=60)
    assert run.returncode == 0, run.stderr
    stored = json.loads((home / ".claude" / "widget-config.json").read_text())
    assert stored["thresholds"] == {"warn": 75, "alert": 90}, stored


def test_setting_the_thresholds_does_not_run_the_collection(tmp_path):
    """--set-thresholds returns before build_widget_data(). It is called from
    a config-changed handler, and a network round trip there would freeze the
    panel; it would also write widget-data.json from a code path nobody
    expects to."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    env = {**os.environ, "HOME": str(home)}
    subprocess.run([sys.executable, str(COLLECTOR), "--set-thresholds=60,85"],
                   capture_output=True, text=True, env=env, timeout=60)
    assert not (home / ".claude" / "widget-data.json").exists()


# ── the dialog ─────────────────────────────────────────────────────────────

def test_the_config_page_exposes_both_thresholds():
    """KCM binds a control to cfg_<name>. Without the property the entry
    exists in the config file and nowhere in the dialog."""
    src = CONFIG_QML.read_text()
    for name in ("usageWarnAt", "usageAlertAt"):
        assert re.search(r"property int cfg_%s\b" % name, src), name


def test_the_dialog_cannot_be_used_to_put_the_warning_above_the_alert():
    """Checked as a bound range rather than as validation after the fact:
    there is nowhere on a KCM page to tell somebody their pair was rejected,
    so the pair has to be untypeable instead."""
    src = CONFIG_QML.read_text()
    assert re.search(r"to:\s*Math\.max\(\s*5,\s*page\.cfg_usageAlertAt - 1\)", src), (
        "the warning box's ceiling does not follow the alert")
    assert re.search(r"from:\s*Math\.min\(\s*99,\s*page\.cfg_usageWarnAt \+ 1\)", src), (
        "the alert box's floor does not follow the warning")


def test_the_page_says_the_two_numbers_also_decide_the_notification():
    """Somebody moving a colour boundary is also moving when they get
    interrupted, and there is no way to tell from the control itself."""
    src = CONFIG_QML.read_text()
    at = src.find("Where a quota turns amber")
    assert at != -1, "the thresholds have no explanatory text on the page"
    blurb = src[at:at + 500]
    assert "notification" in blurb, blurb
