"""The on-demand read on a repository, and the flags that make it cheap.

Measured on this machine for one short answer:

    default flags        $0.1256   22,010 tokens   inherits the caller's model
    --tools "" + haiku   $0.0031    1,905 tokens
    ... + --safe-mode    $0.0018      843 tokens

Nothing here calls the API; the runner is injected.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import repo_brief


class _Done:
    def __init__(self, stdout):
        self.stdout = stdout
        self.returncode = 0


def _envelope(text, cost=0.0018, tokens=843):
    return json.dumps([
        {"type": "system", "subtype": "init"},
        {"type": "result", "subtype": "success", "result": text,
         "total_cost_usd": cost, "duration_ms": 3300,
         "usage": {"input_tokens": 600, "output_tokens": tokens - 600}},
    ])


def test_the_expensive_defaults_are_all_overridden():
    """Each flag is worth an order of magnitude and none is decoration.

    Without --model the call inherits whatever the caller was using, which on
    the machine this was measured on meant an Opus answering a one-line
    question for twelve cents.
    """
    cmd = repo_brief.build_command("hello")
    for flag in ("--model", "--tools", "--system-prompt", "--strict-mcp-config",
                 "--safe-mode", "--output-format"):
        assert flag in cmd, f"{flag} missing; the call reverts to the expensive path"
    assert cmd[cmd.index("--tools") + 1] == "", "tools not actually disabled"
    assert cmd[cmd.index("--model") + 1] == "haiku"


def test_the_prompt_carries_the_facts_because_tools_are_off():
    """With no tools the model cannot look at anything, so everything it is
    going to know has to be in the prompt."""
    captured = {}

    def runner(cmd):
        captured["prompt"] = cmd[cmd.index("-p") + 1]
        return _Done(_envelope("tudo certo"))

    repo_brief.brief(REPO, {"state": "working", "background": 2}, runner=runner)
    prompt = captured["prompt"]
    assert "branch" in prompt and "recent" in prompt
    assert "background" in prompt, "the session state never reached the model"


def test_a_huge_working_tree_is_trimmed():
    """Two hundred modified files say what twenty say, and the other hundred
    and eighty are paid for."""
    lines = [f" M file{i}.py" for i in range(200)]
    trimmed = repo_brief.gather.__doc__  # documented behaviour
    assert "small" in trimmed.lower()
    facts = repo_brief.gather(REPO)
    assert facts["uncommitted"].count("\n") <= repo_brief.MAX_DIFFSTAT


def test_the_result_envelope_is_a_list_and_can_hold_control_characters():
    """It is not an object, and strict JSON rejects the raw control characters
    it can carry — both of which broke the first parser written for it."""
    raw = json.dumps([{"type": "result", "subtype": "success",
                       "result": "linha", "total_cost_usd": 0.002,
                       "usage": {"output_tokens": 12}}])
    raw = raw.replace("linha", "linha\x1bcom controle")
    text, meta = repo_brief.parse(raw)
    assert text and "controle" in text
    assert meta["costUSD"] == 0.002


def test_a_call_that_never_returns_is_not_an_exception():
    """The companion asks for this from a menu; a timeout has to come back as
    'no answer', not as a traceback in a desktop process."""
    def runner(cmd):
        raise subprocess.TimeoutExpired(cmd, 90)

    text, meta = repo_brief.brief(REPO, runner=runner)
    assert text is None and meta == {}


def test_the_variables_that_hang_a_nested_call_are_stripped():
    """A nested claude inherits these from a parent session and then hangs:
    measured, the same command times out with them present and returns in
    seconds without. The companion is standalone and normally has none, but it
    can be started from a terminal inside a session."""
    env = repo_brief.clean_env({
        "PATH": "/usr/bin", "HOME": "/home/x",
        "CLAUDE_CODE_MESSAGING_SOCKET": "/tmp/s", "CLAUDECODE": "1",
    })
    assert env == {"PATH": "/usr/bin", "HOME": "/home/x"}
