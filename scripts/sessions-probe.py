#!/usr/bin/env python3
"""Which Claude sessions are alive, where, and whether they need you.

Several Claude Code sessions run at once across different repositories, and
nothing on the desktop says which of them finished, which is stuck waiting on
an answer, and which has been idle for an hour. That is the useful half of the
widget's mascot: it can only be funny about something if it knows something.

State comes from two sources crossed together:

  - `pgrep -x claude` plus /proc/<pid>/cwd — which sessions are actually alive
    and in which working directory. A transcript on disk proves a session
    existed, not that it is running.
  - the newest transcript under ~/.claude/projects/<slugged-cwd>/ — its last
    record says what the session is doing, and its mtime says for how long.

Nothing here reads message text. Only record types, stop reasons, tool names
and timestamps are inspected; the working directory is reported because it is
what identifies the session to its owner.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
OUT_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "usage-buddies"
OUT_FILE = OUT_DIR / "sessions.json"
STATE_FILE = OUT_DIR / "sessions-state.json"
FOCUS_HELPER = Path(__file__).resolve().parent / "focus-session.sh"

# A turn that ended more than this long ago is waiting on the human, not still
# thinking. Below it, the session may simply be between tool calls.
SETTLED_SECONDS = 20
# No transcript write for this long, with the process still alive, is idle.
IDLE_SECONDS = 600
# Reading the tail is enough to classify; whole transcripts run to megabytes.
TAIL_BYTES = 64 * 1024
# An auxiliary file untouched for this long is finished work, not running work.
BACKGROUND_WINDOW = 180
TASK_DIR = Path(os.environ.get("TMPDIR", "/tmp")) / f"claude-{os.getuid()}"


def _slug(path: str) -> str:
    """~/.claude/projects encodes the working directory in the folder name."""
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def _live_sessions() -> list[dict]:
    try:
        pids = subprocess.run(["pgrep", "-x", "claude"], capture_output=True,
                              text=True, timeout=5).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return []

    out = []
    for pid in pids:
        try:
            cwd = os.readlink(f"/proc/{pid}/cwd")
            started = os.stat(f"/proc/{pid}").st_mtime
        except OSError:
            continue          # exited between listing and reading
        out.append({"pid": int(pid), "cwd": cwd, "ageSeconds": int(time.time() - started)})
    return out


def _tail_records(path: Path, limit=25):
    """The last few JSON records of a transcript, newest first.

    Not just the last one: a finished turn is followed by bookkeeping —
    `attachment`, then system records for stop_hook_summary, turn_duration and
    away_summary. Reading only the final line finds one of those, which carries
    no stop_reason, and every settled session looks busy.

    Read from the tail: transcripts reach hundreds of megabytes and only the
    end classifies them.
    """
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            if size > TAIL_BYTES:
                f.seek(-TAIL_BYTES, os.SEEK_END)
                f.readline()          # discard the partial line
            chunk = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []

    out = []
    for line in reversed(chunk.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(out) >= limit:
            break
    return out


def _newest_transcript(cwd: str):
    folder = PROJECTS / _slug(cwd)
    if not folder.is_dir():
        return None
    newest, newest_mtime = None, 0
    try:
        for f in folder.glob("*.jsonl"):
            if "subagents" in str(f):
                continue
            m = f.stat().st_mtime
            if m > newest_mtime:
                newest, newest_mtime = f, m
    except OSError:
        return None
    return newest


def _background_bash_ids(transcript: Path):
    """Ids of tasks this session launched with run_in_background.

    Read structurally, not by scanning the text: `backgroundTaskId` is a key
    under `toolUseResult`, and a transcript also contains tool *output* that
    can quote the same string. Scanning matched this probe's own diagnostic
    output echoed back into a transcript and invented a running task.
    """
    ids = set()
    try:
        fh = transcript.open(encoding="utf-8", errors="replace")
    except OSError:
        return ids
    with fh:
        for line in fh:
            if '"backgroundTaskId"' not in line:
                continue
            try:
                result = json.loads(line).get("toolUseResult")
            except json.JSONDecodeError:
                continue
            if isinstance(result, dict) and result.get("backgroundTaskId"):
                ids.add(result["backgroundTaskId"])
    return ids


def background_activity(transcript: Path, now=None):
    """Work still running after the turn that started it ended.

    A subagent writes to its own file, not to the main transcript, so when the
    parent turn ends the main transcript stops growing while the agent keeps
    working. Idle time measured from the main transcript alone counts up
    through work that is very much still happening — which is a session
    reported as finished while it is not.

    Two signals, each an mtime, because an mtime only moves when something
    writes:

      agents  a file under subagents/ touched more recently than the main
              transcript
      bash    tasks/<id>.output touched recently, for an id that a structural
              read confirmed was launched in the background

    The id filter on the bash side is not optional: that directory also
    collects output from ordinary foreground tool calls, and counting it whole
    reports every session as busy whenever it runs anything at all.

    Completion markers in the log are deliberately not used. The one shape
    that announces a finished task also appears in tool results that merely
    quote it, and there is no field position that tells the two apart.

    Returns (count, newest_mtime); the mtime is the newest activity of any
    kind, so idle time can be measured from work the main transcript cannot
    see.
    """
    now = now or time.time()
    try:
        base = transcript.stat().st_mtime
    except OSError:
        return 0, 0.0

    session = transcript.stem
    fresh = []
    for f in (transcript.parent / session / "subagents").glob("agent-*.jsonl"):
        fresh.append(f)

    bash_ids = _background_bash_ids(transcript)
    if bash_ids:
        tasks = TASK_DIR / transcript.parent.name / session / "tasks"
        fresh += [tasks / f"{i}.output" for i in bash_ids]

    count, newest = 0, base
    for f in fresh:
        try:
            m = f.stat().st_mtime
        except OSError:
            continue
        if m <= base or now - m > BACKGROUND_WINDOW:
            continue
        count += 1
        newest = max(newest, m)
    return count, newest


def session_idle(transcript: Path, now=None):
    """How long this session has been quiet, and how much work is still live.

    Idle counts from the newest activity of any kind, not from the main
    transcript. An agent that is working writes to its own file while the main
    one stops moving, so measuring only the main one times a running session
    out as abandoned — which is the session announced as finished while its
    agent is still going.
    """
    now = now or time.time()
    count, newest = background_activity(transcript, now=now)
    try:
        newest = max(newest, transcript.stat().st_mtime)
    except OSError:
        return count, None
    return count, int(now - newest)


def classify(records, idle_seconds, background=0):
    """What the session is doing, most-urgent first.

    Ordering matters: a session asking a question is blocked on a human no
    matter how long ago it spoke, while one that merely finished can wait.

    `background` outranks a finished turn but not a question. A turn ends when
    the assistant stops writing, which is not the same as the work stopping:
    an agent launched during that turn keeps going afterwards. Announcing that
    as finished sends someone to look at a session that is still moving, and
    it is the more expensive error — the opposite one only delays a nudge.
    """
    if not records:
        return "unknown", None

    # Newest assistant turn, skipping the bookkeeping records that follow it.
    assistant = next((r for r in records
                      if (r.get("message") or {}).get("role") == "assistant"), None)
    message = (assistant or {}).get("message") or {}
    tools = [c.get("name") for c in (message.get("content") or [])
             if isinstance(c, dict) and c.get("type") == "tool_use"]

    if "AskUserQuestion" in tools:
        return "asking", "AskUserQuestion"

    stop = message.get("stop_reason")
    if background:
        return "background", f"{background} em background"

    if stop in ("end_turn", "stop_sequence"):
        # Only once it has settled: a turn that ended two seconds ago is
        # probably about to continue.
        if idle_seconds >= IDLE_SECONDS:
            return "idle", stop
        return ("waiting" if idle_seconds >= SETTLED_SECONDS else "working"), stop

    if idle_seconds >= IDLE_SECONDS:
        return "idle", stop

    return "working", (tools[0] if tools else stop or "")


def _notify(session, lang="en"):
    """Announce a session that needs the human, with a button that goes there.

    --action implies --wait, so this runs detached and the chosen action is
    read from its stdout by a small waiter. Without that the probe would block
    for the notification's whole lifetime, every cycle.
    """
    name = session.get("name") or "?"
    state = session.get("state")
    if lang == "pt":
        title = f"{name}: pronto" if state == "waiting" else f"{name}: perguntou algo"
        body = ("Terminou o que tinha para fazer." if state == "waiting"
                else "Está esperando sua resposta.")
        go = "Ir para lá"
    else:
        title = f"{name}: done" if state == "waiting" else f"{name}: asking"
        body = ("Finished what it was doing." if state == "waiting"
                else "Waiting on your answer.")
        go = "Go there"

    helper = str(FOCUS_HELPER)
    if not os.path.exists(helper):
        helper = str(Path.home() / ".local" / "bin" / "focus-session.sh")

    # notify-send prints the chosen action name; feed that to the focus helper.
    shell = (
        f'a=$(notify-send --app-name="Usage Buddies" --icon=claude-logo '
        f'--urgency={"critical" if state == "asking" else "normal"} '
        f'--action="go={go}" {json.dumps(title)} {json.dumps(body)} 2>/dev/null); '
        f'[ "$a" = go ] && exec {json.dumps(helper)} {int(session["pid"])}'
    )
    try:
        subprocess.Popen(["sh", "-c", shell],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except (OSError, subprocess.SubprocessError) as error:
        print(f"warn: notify failed: {type(error).__name__}", file=sys.stderr)


def announce(data, lang="en"):
    """Fire once per transition into a state that needs attention.

    Keyed on pid and state: a session that has been waiting for an hour must
    not re-announce every thirty seconds, and one that goes back to work and
    finishes again is a new event, not a repeat.
    """
    try:
        previous = json.loads(STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        previous = {}

    current = {str(s["pid"]): s["state"] for s in data["sessions"]}
    for session in data["sessions"]:
        key = str(session["pid"])
        if session["state"] not in ("asking", "waiting"):
            continue
        if previous.get(key) == session["state"]:
            continue
        _notify(session, lang)

    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(current))
        os.chmod(tmp, 0o600)
        os.replace(tmp, STATE_FILE)
    except OSError:
        pass


def collect() -> dict:
    sessions = []
    for live in _live_sessions():
        transcript = _newest_transcript(live["cwd"])
        idle = None
        records = []
        record = None
        background = 0
        if transcript is not None:
            background, idle = session_idle(transcript)
            records = _tail_records(transcript)

        state, detail = classify(records, idle if idle is not None else 0,
                                 background=background)
        record = records[0] if records else None
        name = os.path.basename(live["cwd"].rstrip("/")) or live["cwd"]
        sessions.append({
            "pid": live["pid"],
            "cwd": live["cwd"],
            "name": name,
            "branch": next((r.get("gitBranch") for r in records if r.get("gitBranch")), ""),
            "state": state,
            "detail": detail or "",
            "idleSeconds": idle if idle is not None else -1,
            "background": background,
            "ageSeconds": live["ageSeconds"],
            "hasTranscript": transcript is not None,
        })

    # background sits below the states that want a human and above working:
    # it is information, not a summons.
    order = {"asking": 0, "waiting": 1, "idle": 2, "background": 3,
             "working": 4, "unknown": 5}
    sessions.sort(key=lambda s: (order.get(s["state"], 9), -s["idleSeconds"]))

    counts = {}
    for s in sessions:
        counts[s["state"]] = counts.get(s["state"], 0) + 1

    return {
        "sessions": sessions,
        "counts": counts,
        "total": len(sessions),
        # What the mascot should react to, resolved here rather than in QML so
        # the rule lives next to the data that defines it.
        "attention": next((s for s in sessions if s["state"] in ("asking", "waiting")), None),
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


def main() -> None:
    try:
        data = collect()
    except Exception as error:
        print(f"error: sessions probe failed: {type(error).__name__}", file=sys.stderr)
        raise SystemExit(1) from None

    # Notifications are opt-in: the probe is harmless to run, but nothing pops
    # up unless the widget asked for it.
    if "--announce" in sys.argv:
        lang = "pt" if "--pt" in sys.argv else "en"
        try:
            announce(data, lang)
        except Exception as error:
            print(f"warn: announce failed: {type(error).__name__}", file=sys.stderr)

    OUT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = OUT_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    os.chmod(tmp, 0o600)
    os.replace(tmp, OUT_FILE)

    if "--verbose" in sys.argv:
        print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
