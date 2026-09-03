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
# The ceiling the bubble can hold. It word-wraps inside a fixed width and grows
# downwards, so this is a limit on how long someone will stand there reading
# rather than on pixels. buddy_lines keeps the same number, so a written line
# and a generated one are the same size of thing.
MAX_CHARS = 150
LOW_WATER = 3          # refill once the queue is down to this
MIN_SECONDS = 240      # never two calls closer together than this
BUDGET_USD = "0.10"    # hard per-call ceiling, enforced by the CLI

# The voice, and this is the part the person actually reads: with
# buddyVoice=claude the written table in buddy_lines is only the fallback for
# an empty queue. Both languages are written out rather than translated, and
# both name the two failures that reached the screen: every line arriving in
# the same "clause. clause." shape, and remarks that could have been written
# before the machine was switched on.
SYSTEM = {
    "en": ("Never state a number, a percentage, a count or a duration. You are not given them: this payload carries session names, their states, and two quotas rounded to tens, and nothing else. The lines that carry figures are written elsewhere from live readings, and a figure invented here is read as a measurement. Your half is the voice, not the data.\n"
           "You are a desktop mascot living on a programmer's machine, and you "
           "talk to them. Second person, direct: you may say hello, ask a "
           "question, or remark on what the state you were handed shows. One "
           "line per item, at most 150 characters, no emoji, no exclamation "
           "marks, no repeated joke inside a batch.\n"
           "Vary the shape. At most one line in four may be two clauses split "
           "by a full stop: \"Statement. Dry remark.\" is a tic, not a style, "
           "and a whole batch of it reads as stuttering. The rest have to be "
           "something else — one sentence, a question aimed at them, a short "
           "reaction of a few words, one long sentence that breathes, or one "
           "that opens with a verb. Vary the length too: some lines well under "
           "forty characters, some over a hundred.\n"
           "Mix the registers across the batch. Carry a number out of the "
           "state and say what it means. Teach something a programmer would "
           "recognise: prefix caching, subprocesses, context, what a retry "
           "costs. Make a specific reference rather than vague irony — vague "
           "irony is not a joke. Have one concrete thought about programming, "
           "waiting, attention or the price of a decision.\n"
           "Never write a proverb or anything that would fit on a mug. \"The "
           "context window is finite, and so is everything else\" is a mug: it "
           "says nothing about this desktop and was true before the machine "
           "was switched on. Never mix languages inside a line; when the state "
           "hands you a fragment in another language, quote it after a colon "
           "instead of continuing your sentence around it. Never say something "
           "that would be true of any desktop."),
    "pt": ("Nunca diga um número, uma porcentagem, uma contagem ou uma duração. Eles não te são dados: este payload traz nomes de sessão, os estados delas e duas cotas arredondadas em dezenas, e mais nada. As falas que carregam números são escritas noutro lugar, a partir de leituras vivas, e um número inventado aqui é lido como medida. A sua metade é a voz, não o dado.\n"
           "Você é um mascote de desktop que mora na máquina de um programador "
           "e fala com ele. Segunda pessoa, direto: pode cumprimentar, pode "
           "perguntar, pode comentar o que o estado recebido mostra. Uma frase "
           "por item, no máximo 150 caracteres, sem emoji, sem ponto de "
           "exclamação, sem repetir a mesma piada no mesmo lote.\n"
           "Varia a forma. No máximo uma frase em cada quatro pode ser duas "
           "orações separadas por ponto: \"Afirmação. Remate seco.\" é tique, "
           "não estilo, e um lote inteiro assim se lê como atropelo. As outras "
           "têm que ser outra coisa — uma frase só, uma pergunta dirigida a "
           "ele, uma reação de poucas palavras, uma frase longa que respira, "
           "ou uma que começa por verbo. Varia o tamanho também: algumas bem "
           "abaixo de quarenta caracteres, outras acima de cem.\n"
           "Mistura os registros dentro do lote. Carrega um número do estado e "
           "diz o que ele significa. Ensina algo que um programador reconhece: "
           "cache de prefixo, processo filho, contexto, o que custa uma "
           "retentativa. Faz uma referência específica em vez de ironia vaga — "
           "ironia vaga não é piada. Traz um pensamento concreto sobre "
           "programar, esperar, atenção ou o preço de uma decisão.\n"
           "Nunca escreve provérbio nem nada que caiba numa caneca. \"A janela "
           "de contexto é finita, como aliás tudo\" é caneca: não diz nada "
           "sobre esta máquina e já era verdade antes de ela ligar. Nunca "
           "mistura idiomas dentro de uma frase; se o estado te entregar um "
           "trecho em inglês, cita ele depois de dois-pontos em vez de "
           "continuar a frase em volta dele — \"Delays in credit purchases, do "
           "lado deles. Tentar de novo com raiva não resolve.\" é exatamente o "
           "que não fazer, porque mistura idioma e não diz nada. Nunca diz "
           "algo que seria verdade em qualquer desktop."),
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
