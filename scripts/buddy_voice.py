"""Lines written by Claude instead of drawn from a table, in batches.

Why batches. One call per remark is what the menu does, and it is the wrong
shape for ambient chatter: measured on this machine, a single short answer
costs about $0.024 and takes forty seconds. A batch of twelve costs $0.031 and
takes fifty-four — $0.0026 a line, ten times cheaper, and the wait happens once
instead of before every sentence.

So the companion never waits for the model. It speaks from a queue that a
background call refills, and falls back to the written table whenever the queue
is empty. Nothing here can make the character go quiet or make it stutter: the
worst case is that it sounds like it did before.

Refills are triggered by the situation changing, not by a clock. A queue that
tops itself up every N minutes spends money describing a desktop that has not
moved; a signature of what the sessions are doing means a quiet afternoon costs
one call.
"""
from __future__ import annotations

import json

from repo_brief import build_command, claude_binary, clean_env, parse   # noqa: F401

BATCH = 12
MAX_CHARS = 110
LOW_WATER = 3          # refill once the queue is down to this
MIN_SECONDS = 240      # never two calls closer together than this
BUDGET_USD = "0.10"    # hard per-call ceiling, enforced by the CLI

SYSTEM = {
    "en": ("You are a programmer's desktop mascot. Short, dry, deadpan lines, "
           "sometimes philosophical. One sentence each, at most 110 characters. "
           "Never greet, never explain, never use emoji, never repeat a joke. "
           "Talk about the actual state you are given."),
    "pt": ("Você é o mascote de desktop de um programador. Frases curtas, secas, "
           "debochadas, às vezes filosóficas. Uma frase por item, no máximo 110 "
           "caracteres. Nunca cumprimenta, nunca explica, nunca usa emoji, nunca "
           "repete a mesma piada. Fala sobre o estado real que recebe."),
}

SCHEMA = json.dumps({
    "type": "object",
    "properties": {"lines": {
        "type": "array", "minItems": 6, "maxItems": BATCH + 2,
        "items": {"type": "string", "maxLength": MAX_CHARS}}},
    "required": ["lines"],
})


def situation(sessions, usage):
    """What the model is told, and what decides when to ask again.

    Deliberately coarse. Idle seconds are bucketed and percentages rounded to
    tens, so a number ticking up by one does not read as a new situation and
    buy a new batch.
    """
    rows = []
    for session in (sessions.get("sessions") or [])[:8]:
        idle = session.get("idleSeconds") or 0
        rows.append({
            "name": session.get("name") or "?",
            "state": session.get("state") or "unknown",
            "quietFor": ("moments" if idle < 60 else
                         f"{idle // 60}min" if idle < 3600 else f"{idle // 3600}h"),
            "background": session.get("background") or 0,
        })
    limits = (usage or {}).get("rateLimits") or {}

    def pct(block):
        value = (limits.get(block) or {}).get("percentUsed")
        return None if value is None else int(round(value / 10.0) * 10)

    return {"sessions": rows,
            "usage": {"session5h": pct("session"), "weekly": pct("weeklyAll")}}


def signature(state):
    """A stable key for a situation, so an unchanged desktop costs nothing."""
    return json.dumps(state, sort_keys=True, ensure_ascii=False)


def build(state, lang="en", count=BATCH):
    """The command for one batch. Nothing here runs it."""
    prompt = (f"Gere {count} falas para este estado. Varie o assunto."
              if lang == "pt" else
              f"Write {count} lines for this state. Vary what they are about.")
    command = build_command(prompt + "\n" + json.dumps(state, ensure_ascii=False,
                                                       indent=1), lang=lang)
    # build_command carries the cheap defaults; these are the batch's own.
    command[command.index("--system-prompt") + 1] = SYSTEM.get(lang, SYSTEM["en"])
    return command + ["--json-schema", SCHEMA, "--max-budget-usd", BUDGET_USD]


def harvest(stdout):
    """Usable lines from a finished call. Never raises, never returns junk.

    Everything is filtered rather than trusted: the schema caps the length but
    not the content, and a model that decides to number its answers or wrap
    them in quotes would otherwise put that on the screen.
    """
    text, meta = parse(stdout)
    if not text:
        return [], meta
    try:
        payload = json.loads(text, strict=False)
    except (json.JSONDecodeError, TypeError):
        return [], meta
    lines = payload.get("lines") if isinstance(payload, dict) else payload
    if not isinstance(lines, list):
        return [], meta
    clean = []
    for line in lines:
        if not isinstance(line, str):
            continue
        line = line.strip().strip('"').lstrip("-•").strip()
        while line[:2].rstrip(".").isdigit() and "." in line[:4]:
            line = line.split(".", 1)[1].strip()
        if 8 <= len(line) <= MAX_CHARS:
            clean.append(line)
    return clean, meta


class Voice:
    """The queue, and the decision of when to buy more of it.

    Holds no Qt and starts no process: the companion owns the subprocess so the
    UI thread is never blocked. This decides *whether* to ask and what to say
    next, which is the part worth testing without a display.
    """

    def __init__(self, lang="en", now=0.0):
        self.lang = lang
        self.queue = []
        self.signature = None
        self.last_call = now - MIN_SECONDS
        self.failures = 0

    def should_refill(self, state, now):
        """True when it is worth spending a call.

        Three gates, and every one of them exists to stop money leaking: the
        situation has to have actually changed or the queue run low, calls are
        spaced, and repeated failures back off instead of retrying forever.
        """
        if claude_binary() is None:
            return False
        if now - self.last_call < MIN_SECONDS * (1 + min(self.failures, 4)):
            return False
        if not (state.get("sessions") or []):
            return False
        return len(self.queue) <= LOW_WATER or signature(state) != self.signature

    def started(self, state, now):
        self.signature = signature(state)
        self.last_call = now

    def delivered(self, lines):
        if not lines:
            self.failures += 1
            return 0
        self.failures = 0
        self.queue.extend(lines)
        return len(lines)

    def take(self):
        """The next line, or None to fall back to the written table."""
        return self.queue.pop(0) if self.queue else None
