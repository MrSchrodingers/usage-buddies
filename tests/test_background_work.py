"""A turn ending is not the work ending.

An async agent writes to its own file under subagents/, not to the main
transcript. So when the parent turn ends, the main transcript stops growing
while the agent keeps working — and idle time measured from that file alone
counts up through work that is still happening. The session gets announced as
finished and someone goes to look at a session that is still moving.
"""
import importlib.util
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROBE = REPO / "scripts" / "sessions-probe.py"


def _probe():
    spec = importlib.util.spec_from_file_location("sessions_probe", PROBE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sessions_probe"] = mod
    spec.loader.exec_module(mod)
    return mod


def _session(tmp_path, *, turn_age, agent_age=None, bash_age=None, bash_launched=False):
    """A transcript whose turn ended `turn_age` seconds ago, optionally with
    an agent or a background shell that wrote more recently."""
    project = tmp_path / "projects" / "-repo"
    project.mkdir(parents=True)
    transcript = project / "abc123.jsonl"

    lines = [{"type": "assistant", "message": {"role": "assistant",
              "stop_reason": "end_turn", "content": [{"type": "text", "text": "done"}]}}]
    if bash_launched:
        lines.insert(0, {"type": "user", "timestamp": "2026-09-01T12:00:00.000Z",
                         "toolUseResult": {"backgroundTaskId": "bg1"}})
    transcript.write_text("\n".join(json.dumps(x) for x in lines) + "\n")

    now = time.time()
    import os
    os.utime(transcript, (now - turn_age, now - turn_age))

    if agent_age is not None:
        subagents = project / "abc123" / "subagents"
        subagents.mkdir(parents=True)
        f = subagents / "agent-a1.jsonl"
        f.write_text("{}\n")
        os.utime(f, (now - agent_age, now - agent_age))

    if bash_age is not None:
        tasks = tmp_path / "tmp" / "-repo" / "abc123" / "tasks"
        tasks.mkdir(parents=True)
        f = tasks / "bg1.output"
        f.write_text("running\n")
        os.utime(f, (now - bash_age, now - bash_age))

    return transcript


def test_an_agent_still_writing_is_not_a_finished_session(tmp_path, monkeypatch):
    """The defect, stated as a case: the turn ended half an hour ago and the
    agent wrote two seconds ago."""
    mod = _probe()
    transcript = _session(tmp_path, turn_age=1800, agent_age=2)

    count, idle = mod.session_idle(transcript)
    assert count == 1, "the running agent was not seen"
    assert idle < mod.SETTLED_SECONDS, f"idle still {idle}s despite live work"

    records = mod._tail_records(transcript)
    state, _ = mod.classify(records, idle, background=count)
    assert state == "background", f"reported {state}"


def test_without_the_background_signal_it_reports_finished(tmp_path):
    """The old behaviour, kept as the contrast. If this ever stops saying
    'idle', the case above has stopped being a regression test."""
    mod = _probe()
    transcript = _session(tmp_path, turn_age=1800, agent_age=2)
    records = mod._tail_records(transcript)
    state, _ = mod.classify(records, 1800, background=0)
    assert state == "idle"


def test_a_quiet_session_with_no_background_is_still_idle(tmp_path):
    """The warning the operator asked for: everything stopped, the session and
    whatever it launched. That has to survive the fix."""
    mod = _probe()
    transcript = _session(tmp_path, turn_age=1800)
    count, idle = mod.session_idle(transcript)
    assert count == 0
    assert idle >= mod.IDLE_SECONDS, f"idle only {idle}s"
    state, _ = mod.classify(mod._tail_records(transcript), idle, background=count)
    assert state == "idle", f"reported {state}"


def test_a_finished_agent_does_not_pin_the_session_to_busy(tmp_path):
    """An agent file from an hour ago is finished work. Counting it would make
    every session that ever ran one look permanently busy."""
    mod = _probe()
    # The agent file must be *newer* than the transcript, or the "has anything
    # happened since the turn ended" check drops it first and the freshness
    # window is never the thing being tested.
    transcript = _session(tmp_path, turn_age=7200, agent_age=3600)
    assert 3600 > mod.BACKGROUND_WINDOW, "the case no longer exercises the window"
    assert mod.background_activity(transcript)[0] == 0


def test_foreground_tool_output_is_not_background_work(tmp_path, monkeypatch):
    """tasks/ also collects output from ordinary foreground calls. Counting the
    directory whole reported this machine's own session as busy purely because
    it was running the command doing the measuring."""
    mod = _probe()
    transcript = _session(tmp_path, turn_age=1800, bash_age=2, bash_launched=False)
    monkeypatch.setattr(mod, "TASK_DIR", tmp_path / "tmp")
    assert mod.background_activity(transcript)[0] == 0, \
        "counted a task the session never launched in the background"


def test_a_background_shell_still_writing_counts(tmp_path, monkeypatch):
    mod = _probe()
    transcript = _session(tmp_path, turn_age=1800, bash_age=2, bash_launched=True)
    monkeypatch.setattr(mod, "TASK_DIR", tmp_path / "tmp")
    assert mod.background_activity(transcript)[0] == 1


def test_a_quoted_launch_in_tool_output_is_not_a_launch(tmp_path):
    """A transcript contains tool output, and tool output can quote the very
    string that announces a launch. Scanning the text for it invented a
    running agent out of this probe's own diagnostic printout."""
    mod = _probe()
    project = tmp_path / "projects" / "-repo"
    project.mkdir(parents=True)
    transcript = project / "abc123.jsonl"
    transcript.write_text(json.dumps({
        "type": "user",
        "message": {"role": "user", "content": [{"type": "text", "text":
            'saida do comando: {"backgroundTaskId":"ghost"} '
            'Async agent launched successfully ... agentId: deadbeef'}]},
    }) + "\n")
    assert mod._background_bash_ids(transcript) == set(), \
        "a quoted id was read as a launch"


def test_a_session_inside_a_long_tool_call_is_not_abandoned(tmp_path):
    """Nothing is written to the transcript while a command runs.

    A deploy watched from a shell goes quiet for as long as the deploy takes,
    and the session was then announced as finished. The process is known alive
    — this probe starts from pgrep — so a turn that stopped to call a tool is
    inside that call, not done with it.
    """
    import os
    mod = _probe()
    project = tmp_path / "projects" / "-repo"
    project.mkdir(parents=True)
    transcript = project / "abc123.jsonl"
    transcript.write_text(json.dumps({
        "type": "assistant",
        "message": {"role": "assistant", "stop_reason": "tool_use",
                    "content": [{"type": "tool_use", "name": "Bash", "input": {}}]},
    }) + "\n")
    old = time.time() - 3600
    os.utime(transcript, (old, old))

    state, detail = mod.classify(mod._tail_records(transcript), 3600,
                                 background=0, executing=True)
    assert state == "working", f"an hour into a deploy it reported {state}"
    assert detail == "Bash"

    # And the case the old behaviour existed to catch: stopped mid-call with
    # nothing running is stuck, and saying "working" would bury it.
    stuck, _ = mod.classify(mod._tail_records(transcript), 3600,
                            background=0, executing=False)
    assert stuck == "idle", f"a stalled session reported {stuck}"


def test_a_finished_turn_that_is_quiet_is_still_idle(tmp_path):
    """The contrast. Without it, 'never idle' would pass the test above."""
    mod = _probe()
    transcript = _session(tmp_path, turn_age=3600)
    state, _ = mod.classify(mod._tail_records(transcript), 3600, background=0)
    assert state == "idle"


def test_a_shell_child_is_what_counts_as_running(tmp_path):
    """Against real /proc, not a fixture.

    Every session carries the same persistent children — the MCP servers it
    launched, which are `npm exec ...` and always there. Counting any child at
    all would report every session as executing, forever. Only a shell appears
    while a command runs.
    """
    import os
    import subprocess
    mod = _probe()

    assert not mod.running_command(os.getpid()), \
        "reported a command running before one was started"

    child = subprocess.Popen(["sh", "-c", "sleep 4"])
    try:
        deadline = time.time() + 3
        while time.time() < deadline and not mod.running_command(os.getpid()):
            time.sleep(0.05)
        assert mod.running_command(os.getpid()), "missed a running shell child"
    finally:
        child.terminate()
        child.wait(timeout=5)

    deadline = time.time() + 3
    while time.time() < deadline and mod.running_command(os.getpid()):
        time.sleep(0.05)
    assert not mod.running_command(os.getpid()), \
        "still reported running after the shell exited"


def test_a_non_shell_child_does_not_count(tmp_path):
    """The MCP servers are long-lived children of every session. If they
    counted, no session would ever be reported quiet again."""
    import os
    import subprocess
    mod = _probe()
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(4)"])
    try:
        time.sleep(0.4)
        assert not mod.running_command(os.getpid()), \
            "a non-shell child was counted as a running command"
    finally:
        child.terminate()
        child.wait(timeout=5)
