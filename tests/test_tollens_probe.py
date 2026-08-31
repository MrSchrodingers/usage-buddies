"""The Tollens probe reads a governed config; what it must NOT read matters most.

Two files in that tree carry data that must never reach a widget JSON:
subagent-probe.jsonl holds `last_assistant_message` and `cwd` (its own header
says the payload must not leave the machine), and the activation log holds
project file paths that name clients.
"""
import importlib.util
import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PROBE = REPO / "scripts" / "tollens-probe.py"


@pytest.fixture
def probe(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("tollens_probe", PROBE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["tollens_probe"] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path / "out")
    monkeypatch.setattr(mod, "OUT_FILE", tmp_path / "out" / "tollens.json")
    return mod


def _settings(tmp_path, **over):
    d = {
        "_managed_by": "tollens",
        "allowManagedHooksOnly": True,
        "hooks": {
            "SessionStart": [{"hooks": [{"command": "a"}]}],
            "PreToolUse": [{"hooks": [{"command": "b"}, {"command": "c"}]}],
        },
    }
    d.update(over)
    p = tmp_path / "managed-settings.json"
    p.write_text(json.dumps(d))
    return p


# ── absence and identity ──

def test_absent_tollens_reports_only_absence(probe, monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "MANAGED_SETTINGS", tmp_path / "nope.json")
    assert probe.detect() == {"present": False}


def test_a_managed_settings_from_something_else_is_not_tollens(probe, monkeypatch, tmp_path):
    """The file existing is not the question; who owns it is."""
    monkeypatch.setattr(probe, "MANAGED_SETTINGS",
                        _settings(tmp_path, _managed_by="something-else"))
    assert probe.detect()["present"] is False


def test_present_and_enforced_are_separate_questions(probe, monkeypatch, tmp_path):
    """A policy can be deployed and not enforced. Collapsing the two into one
    light is exactly the confusion Tollens exists to name."""
    monkeypatch.setattr(probe, "MANAGED_SETTINGS",
                        _settings(tmp_path, allowManagedHooksOnly=False))
    got = probe.detect()
    assert got["present"] is True
    assert got["enforced"] is False


def test_hooks_are_counted_per_event(probe, monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "MANAGED_SETTINGS", _settings(tmp_path))
    hooks = probe.detect()["hooks"]
    assert hooks["total"] == 3
    assert hooks["byEvent"] == {"SessionStart": 1, "PreToolUse": 2}


# ── manifest ──

def test_inventory_counts_by_type(probe, monkeypatch, tmp_path):
    src = tmp_path / "src" / "install"
    src.mkdir(parents=True)
    (src / "manifest.lock").write_text(
        "hook\ta\tb\tsha1\n"
        "hook\tc\td\tsha2\n"
        "agent\te\tf\tsha3\n"
        "# comment line\n"
        "\n")
    monkeypatch.setattr(probe, "TOLLENS_SRC", tmp_path / "src")
    assert probe.inventory() == {"byType": {"hook": 2, "agent": 1}, "total": 3}


def test_missing_manifest_is_empty_not_a_crash(probe, monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "TOLLENS_SRC", tmp_path / "absent")
    assert probe.inventory() == {}


# ── heartbeat ──

def test_heartbeat_reads_the_last_line(probe, monkeypatch, tmp_path):
    hb = tmp_path / "hb.jsonl"
    hb.write_text(
        json.dumps({"ts": "old", "result": "ok"}) + "\n" +
        json.dumps({"ts": "2026-08-31T19:23:20Z", "result": "drift",
                    "summary": "PROJECAO USUARIO: 48/49 ok",
                    "managed_summary": "managed: 31 componentes"}) + "\n")
    monkeypatch.setattr(probe, "HEARTBEAT", hb)
    got = probe.heartbeat()
    assert got["at"] == "2026-08-31T19:23:20Z"
    assert got["result"] == "drift"


def test_heartbeat_tolerates_the_older_schema(probe, monkeypatch, tmp_path):
    """The first records predate several fields; a strict parser breaks on them."""
    hb = tmp_path / "hb.jsonl"
    hb.write_text(json.dumps({"ts": "2026-08-04T00:00:00Z", "policy": "user"}) + "\n")
    monkeypatch.setattr(probe, "HEARTBEAT", hb)
    got = probe.heartbeat()
    assert got["at"] == "2026-08-04T00:00:00Z"
    assert got["user"] == "" and got["managed"] == ""


def test_missing_heartbeat_is_empty(probe, monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "HEARTBEAT", tmp_path / "absent.jsonl")
    assert probe.heartbeat() == {}


# ── privacy ──

# Never opened at all: the whole file is unsafe.
NEVER_READ = ["subagent-probe", "last_assistant_message", "transcript_path"]


@pytest.mark.parametrize("needle", NEVER_READ)
def test_probe_never_touches_the_transcript_probe(needle):
    """subagent-probe.jsonl carries `last_assistant_message` and `cwd`, and its
    own header states the payload must not leave the machine. There is no safe
    subset — the file is simply not opened."""
    body = PROBE.read_text()
    code = body.split('"""', 2)[-1]
    code = "\n".join(l for l in code.split("\n") if not l.strip().startswith("#"))
    assert needle not in code, f"probe references {needle!r} outside its rationale"


def test_activation_log_is_read_but_paths_are_not():
    """The activation log is read — it is the only source of usage counts — but
    its `f` field holds project paths that name clients. The rule is a field
    allowlist, not file avoidance, so it is stated as one."""
    body = PROBE.read_text()
    assert "ACTIVATION_SAFE" in body, "no declared allowlist of safe fields"
    assert '"f"' not in body.split("ACTIVATION_SAFE")[1].split(")")[0], (
        "the paths field is inside the safe list"
    )
    # and the code must never index that field
    code = body.split('"""', 2)[-1]
    assert 'rec.get("f")' not in code and "['f']" not in code, (
        "probe reads the project-paths field"
    )


def test_output_lands_outside_the_audited_tree():
    """~/.claude is what Tollens audits. A widget file inside it is a candidate
    orphan the moment their scan widens."""
    body = PROBE.read_text()
    assert 'OUT_DIR' in body and 'XDG_CACHE_HOME' in body
    assert '.claude" / "usage-buddies' not in body


# ── output ──

def test_written_file_is_private(probe, monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "MANAGED_SETTINGS", tmp_path / "nope.json")
    monkeypatch.setattr(sys, "argv", ["tollens-probe.py"])
    probe.main()
    mode = stat.S_IMODE(probe.OUT_FILE.stat().st_mode)
    assert mode == 0o600, oct(mode)
    assert json.loads(probe.OUT_FILE.read_text()) == {"present": False}


def test_conformance_is_throttled(probe, monkeypatch, tmp_path):
    """0.75s against a 30s timer is 2.5% of a core spent re-deriving something
    that changes rarely."""
    monkeypatch.setattr(probe, "MANAGED_SETTINGS", _settings(tmp_path))
    monkeypatch.setattr(probe, "TOLLENS_SRC", tmp_path / "absent")
    calls = []
    monkeypatch.setattr(probe, "conformance",
                        lambda: calls.append(1) or {"available": True,
                                                    "checkedAt": probe.time.time()})
    monkeypatch.setattr(sys, "argv", ["tollens-probe.py"])
    probe.main()
    probe.main()
    probe.main()
    assert len(calls) == 1, f"conformance ran {len(calls)} times in a row"


def test_probe_runs_end_to_end(tmp_path):
    """It must not crash on this machine, whatever Tollens' state is."""
    env = {**dict(__import__("os").environ), "XDG_CACHE_HOME": str(tmp_path)}
    r = subprocess.run([sys.executable, str(PROBE)], capture_output=True,
                       text=True, timeout=60, env=env)
    assert r.returncode == 0, r.stderr
    out = json.loads((tmp_path / "usage-buddies" / "tollens.json").read_text())
    assert "present" in out


# ── usage metrics ──

def _activation(tmp_path, records):
    p = tmp_path / "activation.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return p


def test_usage_ranks_agents_with_shares(probe, monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "ACTIVATION_LOG", _activation(tmp_path, [
        {"ev": "SubagentStart", "a": "investigador", "s": "s1"},
        {"ev": "SubagentStart", "a": "investigador", "s": "s1"},
        {"ev": "SubagentStart", "a": "investigador", "s": "s2"},
        {"ev": "SubagentStart", "a": "refutador", "s": "s2"},
    ]))
    u = probe.usage()
    assert u["agents"][0] == {"name": "investigador", "count": 3, "share": 0.75}
    assert u["sessions"] == 2, "distinct sessions miscounted"


def test_skills_and_tools_are_separated_by_event(probe, monkeypatch, tmp_path):
    """`k` carries both, distinguished only by the event that logged it."""
    monkeypatch.setattr(probe, "ACTIVATION_LOG", _activation(tmp_path, [
        {"ev": "Skill", "k": "claude-api", "s": "s1"},
        {"ev": "PreToolUse", "k": "Bash", "s": "s1"},
        {"ev": "PreToolUse", "k": "Bash", "s": "s1"},
    ]))
    u = probe.usage()
    assert [r["name"] for r in u["skills"]] == ["claude-api"]
    assert [r["name"] for r in u["tools"]] == ["Bash"]


def test_memory_scope_is_captured(probe, monkeypatch, tmp_path):
    """The closest thing Tollens records to evidence of ACTIVATED."""
    monkeypatch.setattr(probe, "ACTIVATION_LOG", _activation(tmp_path, [
        {"ev": "InstructionsLoaded", "t": "Managed", "s": "s1"},
        {"ev": "InstructionsLoaded", "t": "Project", "s": "s1"},
        {"ev": "InstructionsLoaded", "t": "Project", "s": "s2"},
    ]))
    assert probe.usage()["memoryScope"] == {"Managed": 1, "Project": 2}


def test_project_paths_never_reach_the_output(probe, monkeypatch, tmp_path):
    """`f` holds project file paths that name clients. They must not appear in
    the emitted structure under any key."""
    monkeypatch.setattr(probe, "ACTIVATION_LOG", _activation(tmp_path, [
        {"ev": "InstructionsLoaded", "t": "Project", "s": "s1",
         "f": "/var/www/ACME-CLIENT/backend/CLAUDE.md"},
    ]))
    blob = json.dumps(probe.usage())
    assert "ACME-CLIENT" not in blob and "/var/www" not in blob, blob


def test_session_ids_are_counted_not_emitted(probe, monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "ACTIVATION_LOG", _activation(tmp_path, [
        {"ev": "SubagentStart", "a": "x", "s": "68e9eb26-f760-418d-a88d-613921631721"},
    ]))
    u = probe.usage()
    assert u["sessions"] == 1
    assert "68e9eb26" not in json.dumps(u)


def test_usage_reports_no_time_window(probe, monkeypatch, tmp_path):
    """The log has no timestamps. Deriving a start from ctime would be wrong —
    on Linux that is the inode change time and moves on every append."""
    monkeypatch.setattr(probe, "ACTIVATION_LOG", _activation(tmp_path, [
        {"ev": "Skill", "k": "a", "s": "s1"}]))
    assert "since" not in probe.usage()


def test_missing_activation_log_is_empty(probe, monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "ACTIVATION_LOG", tmp_path / "absent.jsonl")
    assert probe.usage() == {}


def test_malformed_lines_are_skipped(probe, monkeypatch, tmp_path):
    p = tmp_path / "a.jsonl"
    p.write_text('{"ev":"Skill","k":"ok","s":"s1"}\nnot json\n\n{"ev":"Skill","k":"ok","s":"s1"}\n')
    monkeypatch.setattr(probe, "ACTIVATION_LOG", p)
    assert probe.usage()["records"] == 2


# ── verify gate ──

def test_gate_tallies_verdicts(probe, monkeypatch, tmp_path):
    ev = tmp_path / "evidence"
    ev.mkdir()
    (ev / "a.jsonl").write_text(
        json.dumps({"verdict": "pass"}) + "\n" + json.dumps({"verdict": "fail"}) + "\n")
    (ev / "b.jsonl").write_text(json.dumps({"verdict": "pass"}) + "\n")
    monkeypatch.setattr(probe, "EVIDENCE_DIR", ev)
    g = probe.gate()
    assert g["byVerdict"] == {"pass": 2, "fail": 1}
    assert g["passRate"] == round(2 / 3, 4)


def test_gate_skips_the_heartbeat_file(probe, monkeypatch, tmp_path):
    """The heartbeat lives in the same directory and is not a gate ledger."""
    ev = tmp_path / "evidence"
    ev.mkdir()
    (ev / probe.HEARTBEAT.name).write_text(json.dumps({"verdict": "pass"}) + "\n")
    monkeypatch.setattr(probe, "EVIDENCE_DIR", ev)
    assert probe.gate() == {}


def test_gate_is_empty_without_evidence(probe, monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "EVIDENCE_DIR", tmp_path / "absent")
    assert probe.gate() == {}


# ── divergence detail and trend ──

VERIFY_OUTPUT = """
  DIVERGE   agents/investigador.md                     (instalado != manifesto)
  DIVERGE   agents/refutador.md                        (instalado != manifesto)
  AUSENTE   hooks/self-mod-audit.sh                    (declarado, nao instalado)
  ORFAO     hooks/estranho.sh                          (roda, nao esta no manifesto)
  REPO-DRIFT skills/forge                              (working tree != manifesto)

PROJECAO USUARIO: 45/49 ok | 3 divergentes | 1 ausentes | 1 orfaos
"""


def test_details_name_the_offending_components(probe):
    """"10 divergent" is a count; the ten names are a to-do list."""
    rows = probe._details(VERIFY_OUTPUT)
    assert [r["name"] for r in rows][:3] == [
        "agents/investigador.md", "agents/refutador.md", "hooks/self-mod-audit.sh"]


def test_details_carry_the_kind(probe):
    kinds = {r["name"]: r["kind"] for r in probe._details(VERIFY_OUTPUT)}
    assert kinds["agents/refutador.md"] == "divergent"
    assert kinds["hooks/self-mod-audit.sh"] == "missing"
    assert kinds["hooks/estranho.sh"] == "orphan"
    assert kinds["skills/forge"] == "repoDrift"


def test_details_drop_the_trailing_reason(probe):
    """Every row of a kind carries the same parenthetical; it is noise."""
    assert all("(" not in r["name"] for r in probe._details(VERIFY_OUTPUT))


def test_details_are_capped(probe):
    many = "\n".join(f"  DIVERGE   c{i}   (x)" for i in range(50))
    assert len(probe._details(many)) <= 12


def test_a_clean_run_lists_nothing(probe):
    assert probe._details("PROJECAO USUARIO: 49/49 ok | 0 divergentes") == []


def test_trend_records_one_sample_per_hour(probe, monkeypatch, tmp_path):
    """The probe may run every five minutes; a fortnight of that is 4000 points
    to render a sparkline nobody reads at that resolution."""
    monkeypatch.setattr(probe, "TREND_FILE", tmp_path / "trend.jsonl")
    monkeypatch.setattr(probe, "OUT_DIR", tmp_path)
    for _ in range(5):
        probe.record_trend({"available": True, "state": "conformant",
                            "userCounts": {"ok": 49, "total": 49}})
    lines = [l for l in (tmp_path / "trend.jsonl").read_text().split("\n") if l.strip()]
    assert len(lines) == 1, f"{len(lines)} samples written for one hour"


def test_no_history_at_all_yields_no_series(probe, monkeypatch, tmp_path):
    """Before the first sample there is nothing to trend, and seven hollow bars
    would be noise. The card hides on an empty list."""
    monkeypatch.setattr(probe, "TREND_FILE", tmp_path / "absent.jsonl")
    assert probe.read_trend(days=7) == []


def test_gaps_inside_a_series_are_slots_not_zeros(probe, monkeypatch, tmp_path):
    """Once a series exists, a day with no sample is a different state from a
    bad day and must not render as one."""
    import time as _t
    day = _t.strftime("%Y-%m-%d", _t.gmtime())
    f = tmp_path / "trend.jsonl"
    f.write_text(json.dumps({"h": day + "T01", "ok": True, "n": 49, "t": 49}) + "\n")
    monkeypatch.setattr(probe, "TREND_FILE", f)
    rows = probe.read_trend(days=7)
    assert len(rows) == 7
    assert rows[-1]["share"] == 1.0, "today's sample missing"
    assert all(r["ok"] is None and r["share"] is None for r in rows[:-1]), (
        "days without a sample rendered as data"
    )


def test_trend_keeps_the_worst_reading_of_a_day(probe, monkeypatch, tmp_path):
    """A day that was ever broken was a broken day."""
    import time as _t
    day = _t.strftime("%Y-%m-%d", _t.gmtime())
    f = tmp_path / "trend.jsonl"
    f.write_text(
        json.dumps({"h": day + "T01", "ok": True, "n": 49, "t": 49}) + "\n" +
        json.dumps({"h": day + "T05", "ok": False, "n": 39, "t": 49}) + "\n" +
        json.dumps({"h": day + "T09", "ok": True, "n": 49, "t": 49}) + "\n")
    monkeypatch.setattr(probe, "TREND_FILE", f)
    today = probe.read_trend(days=1)[0]
    assert today["ok"] is False and today["share"] == pytest.approx(39 / 49, abs=0.001)


def test_unavailable_conformance_records_nothing(probe, monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "TREND_FILE", tmp_path / "trend.jsonl")
    probe.record_trend({"available": False})
    assert not (tmp_path / "trend.jsonl").exists()
