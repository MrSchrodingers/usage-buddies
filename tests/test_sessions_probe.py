"""Which Claude sessions need the human.

The classification is the whole feature: a session wrongly reported as working
never gets looked at, and one wrongly reported as done cries wolf until the
notification is muted.
"""
import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PROBE = REPO / "scripts" / "sessions-probe.py"


@pytest.fixture
def probe(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("sessions_probe", PROBE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sessions_probe"] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path / "out")
    monkeypatch.setattr(mod, "OUT_FILE", tmp_path / "out" / "sessions.json")
    monkeypatch.setattr(mod, "STATE_FILE", tmp_path / "out" / "state.json")
    return mod


def _assistant(stop=None, tools=()):
    content = [{"type": "tool_use", "name": t} for t in tools]
    return {"type": "assistant",
            "message": {"role": "assistant", "stop_reason": stop, "content": content}}


# The bookkeeping a finished turn is followed by. Reading only the last record
# finds one of these, which carries no stop_reason.
TRAILING = [
    {"type": "system", "subtype": "away_summary"},
    {"type": "system", "subtype": "turn_duration"},
    {"type": "system", "subtype": "stop_hook_summary"},
    {"type": "attachment"},
]


def test_end_turn_behind_bookkeeping_is_still_a_finished_turn(probe):
    """The regression this was written for: every settled session looked busy
    because the classifier read only the final line."""
    records = TRAILING + [_assistant(stop="end_turn")]
    state, detail = probe.classify(records, idle_seconds=300)
    assert state == "waiting", (state, detail)


def test_a_turn_that_just_ended_is_not_yet_waiting(probe):
    """Two seconds after end_turn the session is probably about to continue;
    announcing it would fire on every tool boundary."""
    records = TRAILING + [_assistant(stop="end_turn")]
    assert probe.classify(records, idle_seconds=3)[0] == "working"


def test_asking_outranks_everything(probe):
    """A session blocked on a question is blocked no matter how long ago it
    spoke, so it must not be filed as idle."""
    records = [_assistant(stop="tool_use", tools=["AskUserQuestion"])]
    assert probe.classify(records, idle_seconds=99999)[0] == "asking"


def test_a_long_finished_turn_reads_as_idle_not_waiting(probe):
    """After ten minutes "done, go look" has stopped being news."""
    records = TRAILING + [_assistant(stop="end_turn")]
    assert probe.classify(records, idle_seconds=3600)[0] == "idle"


def test_mid_tool_call_is_working(probe):
    assert probe.classify([_assistant(stop="tool_use", tools=["Bash"])], 5)[0] == "working"


def test_silence_while_mid_tool_call_is_idle(probe):
    assert probe.classify([_assistant(stop="tool_use", tools=["Bash"])], 3600)[0] == "idle"


def test_no_records_is_unknown_not_a_guess(probe):
    assert probe.classify([], 10)[0] == "unknown"


def test_detail_names_the_tool_being_run(probe):
    assert probe.classify([_assistant(stop="tool_use", tools=["Bash"])], 5)[1] == "Bash"


# ── tail reading ──

def test_tail_reads_only_the_end_of_a_large_transcript(probe, tmp_path):
    """Transcripts reach hundreds of megabytes; reading them whole every cycle
    would cost more than everything else combined."""
    f = tmp_path / "big.jsonl"
    filler = json.dumps({"type": "filler", "pad": "x" * 500}) + "\n"
    with f.open("w") as fh:
        fh.write(filler * 4000)
        fh.write(json.dumps(_assistant(stop="end_turn")) + "\n")
    assert f.stat().st_size > probe.TAIL_BYTES
    records = probe._tail_records(f)
    assert records, "nothing parsed from the tail"
    assert (records[0].get("message") or {}).get("stop_reason") == "end_turn"


def test_tail_survives_a_truncated_first_line(probe, tmp_path):
    """Seeking into the middle of a line leaves a fragment that is not JSON."""
    f = tmp_path / "t.jsonl"
    f.write_text("x" * (probe.TAIL_BYTES + 100) + "\n" +
                 json.dumps(_assistant(stop="end_turn")) + "\n")
    records = probe._tail_records(f)
    assert any((r.get("message") or {}).get("stop_reason") == "end_turn" for r in records)


def test_missing_file_yields_no_records(probe, tmp_path):
    assert probe._tail_records(tmp_path / "absent.jsonl") == []


# ── the working directory encodes the project folder ──

def test_slug_matches_the_projects_layout(probe):
    assert probe._slug("/var/www/DEBTHUB-2.1") == "-var-www-DEBTHUB-2-1"
    assert probe._slug("/home/ti") == "-home-ti"


# ── announcements ──

def _data(pid, state, name="repo"):
    s = {"pid": pid, "state": state, "name": name, "cwd": "/x", "idleSeconds": 60,
         "ageSeconds": 100, "branch": "", "detail": "", "hasTranscript": True}
    return {"sessions": [s], "counts": {state: 1}, "total": 1,
            "attention": s if state in ("asking", "waiting") else None}


def test_announcement_fires_once_per_transition(probe, monkeypatch):
    """A session waiting for an hour must not re-announce every thirty
    seconds."""
    fired = []
    monkeypatch.setattr(probe, "_notify", lambda s, lang="en": fired.append(s["state"]))
    for _ in range(4):
        probe.announce(_data(1, "waiting"))
    assert fired == ["waiting"], fired


def test_returning_to_work_then_finishing_is_a_new_event(probe, monkeypatch):
    fired = []
    monkeypatch.setattr(probe, "_notify", lambda s, lang="en": fired.append(s["state"]))
    probe.announce(_data(1, "waiting"))
    probe.announce(_data(1, "working"))
    probe.announce(_data(1, "waiting"))
    assert fired == ["waiting", "waiting"], fired


def test_working_and_idle_never_announce(probe, monkeypatch):
    """Only states that need a human interrupt one."""
    fired = []
    monkeypatch.setattr(probe, "_notify", lambda s, lang="en": fired.append(s["state"]))
    probe.announce(_data(1, "working"))
    probe.announce(_data(2, "idle"))
    assert fired == []


def test_probe_is_silent_without_the_flag(tmp_path):
    """Running the probe must be harmless; nothing pops up unless asked."""
    import subprocess
    env = {**__import__("os").environ, "XDG_CACHE_HOME": str(tmp_path)}
    r = subprocess.run([sys.executable, str(PROBE)], capture_output=True,
                       text=True, timeout=60, env=env)
    assert r.returncode == 0, r.stderr
    assert not (tmp_path / "usage-buddies" / "state.json").exists()


def test_probe_runs_end_to_end(tmp_path):
    import subprocess
    env = {**__import__("os").environ, "XDG_CACHE_HOME": str(tmp_path)}
    r = subprocess.run([sys.executable, str(PROBE)], capture_output=True,
                       text=True, timeout=60, env=env)
    assert r.returncode == 0, r.stderr
    out = json.loads((tmp_path / "usage-buddies" / "sessions.json").read_text())
    assert "sessions" in out and "attention" in out
