"""Ask Claude Code for a read on a repository, on demand and off the hot path.

Why the CLI and not the API: `claude -p` authenticates with the subscription
already on this machine, so there is no key to manage and no separate bill. The
alternative, `--bare`, refuses without ANTHROPIC_API_KEY — measured: it exits 1
with "Not logged in".

Why it costs almost nothing, and why the flags are not optional. Measured on
this machine, one short answer:

    default flags        $0.1256   22,010 tokens   inherits the caller's model
    --tools "" + haiku   $0.0031    1,905 tokens
    ... + --safe-mode    $0.0018      843 tokens

The 69x is the harness: without the flags, `claude -p` loads CLAUDE.md, hooks,
plugins, skills and the whole tool schema to produce two sentences, and inherits
whichever model the caller was using. `--safe-mode` drops the customisations,
`--tools ""` drops the tool definitions, `--model haiku` stops it borrowing an
Opus, and `--strict-mcp-config` stops it dialing MCP servers.

Tools are off, so nothing is read from disk on the model's side. Everything it
gets is gathered here and passed in the prompt: that keeps it to one round
trip, and it means the call cannot touch the repository or ask for permission.

This is user-initiated only. Nothing here runs on a timer.
"""
from __future__ import annotations

import json
import subprocess

TIMEOUT = 90
MAX_DIFFSTAT = 24          # lines of git status; a huge tree is not more useful

# A nested `claude` inherits these from a parent Claude Code session and then
# hangs — measured: the same command times out with them present and returns
# in seconds with them stripped. The companion is a standalone process and
# normally has none of them, but it can be launched from a terminal inside a
# session, and a companion that silently never answers is worse than one that
# does not offer the button.
INHERITED_PREFIX = "CLAUDE"

SYSTEM = {
    "en": ("You read a repository's current state and say what is going on. "
           "Two sentences, maximum. Lead with the thing that most deserves "
           "attention. No preamble, no greeting, no bullet points, no emoji. "
           "If nothing needs attention, say so plainly."),
    "pt": ("Você lê o estado atual de um repositório e diz o que está "
           "acontecendo. No máximo duas frases. Comece pelo que mais merece "
           "atenção. Sem preâmbulo, sem saudação, sem lista, sem emoji. "
           "Se nada precisa de atenção, diga isso direto."),
}


def clean_env(base=None):
    """The parent environment without the variables a nested claude chokes on."""
    import os
    return {k: v for k, v in (base or os.environ).items()
            if not k.startswith(INHERITED_PREFIX)}


def _git(repo, *args):
    try:
        out = subprocess.run(("git", "-C", str(repo)) + args, capture_output=True,
                             text=True, timeout=8)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def gather(repo, session=None):
    """Everything the model gets. Assembled here because tools are off.

    Deliberately small: a working tree with two hundred modified files says
    the same thing as one with twenty, and paying for the other hundred and
    eighty buys nothing.
    """
    status = _git(repo, "status", "--short")
    lines = status.splitlines()
    trimmed = "\n".join(lines[:MAX_DIFFSTAT])
    if len(lines) > MAX_DIFFSTAT:
        trimmed += f"\n... and {len(lines) - MAX_DIFFSTAT} more"

    facts = {
        "repo": str(repo),
        "branch": _git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
        "uncommitted": trimmed or "(clean)",
        "recent": _git(repo, "log", "--oneline", "-5"),
        "ahead_behind": _git(repo, "rev-list", "--left-right", "--count",
                             "@{upstream}...HEAD") or "(no upstream)",
    }
    if session:
        facts["session"] = {
            "state": session.get("state"),
            "idleSeconds": session.get("idleSeconds"),
            "background": session.get("background", 0),
        }
    return facts


def build_command(prompt, lang="en", model="haiku"):
    """The flags are the whole point; see the measurements in the docstring."""
    return [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--model", model,
        # Two sentences over facts already gathered is not a reasoning problem.
        # The default effort spends thinking tokens deciding how to phrase a
        # summary, which is the most expensive way to be brief.
        "--effort", "low",
        "--tools", "",
        "--system-prompt", SYSTEM.get(lang, SYSTEM["en"]),
        "--strict-mcp-config",
        "--safe-mode",
    ]


def parse(stdout):
    """Pull the answer out of the result envelope.

    The envelope is a list of events, not an object, and it can carry raw
    control characters, which strict JSON rejects.
    """
    try:
        events = json.loads(stdout, strict=False)
    except (json.JSONDecodeError, TypeError):
        return None, {}
    if isinstance(events, dict):
        events = [events]
    for event in events:
        if isinstance(event, dict) and event.get("type") == "result":
            usage = event.get("usage") or {}
            return (event.get("result") or "").strip(), {
                "costUSD": event.get("total_cost_usd"),
                "ms": event.get("duration_ms"),
                "tokens": sum(usage.get(k, 0) or 0 for k in (
                    "input_tokens", "output_tokens",
                    "cache_read_input_tokens", "cache_creation_input_tokens")),
            }
    return None, {}


def brief(repo, session=None, lang="en", model="haiku", runner=None):
    """A short read on the repository, or None if the call did not come back."""
    facts = gather(repo, session)
    prompt = (("Estado de " if lang == "pt" else "State of ")
              + f"{facts['repo']}:\n" + json.dumps(facts, indent=1, ensure_ascii=False))
    command = build_command(prompt, lang=lang, model=model)
    run = runner or (lambda cmd: subprocess.run(
        cmd, capture_output=True, text=True, timeout=TIMEOUT, cwd=str(repo),
        stdin=subprocess.DEVNULL, env=clean_env()))
    try:
        done = run(command)
    except (OSError, subprocess.SubprocessError):
        return None, {}
    return parse(done.stdout)
