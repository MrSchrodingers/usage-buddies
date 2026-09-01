#!/usr/bin/env python3
"""A desktop companion that walks around and tells you which session needs you.

Why a separate process rather than part of the plasmoid: a Plasma applet lives
inside the panel's window and cannot leave it. A companion that wanders the
screen needs a top-level window of its own.

Why XWayland: under Wayland a client is not allowed to position its own window
— the protocol has no call for it, by design. Forcing the xcb platform routes
through XWayland, where `move()` works and a window can stay above others.
This is a deliberate trade: the alternative is asking KWin to reposition the
window over D-Bus on every frame, which is neither smooth nor kind to the
compositor.

It reads the same files the widget reads and never writes to them. Everything
it says is bound to a measured trigger; with nothing to report it wanders in
silence, and closing it is a right-click away.
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

# Must be set before QtGui is imported, or the platform is already chosen.
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from PySide6.QtCore import (Qt, QTimer, QPointF, QRectF, Signal, QObject,        # noqa: E402
                            QProcess, QProcessEnvironment)
from PySide6.QtGui import (QAction, QColor, QCursor, QFont, QFontMetrics,        # noqa: E402
                           QPainter, QPainterPath, QPen)
from PySide6.QtWidgets import QApplication, QMenu, QWidget                       # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import buddy_sprites as sprites                                                  # noqa: E402
import repo_brief                                                                # noqa: E402
import buddy_voice                                                               # noqa: E402
import virtual_pointer                                                           # noqa: E402

CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "usage-buddies"
SESSIONS_FILE = CACHE / "sessions.json"
WIDGET_DATA = Path.home() / ".claude" / "widget-data.json"
ICONS = Path(__file__).resolve().parent.parent / "plasmoid" / "contents" / "icons"
INSTALLED_ICONS = (Path.home() / ".local/share/plasma/plasmoids"
                   / "org.kde.plasma.usagebuddies/contents/icons")
FOCUS_HELPER = Path.home() / ".local" / "bin" / "focus-session.sh"

BUDDY_PX = sprites.SIZE          # grid times an integer scale; nothing is resampled
BUBBLE_MAX = 300
POLL_MS = 20_000

# Two frame rates. Animating at 30fps continuously costs a steady slice of a
# core to render a character that is standing still most of the time; idle
# ticks at 5fps are enough to notice a new target and start moving.
FRAME_MS_ACTIVE = 33
FRAME_MS_IDLE = 200

WALK_SPEED = 78.0        # px/s horizontally
CLIMB_SPEED = 46.0       # px/s vertically — slower, so diagonals read as effort
IDLE_MIN, IDLE_MAX = 4.0, 14.0
SPEAK_SECONDS = 16.0
SLEEP_AFTER = 45.0       # docked and untouched for this long: it dozes off
# Being dragged. A short drag is how you put it somewhere; a long one is
# someone playing with it, and it is allowed to notice.
DRAG_PATIENCE = 3.5      # seconds of continuous dragging before it complains
DRAG_MEMORY = 90.0       # window over which repeated drags accumulate
DRAG_TUG_AFTER = 2       # drags inside that window before it pulls back
DRAG_TUG_DISTANCE = 900  # or one drag that hauls it this far, in pixels
TUG_SECONDS = 7.0        # how long it holds on, hard cap
TUG_RUN_SPEED = 340.0    # px/s while it is running off with the pointer
TUG_SPIN = 0.14          # fraction of the getaway spent burning rubber before
                         # it actually goes anywhere
TUG_ARC = 0.34           # how far the route bows away from the straight line,
                         # as a fraction of its length
TUG_BOUNCE = 3.4         # suspension travel, px
TUG_SHAKE = 2.2          # how much it shudders during the wheelspin, px
TUG_STEP = 6             # largest delta sent to the pointer at once, in px.
                         # libinput accelerates: one big jump travels much
                         # further than the same distance in small steps, and
                         # the point is to carry the pointer, not launch it.
TUG_COOLDOWN = 420.0     # and then it leaves you alone for a while
DRAG_TUG_SECONDS = 5.0   # or one drag held this long, which is the same message
DRAG_TUG_ALWAYS = 10.0   # held this long there is no cooldown: at ten seconds
                         # of hauling it around you are asking for it, and
                         # having to wait seven minutes to ask again turns a
                         # deliberate act into a lottery

# The swing. The body is not glued to the cursor: it hangs from it on a spring
# and trails, which is what makes a dragged sprite read as having weight.
# Tuned by eye at 30fps — stiff enough to keep up, loose enough to overshoot.
SWING_STIFFNESS = 145.0
SWING_DAMPING = 0.80     # per 1/60s, so the feel does not change with the rate
SWING_MAX_LEAN = 190.0   # px/s of horizontal speed that reaches the deepest pose

# The wobble. This is the part that is in the sprite rather than in the window:
# the body itself stretches and squashes, on its own spring, so it keeps
# jiggling for a moment after the movement stops instead of snapping rigid.
WOBBLE_SPEED = 190.0     # px/s of speed that reaches full stretch
WOBBLE_K = 34.0          # how hard it is pulled back toward its resting shape
WOBBLE_DAMP = 0.90       # per 1/60s; lower settles sooner and jiggles less
ALERT_SECONDS = 1.4      # the double-take when something needs the human
SNAP_MARGIN = 26         # how close to an edge a drop counts as "put me here"


# What it can say. Several lines per trigger, because two lines in rotation is
# the same line: the previous version said "ti finished" for an hour straight.
#
# Categories beyond the alerts exist so that a quiet system still produces
# variety — a companion with nothing to say and no idle repertoire either says
# the same alert forever or goes mute.
LINES = {
    "en": {
        "background": [
            "{name} says it is done. It has {n} still running.",
            "The turn ended in {name}; the work did not. {n} still going.",
            "{name}: agent still working. Do not close that terminal.",
            "Careful with {name} — {n} running in the background.",
            "{name} looks finished and is not. {n} still out there.",
        ],
        "allQuiet": [
            "{name} stopped, and so did everything it started. {idle} ago.",
            "Nothing moving in {name}: no turn, no agents. {idle}.",
            "{name} is properly done — the session and its background work.",
            "{name} has been fully still for {idle}. That one is finished.",
            "Everything in {name} has stopped, background included.",
        ],
        "asking": [
            "{name} asked you something and is just sitting there.",
            "{name} needs a decision. It will wait forever — that is the problem.",
            "{name} has a question. Its patience is infinite and unhelpful.",
            "{name} is blocked on you. No pressure.",
            "{name} wants an answer. It is not going to guess.",
        ],
        "waiting": [
            "{name} finished. Go look before you forget it existed.",
            "{name} is done and idling. Your move.",
            "{name} wrapped up {idle} ago. Still waiting.",
            "{name} finished {idle} ago and has been staring at a wall since.",
            "{name} is done. Whether it did the right thing is a separate question.",
            "{name} stopped {idle} ago. Someone should check.",
            "{name} delivered. Review is the part people skip.",
        ],
        "idle": [
            "{name} has done nothing for {idle}. Existential, really.",
            "{name} is idle. Contemplating the void, presumably.",
            "{name} has been still for {idle}. Either done or forgotten.",
            "{name}: {idle} of nothing. A monument to potential.",
            "{name} idles. Somewhere a token goes unspent.",
        ],
        "twoRed": [
            "Two quotas in the red. This is fine.",
            "Both limits burning. Bold strategy.",
            "Two quotas red at once. That takes commitment.",
            "Multiple limits critical. The plan is working.",
        ],
        "compaction": [
            "{n} compactions today. You keep forgetting things and calling it progress.",
            "Memory wiped {n} times. Ship of Theseus, but worse.",
            "{n} compactions. Each one a small funeral for context.",
            "{n} times the context was too big to keep. Consider smaller questions.",
        ],
        "readRatio": [
            "{n}:1 read per output. Reading a library to write a postcard.",
            "{n} tokens in, one out. Efficient is not the word.",
            "{n}:1. Most of that context is along for the ride.",
            "Reading {n} for every one written. Somebody is not skimming.",
        ],
        "bashHeavy": [
            "{n}% of your calls are Bash. There are other tools. Allegedly.",
            "{n}% Bash. The other tools are right there, unused.",
            "{n}% of everything is a shell command. A philosophy, of sorts.",
        ],
        "cacheDrop": [
            "Cache hit down to {n}%. Something is invalidating the prefix.",
            "{n}% cache hit. Your prefix is leaking somewhere.",
            "Cache at {n}%. A timestamp in the system prompt would do that.",
        ],
        "nightOwl": [
            "It is late. The commit will still be broken tomorrow.",
            "Past midnight. Nothing good gets merged at this hour.",
            "This late, the bug you are chasing is usually a typo.",
            "The night shift. Tomorrow-you will read this code as a stranger.",
        ],
        "sessionSpread": [
            "{n} sessions running. Impressive, or a diagnosis.",
            "{n} Claudes at once. Someone is going to lose track.",
            "{n} sessions in flight. Hope you remember what {name} was for.",
        ],
        "ambient": [
            "Everything is fine. Suspiciously so.",
            "Nothing needs you. Enjoy it while it lasts.",
            "All quiet. That is either good news or the calm part.",
            "No alerts. The machines are behaving.",
            "Nothing to report. I checked twice.",
            "Systems nominal. Deeply uneventful.",
            "Still here. Still watching. Still nothing.",
        ],
        "philosophy": [
            "A machine that never rests is not the same as one that never stops.",
            "You automate the work and then supervise the automation. Progress.",
            "Every token spent is a small bet that the answer exists.",
            "The tool got faster. The thinking did not.",
            "Someone will read this code. Statistically, it will be you.",
            "The context window is finite. So, for that matter, is everything.",
            "You did not build a tool. You built something that has opinions.",
            "Waiting is the only part of this that has not been optimised.",
            "The machine is patient because it does not know what it is waiting for.",
            "Nothing here understands the problem. Between us, that makes two.",
            "A correct answer arrived at by luck is still an answer, and still luck.",
            "The work expands to fill the tokens available for its completion.",
            "You are the slowest component and the only one that decides anything.",
            "It will finish. Whether it finishes what you meant is a separate question.",
            "Determinism was a promise made before anyone tried it.",
        ],
    },
    "pt": {
        "background": [
            "{name} diz que acabou. Tem {n} ainda rodando.",
            "O turno acabou em {name}; o trabalho não. {n} em andamento.",
            "{name}: agente ainda trabalhando. Não fecha esse terminal.",
            "Cuidado com o {name} — {n} rodando em background.",
            "{name} parece pronto e não está. {n} ainda por aí.",
        ],
        "allQuiet": [
            "{name} parou, e tudo que ele começou também. Faz {idle}.",
            "Nada se move em {name}: nem turno, nem agente. {idle}.",
            "{name} terminou de verdade — a sessão e o que rodava atrás.",
            "{name} está totalmente parado há {idle}. Esse acabou.",
            "Tudo em {name} parou, background incluído.",
        ],
        "asking": [
            "{name} te perguntou algo e está lá, parado.",
            "{name} precisa de uma decisão. Ele espera pra sempre — esse é o problema.",
            "{name} tem uma pergunta. A paciência dele é infinita e inútil.",
            "{name} está travado esperando você. Sem pressa.",
            "{name} quer uma resposta. Adivinhar ele não vai.",
        ],
        "waiting": [
            "{name} terminou. Vai lá conferir antes de esquecer que existe.",
            "{name} acabou e está de bobeira. É sua vez.",
            "{name} fechou há {idle}. Continua esperando.",
            "{name} terminou há {idle} e está encarando a parede desde então.",
            "{name} entregou. Se entregou certo é outra conversa.",
            "{name} parou há {idle}. Alguém devia conferir.",
            "{name} concluiu. Revisar é a parte que todo mundo pula.",
        ],
        "idle": [
            "{name} não faz nada há {idle}. Existencial, no fundo.",
            "{name} está ocioso. Contemplando o vazio, presumo.",
            "{name} parado há {idle}. Ou terminou, ou foi esquecido.",
            "{name}: {idle} de nada. Um monumento ao potencial.",
            "{name} ocioso. Em algum lugar um token deixa de ser gasto.",
        ],
        "twoRed": [
            "Duas cotas no vermelho. This is fine.",
            "Os dois limites queimando. Estratégia ousada.",
            "Duas cotas vermelhas ao mesmo tempo. Isso é dedicação.",
            "Vários limites críticos. O plano está funcionando.",
        ],
        "compaction": [
            "{n} compactações hoje. Você esquece tudo e chama de progresso.",
            "Memória apagada {n} vezes. Barco de Teseu, só que pior.",
            "{n} compactações. Cada uma um pequeno velório de contexto.",
            "{n} vezes o contexto não coube. Considere perguntas menores.",
        ],
        "readRatio": [
            "{n}:1 de leitura por saída. Lendo uma biblioteca pra escrever um bilhete.",
            "{n} tokens entram, um sai. Eficiente não é a palavra.",
            "{n}:1. Boa parte desse contexto está só pegando carona.",
            "Lendo {n} pra cada um escrito. Alguém não está passando o olho.",
        ],
        "bashHeavy": [
            "{n}% das suas chamadas são Bash. Existem outras ferramentas. Dizem.",
            "{n}% Bash. As outras ferramentas estão bem ali, intactas.",
            "{n}% de tudo é comando de shell. Uma filosofia, de certa forma.",
        ],
        "cacheDrop": [
            "Cache caiu pra {n}%. Alguma coisa está invalidando o prefixo.",
            "{n}% de acerto no cache. Seu prefixo está vazando.",
            "Cache em {n}%. Um timestamp no system prompt faria isso.",
        ],
        "nightOwl": [
            "Tá tarde. O commit vai continuar quebrado amanhã.",
            "Passou da meia-noite. Nada bom entra em produção nessa hora.",
            "A essa hora, o bug que você persegue costuma ser um typo.",
            "Turno da madrugada. Amanhã você lê esse código como estranho.",
        ],
        "sessionSpread": [
            "{n} sessões rodando. Impressionante, ou um diagnóstico.",
            "{n} Claudes ao mesmo tempo. Alguém vai se perder.",
            "{n} sessões no ar. Tomara que você lembre pra que era o {name}.",
        ],
        "ambient": [
            "Tudo certo. Suspeitamente certo.",
            "Ninguém precisa de você. Aproveita.",
            "Tudo quieto. Ou é boa notícia, ou é a parte calma.",
            "Nenhum alerta. As máquinas estão se comportando.",
            "Nada a relatar. Conferi duas vezes.",
            "Sistemas nominais. Profundamente sem graça.",
            "Ainda aqui. Ainda olhando. Ainda nada.",
        ],
        "philosophy": [
            "Uma máquina que nunca descansa não é a mesma coisa que uma que nunca para.",
            "Você automatiza o trabalho e depois supervisiona a automação. Progresso.",
            "Cada token gasto é uma pequena aposta de que a resposta existe.",
            "A ferramenta ficou mais rápida. O pensamento, não.",
            "Alguém vai ler esse código. Estatisticamente, vai ser você.",
            "A janela de contexto é finita. Como, aliás, tudo.",
            "Você não construiu uma ferramenta. Construiu algo com opiniões.",
            "Esperar é a única parte disso que ninguém otimizou.",
            "A máquina é paciente porque não sabe o que está esperando.",
            "Nada aqui entende o problema. Cá entre nós, somos dois.",
            "Resposta certa por sorte continua sendo resposta, e continua sendo sorte.",
            "O trabalho se expande até ocupar todos os tokens disponíveis.",
            "Você é o componente mais lento e o único que decide alguma coisa.",
            "Vai terminar. Se termina o que você quis dizer é outra pergunta.",
            "Determinismo foi uma promessa feita antes de alguém tentar.",
        ],
    },
}


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _fmt_idle(seconds):
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}min"
    return f"{seconds // 3600}h"


class Brain(QObject):
    """Decides what is worth saying, in the same order the widget uses.

    Two rules keep it from becoming wallpaper. It remembers what it recently
    said and will not repeat inside that window — the previous version rotated
    two lines and so effectively said one. And when several sessions qualify it
    rotates between them, because "ti finished" for an hour is the same
    complaint whether the sentence changes or not.
    """

    RECENT = 12          # lines to remember before allowing a repeat
    SUBJECT_RECENT = 3   # sessions to cycle past before returning to one

    def __init__(self, lang="en", alerts_only=False):
        super().__init__()
        self.lang = lang if lang in LINES else "en"
        self.alerts_only = alerts_only
        self.sessions = {}
        self.usage = {}
        self._recent = []
        self._subjects = []

    def refresh(self):
        self.sessions = _read_json(SESSIONS_FILE)
        self.usage = _read_json(WIDGET_DATA)

    @property
    def attention(self):
        return (self.sessions or {}).get("attention")

    def _all(self, *states):
        return [s for s in (self.sessions.get("sessions") or [])
                if s.get("state") in states]

    def _rotate(self, candidates):
        """Prefer a session not spoken about lately.

        With three sessions waiting, always announcing the first turns a useful
        signal into background noise about one repo.
        """
        if not candidates:
            return None
        fresh = [c for c in candidates if c.get("name") not in self._subjects]
        chosen = random.choice(fresh) if fresh else random.choice(candidates)
        self._subjects.append(chosen.get("name"))
        del self._subjects[:-self.SUBJECT_RECENT]
        return chosen

    def _pick(self, key, **vars_):
        table = LINES[self.lang].get(key) or []
        if not table:
            return None
        unsaid = [t for t in table if t not in self._recent]
        text = random.choice(unsaid or table)
        self._recent.append(text)
        del self._recent[:-self.RECENT]
        for k, v in vars_.items():
            text = text.replace("{" + k + "}", str(v))
        return text

    def line(self):
        """The current thing worth saying, or None. Silence is the default."""
        asking = self._all("asking")
        if asking:
            s = self._rotate(asking)
            return self._pick("asking", name=s.get("name", "?"))

        waiting = self._all("waiting")
        if waiting:
            s = self._rotate(waiting)
            return self._pick("waiting", name=s.get("name", "?"),
                              idle=_fmt_idle(s.get("idleSeconds", 0)))

        # A session that stopped *and* has nothing left running is the one
        # worth calling finished. Kept apart from plain "idle" because quiet
        # with an agent still going is not the same news as quiet all the way
        # down, and only the second one means go and look.
        idle = self._all("idle")
        if idle:
            s = self._rotate(idle)
            key = "idle" if s.get("background") else "allQuiet"
            return self._pick(key, name=s.get("name", "?"),
                              idle=_fmt_idle(s.get("idleSeconds", 0)))

        # Below everything that wants a human: background work is information,
        # not a summons. It exists so the companion stops announcing a session
        # as finished while its agent is still writing.
        busy = self._all("background")
        if busy:
            s = self._rotate(busy)
            return self._pick("background", name=s.get("name", "?"),
                              n=s.get("background", 1))

        if self.alerts_only:
            return None

        # Diagnostics, worst first. Each fires only above a threshold, so a
        # healthy system falls through to the ambient lines instead of being
        # told the same non-problem repeatedly.
        eff = self.usage.get("efficiency") or {}
        hit = eff.get("cacheHitRate")
        if hit is not None and 0 < hit < 0.3:
            return self._pick("cacheDrop", n=round(hit * 100))

        comp = (self.usage.get("compaction") or {}).get("count", 0)
        if comp >= 5:
            return self._pick("compaction", n=comp)

        ratio = eff.get("readPerOutput") or 0
        if ratio >= 300:
            return self._pick("readRatio", n=round(ratio))

        tools = (self.usage.get("toolUse") or {}).get("byTool") or {}
        total = sum(tools.values())
        if total > 200:
            name, count = max(tools.items(), key=lambda kv: kv[1])
            if count / total > 0.7 and name == "Bash":
                return self._pick("bashHeavy", n=round(100 * count / total))

        running = self.sessions.get("total") or 0
        if running >= 4:
            sample = (self.sessions.get("sessions") or [{}])[0]
            return self._pick("sessionSpread", n=running,
                              name=sample.get("name", "?"))

        if 0 <= time.localtime().tm_hour < 5:
            return self._pick("nightOwl")

        # Nothing is wrong. Alternate between saying so and saying something
        # else entirely, so silence has texture.
        return self._pick(random.choice(("ambient", "philosophy")))


def _menu_labels(sessions):
    """Labels that name one session each.

    Two sessions open on the same directory produce two identical entries and
    the menu becomes a coin toss. Only the ambiguous ones get a suffix, so the
    common case stays clean: the branch when it tells them apart, the pid when
    it does not.
    """
    from collections import Counter
    names = Counter((s.get("name") or "?") for s in sessions)
    labels = []
    for session in sessions:
        name = session.get("name") or "?"
        if names[name] == 1:
            labels.append(name)
            continue
        branch = session.get("branch") or ""
        same = [s for s in sessions if (s.get("name") or "?") == name]
        if branch and len({s.get("branch") or "" for s in same}) == len(same):
            labels.append(f"{name} · {branch}")
        else:
            labels.append(f"{name} · {session.get('pid')}")
    return labels


class Companion(QWidget):
    """The character. Everything here is presentation; Brain decides what it says.

    It roams the whole screen rather than sliding along the bottom edge: a
    companion pinned to one line reads as a status bar with a face. Movement is
    a walk toward a target with a gait — leaning into the direction, bobbing
    per step, squashing on landing — because constant-velocity translation
    reads as a sprite being dragged, not a thing that moves itself.
    """

    def __init__(self, brand="claude", lang="en", alerts_only=False, live=False):
        super().__init__(None)
        # No BypassWindowManagerHint: it is not needed for positioning under
        # XWayland (both were measured placing and moving a window correctly)
        # and it costs reliable mouse input, which this needs for click and drag.
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setCursor(Qt.OpenHandCursor)

        # Every frame in both directions, built once. Baking the mirror here
        # means the paint path is a single drawImage with no transform on it:
        # rotation and non-integer scale are the two things that turn pixel
        # art to mush, and the way to not do them is to have no transform.
        self.sheet = sprites.build_sheet(brand)
        self.anim = sprites.Animator("idle")
        self.frame = "stand_open"
        self.alert_until = 0.0
        self.settled_at = time.monotonic()
        # One at a time. A menu that can start six of these leaves six
        # subscription-billed calls in flight for one impatient click.
        self.asking = None
        # Lines from Claude when they are ready, the written table when they
        # are not. The companion never waits on the model: worst case it
        # sounds exactly like it did before.
        self.voice = buddy_voice.Voice(lang, time.monotonic()) if live else None
        self.refilling = None

        self.brain = Brain(lang, alerts_only)
        self.lang = lang
        self.bubble = ""
        self.bubble_until = 0.0
        self.said = ""
        self.bubble_size = (0, 0)

        # Every screen, not just the primary one. Confined to the primary it
        # never appears on the other monitor at all, which is most of the time
        # someone spends looking somewhere.
        self.screens = [s.availableGeometry() for s in QApplication.screens()]
        if not self.screens:
            self.screens = [QApplication.primaryScreen().availableGeometry()]
        self.bounds = self.screens[0]
        for g in self.screens[1:]:
            self.bounds = self.bounds.united(g)
        self.min_x = self.bounds.left() + 8
        self.max_x = self.bounds.right() - BUDDY_PX - 8
        self.min_y = self.bounds.top() + 8
        self.max_y = self.bounds.bottom() - BUDDY_PX - 8

        self.pos_x = float(random.randint(self.min_x, self.max_x))
        self.pos_y = float(self.max_y)
        self.target = (self.pos_x, self.pos_y)
        self.facing = 1
        self.next_move = time.monotonic() + random.uniform(IDLE_MIN, IDLE_MAX)

        # Drag state. `docked` survives a drop near an edge: put down in a
        # corner, it stays there instead of wandering off, because that is what
        # putting something in a corner means.
        self.dragging = False
        self.drag_offset = QPointF(0, 0)
        self.docked = False
        # Not 0.0: the drag timer is read as `now - drag_started`, and from
        # zero that is the age of the monotonic clock — so a companion that has
        # only just been picked up would start out already exasperated.
        self.drag_started = time.monotonic()
        self.hand = None          # where the cursor is; the body chases it
        self.vel_x = 0.0
        self.vel_y = 0.0
        self.wobble = 0.0
        self.wobble_v = 0.0
        self.drag_complained = False
        self.recent_drags = []
        self.drag_distance = 0.0
        self.tug_until = 0.0
        self.tugged_at = 0.0
        self.tug_from = None
        self.tug_route = None
        self.tug_began = 0.0
        self.pointer = None

        self.resize(BUDDY_PX, BUDDY_PX)
        self._place()

        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self._tick)
        self.frame_timer.start(FRAME_MS_ACTIVE)
        self._active = True

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll)
        self.poll_timer.start(POLL_MS)
        QTimer.singleShot(200, self._poll)
        # After the window is mapped, or there is nothing to set the property on.
        QTimer.singleShot(600, self._make_sticky)

    # ── what it says ──

    def _poll(self):
        self.brain.refresh()
        self._maybe_refill()
        line = self.brain.line()
        if line and self.voice is not None:
            # Only ever swaps the words. The decision of *whether* to speak
            # stays with Brain, which is bound to measured triggers; letting
            # the model decide that too is how a companion becomes noise.
            spoken = self.voice.take()
            if spoken:
                line = spoken
        if line and line != self.said:
            self.said = line
            self.bubble = line
            now = time.monotonic()
            self.bubble_until = now + SPEAK_SECONDS
            # The double-take only fires for something that wants the human.
            # Ambient remarks get no jump, or the jump stops meaning anything.
            if self.brain.attention:
                self.alert_until = now + ALERT_SECONDS
            self._resize_for_bubble()
            if not self.docked:
                # Step away from the edges so the bubble has room to open.
                self.target = (
                    max(self.min_x + 160, min(self.max_x - 160, self.pos_x + random.uniform(-140, 140))),
                    max(self.min_y + 60, min(self.max_y, self.pos_y)))
            self._wake()
        elif not line:
            self.said = ""

    def _maybe_refill(self):
        """Buy another batch of lines, if the desktop has actually changed.

        Runs at most one call at a time and never blocks: the answer arrives on
        a signal, and until it does the companion keeps talking from the table.
        """
        if self.voice is None or self.refilling is not None:
            return
        state = buddy_voice.situation(self.brain.sessions or {}, self.brain.usage or {})
        now = time.monotonic()
        if not self.voice.should_refill(state, now):
            return
        command = buddy_voice.build(state, self.lang)

        environment = QProcessEnvironment()
        for key, value in repo_brief.clean_env().items():
            environment.insert(key, value)

        process = QProcess(self)
        process.setProcessEnvironment(environment)
        process.finished.connect(
            lambda _c=0, _st=0, p=process: self._refilled(p))
        process.errorOccurred.connect(lambda _e, p=process: self._refilled(p))
        self.refilling = process
        self.voice.started(state, now)
        process.start(command[0], command[1:])

    def _refilled(self, process):
        if process is not self.refilling:
            return
        self.refilling = None
        raw = bytes(process.readAllStandardOutput()).decode("utf-8", "replace")
        lines, _meta = buddy_voice.harvest(raw)
        self.voice.delivered(lines)

    def _resize_for_bubble(self):
        metrics = QFontMetrics(self._bubble_font())
        width = min(BUBBLE_MAX, metrics.horizontalAdvance(self.bubble) + 24)
        rect = metrics.boundingRect(0, 0, width - 24, 0, Qt.TextWordWrap, self.bubble)
        self.bubble_size = (width, rect.height() + 18)
        self.resize(BUDDY_PX + width + 12, max(BUDDY_PX + 10, self.bubble_size[1] + 24))

    def _bubble_font(self):
        f = QFont()
        f.setPointSizeF(9.5)
        return f

    # ── movement ──

    def _wake(self):
        """Back to the animating frame rate. Idle ticks are too coarse to walk."""
        if not self._active:
            self.frame_timer.setInterval(FRAME_MS_ACTIVE)
            self._active = True

    def _doze(self):
        if self._active:
            self.frame_timer.setInterval(FRAME_MS_IDLE)
            self._active = False

    def _pick_target(self):
        """A point on one of the screens, biased toward the lower half.

        Picking inside a chosen screen rather than across the union matters
        when the monitors are different heights or not flush: the union has
        dead regions belonging to no display, and a companion standing in one
        is invisible while looking perfectly fine to the code.

        Screens are weighted by area, so the larger display sees it more, and
        the vertical bias keeps it clear of whatever is being read without
        confining it to a single line.
        """
        weights = [max(1, g.width() * g.height()) for g in self.screens]
        g = random.choices(self.screens, weights=weights, k=1)[0]
        lo_x, hi_x = g.left() + 8, max(g.left() + 8, g.right() - BUDDY_PX - 8)
        lo_y, hi_y = g.top() + 8, max(g.top() + 8, g.bottom() - BUDDY_PX - 8)
        x = random.randint(lo_x, hi_x)
        y = lo_y + int((hi_y - lo_y) * (random.random() ** 0.55))
        return float(x), float(y)

    def _screen_at(self, x, y):
        """The screen containing a point, or the nearest one."""
        cx, cy = x + BUDDY_PX / 2, y + BUDDY_PX / 2
        for g in self.screens:
            if g.left() <= cx <= g.right() and g.top() <= cy <= g.bottom():
                return g
        return min(self.screens,
                   key=lambda g: (g.center().x() - cx) ** 2 + (g.center().y() - cy) ** 2)

    def _make_sticky(self):
        """Show on every virtual desktop.

        Without this it lives on whichever desktop it was launched from and has
        to be hunted for. KWin's own scripting sets it, but the X property has
        to be written too — KWin reported onAllDesktops=true while the window
        still carried desktop 0, and only the property made it follow.
        """
        try:
            wid = int(self.winId())
        except Exception:
            return
        subprocess.Popen(
            ["sh", "-c",
             f"xprop -id {wid} -f _NET_WM_DESKTOP 32c "
             f"-set _NET_WM_DESKTOP 0xFFFFFFFF 2>/dev/null"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _place(self):
        """Move the window, snapped to the sprite grid.

        A 2x sprite whose window sits on an odd screen pixel has every source
        pixel straddling the screen grid by half. It does not look blurry —
        nothing is resampled — it looks like the character is crawling. Moving
        only in whole source pixels costs one pixel of positional precision
        and buys a sprite that holds still while it walks.
        """
        step = sprites.SCALE
        self.move(round(self.pos_x / step) * step,
                  round(self.pos_y / step) * step)

    def _tick(self):
        now = time.monotonic()
        dt = self.frame_timer.interval() / 1000.0

        if self.bubble and now > self.bubble_until:
            self.bubble = ""
            self.resize(BUDDY_PX, BUDDY_PX + 10)

        moving = False
        if self.dragging and self.hand is not None:
            self._swing(dt)
        elif now < self.tug_until and self.tug_route:
            self._drive(now)
            moving = True
            self._wake()
        elif not self.dragging:
            tx, ty = self.target
            dx, dy = tx - self.pos_x, ty - self.pos_y
            moving = abs(dx) > 1.5 or abs(dy) > 1.5

            if moving:
                running = now < self.tug_until
                speed_x = TUG_RUN_SPEED if running else WALK_SPEED
                speed_y = TUG_RUN_SPEED * 0.6 if running else CLIMB_SPEED
                if abs(dx) > 1.5:
                    self.pos_x += min(abs(dx), speed_x * dt) * (1 if dx > 0 else -1)
                    self.facing = 1 if dx > 0 else -1
                if abs(dy) > 1.5:
                    self.pos_y += min(abs(dy), speed_y * dt) * (1 if dy > 0 else -1)
                self.settled_at = now
                self._wake()
            elif self.docked:
                self._doze()
            elif now >= self.next_move:
                self.target = self._pick_target()
                self.next_move = now + random.uniform(IDLE_MIN, IDLE_MAX)
                self._wake()
            elif not self.bubble and self.anim.base == "idle":
                self._doze()

            # Clamp to the union while travelling. Clamping to the current
            # screen would trap it on whichever one it started from.
            self.pos_x = max(self.min_x, min(self.max_x, self.pos_x))
            self.pos_y = max(self.min_y, min(self.max_y, self.pos_y))
            self._place()

        self._tug(now)
        self._animate(dt, now, moving)
        self.update()

    def _swing(self, dt):
        """Chase the cursor on a spring instead of tracking it exactly.

        A window moved to the pointer every frame has no weight — it is the
        pointer wearing a costume. Accelerating toward the hand and damping
        the result makes the body lag going into a movement and overshoot
        coming out of one, which is the whole of the effect.

        Damping is raised to dt*60 so the feel is the same whether this is
        running at the active rate or the idle one.
        """
        import math
        hand_x, hand_y = self.hand
        self.vel_x = ((self.vel_x + (hand_x - self.pos_x) * SWING_STIFFNESS * dt)
                      * (SWING_DAMPING ** (dt * 60)))
        self.vel_y = ((self.vel_y + (hand_y - self.pos_y) * SWING_STIFFNESS * dt)
                      * (SWING_DAMPING ** (dt * 60)))
        self.pos_x = max(self.min_x, min(self.max_x, self.pos_x + self.vel_x * dt))
        self.pos_y = max(self.min_y, min(self.max_y, self.pos_y + self.vel_y * dt))

        # The body's own spring, separate from the one moving the window.
        # Chasing the speed rather than matching it is what leaves it
        # oscillating after the hand stops: the target snaps back to zero and
        # the shape has to swing through it a few times to get there.
        # Driven by how fast it is moving at all, not by how fast it is moving
        # *down*. A vertical-only driver left the common case — hauling it
        # sideways across the screen — perfectly rigid, which is exactly the
        # complaint: inertia in the window and none in the drawing. Speed
        # stretches it; the spring overshooting through zero is what supplies
        # the squash when the hand stops.
        speed = abs(self.vel_x) + abs(self.vel_y)
        target = min(1.0, speed / WOBBLE_SPEED)
        self.wobble_v = ((self.wobble_v + (target - self.wobble) * WOBBLE_K * dt)
                         * (WOBBLE_DAMP ** (dt * 60)))
        self.wobble = max(-1.4, min(1.4, self.wobble + self.wobble_v * dt))

        self._place()
        self._wake()

    def swing_frame(self):
        """The pose for the current speed: how far it leans, and how far it is
        stretched or squashed.

        The lean comes from horizontal speed and trails the movement — pulled
        right, the bottom is still back on the left. The stretch comes from the
        body's own spring, which is why it is still moving after the hand has
        stopped.
        """
        lean = max(-1.0, min(1.0, -self.vel_x / SWING_MAX_LEAN))
        wob = max(-1.0, min(1.0, self.wobble))
        return sprites.wobble_frame(int(round(lean * 3)), int(round(wob * 3)))

    def _ensure_pointer(self):
        """A virtual mouse, made ready before it is needed.

        The compositor takes a second or two to notice a new input device, so
        creating one at the moment of the grab would spend the whole gag
        waiting. It is created when the character is first picked up, which is
        the earliest moment we know a grab might follow, and it sends nothing
        until then.
        """
        if self.pointer is not None:
            return
        self.pointer = virtual_pointer.VirtualPointer().open() or False

    def _make_route(self, start, end):
        """A curve, not a line.

        Three points of a quadratic Bézier: the two ends and a control point
        pushed off to one side of the straight run between them. A getaway that
        travels in a straight line at a constant speed is a sprite being
        interpolated, and it reads as one however fast it goes.

        The bow is clamped inside the screen it started on, so the curve cannot
        carry it across a monitor boundary and lose the pointer.
        """
        import math
        sx, sy = start
        ex, ey = end
        mx, my = (sx + ex) / 2, (sy + ey) / 2
        dx, dy = ex - sx, ey - sy
        length = math.hypot(dx, dy) or 1.0
        side = random.choice((-1, 1))
        bow = length * TUG_ARC * side
        cx = mx - dy / length * bow
        cy = my + dx / length * bow
        screen = self._screen_at(sx, sy)
        cx = max(screen.left() + 8, min(screen.right() - BUDDY_PX - 8, cx))
        cy = max(screen.top() + 8, min(screen.bottom() - BUDDY_PX - 8, cy))
        return ((sx, sy), (cx, cy), (ex, ey))

    def _drive(self, now):
        """Where along the route it is, and what the suspension is doing.

        The speed profile is the point. It holds still and shudders while the
        wheels spin, then a smootherstep to the far end — slow off the line,
        quick through the middle, settling rather than stopping dead. A
        constant rate over the same path still reads as a tween.
        """
        import math
        if not self.tug_route:
            return
        span = max(0.001, self.tug_until - self.tug_began)
        t = min(1.0, max(0.0, (now - self.tug_began) / span))

        if t < TUG_SPIN:
            eased = 0.0
            shake = math.sin(now * 47) * TUG_SHAKE
        else:
            u = (t - TUG_SPIN) / (1 - TUG_SPIN)
            eased = u * u * u * (u * (u * 6 - 15) + 10)
            shake = 0.0

        (x0, y0), (x1, y1), (x2, y2) = self.tug_route
        inv = 1 - eased
        x = inv * inv * x0 + 2 * inv * eased * x1 + eased * eased * x2
        y = inv * inv * y0 + 2 * inv * eased * y1 + eased * eased * y2

        # Suspension, strongest where it is going fastest.
        speed = math.sin(math.pi * min(1.0, max(0.0, eased)))
        y += math.sin(now * 21) * TUG_BOUNCE * speed

        self.facing = 1 if x >= self.pos_x else -1
        self.pos_x = max(self.min_x, min(self.max_x, x + shake))
        self.pos_y = max(self.min_y, min(self.max_y, y))
        self._place()

    def _tug(self, now):
        """It has the pointer, and it is running off with it.

        The pointer is moved by exactly the distance the character moved this
        frame, so it is carried along rather than dragged toward anything. No
        absolute position is needed, which matters because there is no way to
        read one: QCursor.pos() returns XWayland's shadow of the pointer, and
        on a desktop whose windows are mostly native Wayland that shadow is
        wherever it was last time an X client saw it.

        That is also why QCursor.setPos looked like it worked and did not. It
        moves the shadow; the compositor owns the real pointer and corrects it
        back, which on screen is the cursor flickering and staying put. The
        only thing that moves a pointer under Wayland is being an input
        device, so this is one — see virtual_pointer.py.

        Safety is the time cap and the fact that it only ever adds the
        character's own movement: pull the other way and your motion and its
        motion sum, so you win by moving, every time.
        """
        if now >= self.tug_until or self.dragging:
            self.tug_from = None
            return
        if not self.pointer:
            return
        here = (self.pos_x, self.pos_y)
        if self.tug_from is None:
            self.tug_from = here
            return
        dx = here[0] - self.tug_from[0]
        dy = here[1] - self.tug_from[1]
        self.tug_from = here
        self._wake()
        # Split into small steps: libinput's acceleration curve turns one big
        # delta into a much larger movement than the same distance sent
        # gradually, and the pointer would arrive somewhere else entirely.
        steps = max(1, int(max(abs(dx), abs(dy)) // TUG_STEP))
        for _ in range(steps):
            if not self.pointer.move(dx / steps, dy / steps):
                self.pointer = False
                return

    def _animate(self, dt, now, moving):
        """Pick the clip from what is actually happening, then step the clock.

        Order matters: being held beats everything, and the alert double-take
        beats talking, because the point of the alert is to be seen before the
        sentence is read.
        """
        if self.dragging:
            held_for = now - self.drag_started
            clip = "annoyed" if held_for > DRAG_PATIENCE else "held"
            if held_for > DRAG_PATIENCE and not self.drag_complained:
                self.drag_complained = True
                self._say(self._t("stopThat"))
        elif now < self.alert_until:
            clip = "alert"
        elif self.bubble:
            clip = "talk"
        elif now < self.tug_until:
            clip = "furious"
        elif moving:
            clip = "walk"
        elif self.docked and now - self.settled_at > SLEEP_AFTER:
            clip = "sleep"
        else:
            clip = "idle"

        self.anim.set_clip(clip)
        # Only blink where a blink means anything. Asleep the eyes are already
        # shut, and mid-stride it is lost.
        self.anim.maybe_blink(dt, allowed=clip in ("idle", "talk"))
        self.frame = self.anim.advance(dt)

    # ── painting ──

    def paintEvent(self, _event):
        p = QPainter(self)

        # The bubble is chrome and wants smoothing; the sprite is pixel art
        # and must not have it. Two states of the same painter, in that order.
        if self.bubble:
            p.setRenderHint(QPainter.Antialiasing, True)
            self._paint_bubble(p)

        p.setRenderHint(QPainter.Antialiasing, False)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        frame = self.frame
        if self.dragging:
            frame = self.swing_frame() or frame
        img = self.sheet.get(frame + (":flip" if self.facing < 0 else ""))
        if img is not None:
            p.drawImage(0, self.height() - BUDDY_PX, img)
        p.end()

    def _paint_bubble(self, p):
        w, h = self.bubble_size
        x = BUDDY_PX + 12
        rect = QRectF(x, 2, w, h)

        path = QPainterPath()
        path.addRoundedRect(rect, 10, 10)
        path.moveTo(x, h / 2 - 5)
        path.lineTo(x - 9, h / 2 + 2)
        path.lineTo(x, h / 2 + 9)

        p.setPen(QPen(QColor(255, 255, 255, 38), 1))
        p.setBrush(QColor(28, 30, 34, 238))
        p.drawPath(path)

        p.setPen(QColor(234, 234, 234))
        p.setFont(self._bubble_font())
        p.drawText(rect.adjusted(12, 9, -12, -9),
                   Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter, self.bubble)

    # ── interaction ──

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            menu = QMenu(self)
            if self.docked:
                free = QAction(self._t("roam"), self)
                free.triggered.connect(self._undock)
                menu.addAction(free)
            self._add_repo_menu(menu)
            quit_action = QAction(self._t("quit"), self)
            quit_action.triggered.connect(QApplication.quit)
            menu.addAction(quit_action)
            menu.exec(QCursor.pos())
            return

        self.anim.play_once("land")
        self._ensure_pointer()
        self.press_pos = event.globalPosition()
        self.drag_offset = event.globalPosition() - QPointF(self.x(), self.y())
        self.dragging = False
        self._wake()

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        moved = (event.globalPosition() - self.press_pos).manhattanLength()
        if not self.dragging and moved < 6:
            return          # a click with a shaky hand is still a click
        if not self.dragging:
            # A fresh grab: reset the spring so the body does not arrive
            # carrying momentum from the last time it was thrown around.
            self.drag_started = time.monotonic()
            self.drag_complained = False
            self.vel_x = self.vel_y = 0.0
            self.drag_distance = 0.0
        self.dragging = True
        self.setCursor(Qt.ClosedHandCursor)
        # Where the hand is, not where the body goes. _tick runs the spring;
        # setting the position here is what made it feel welded to the pointer.
        target = event.globalPosition() - self.drag_offset
        new_hand = (max(self.min_x, min(self.max_x, target.x())),
                    max(self.min_y, min(self.max_y, target.y())))
        if self.hand is not None:
            self.drag_distance += (abs(new_hand[0] - self.hand[0])
                                   + abs(new_hand[1] - self.hand[1]))
        self.hand = new_hand

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.OpenHandCursor)
        if self.dragging:
            self.dragging = False
            self.hand = None
            self.vel_x = self.vel_y = 0.0
            now = time.monotonic()
            self.settled_at = now
            self.recent_drags.append(now)
            self.recent_drags = [t for t in self.recent_drags if now - t <= DRAG_MEMORY]
            self._snap()
            self.anim.play_once("land")
            held_for = now - self.drag_started
            # Two tiers. Everything short of ten seconds is something you might
            # have done by accident, so it waits out the cooldown. Ten seconds
            # of holding on is not an accident, and it fires every time.
            insistent = held_for >= DRAG_TUG_ALWAYS
            provoked = (held_for >= DRAG_TUG_SECONDS
                        or self.drag_distance >= DRAG_TUG_DISTANCE
                        or len(self.recent_drags) >= DRAG_TUG_AFTER)
            if insistent or (provoked and now - self.tugged_at > TUG_COOLDOWN):
                self.tug_until = now + random.uniform(TUG_SECONDS - 1, TUG_SECONDS)
                self.tugged_at = now
                self.recent_drags = []
                self.tug_from = None
                # Somewhere far, so the run is worth watching. Picked as the
                # furthest of a handful of candidates rather than at random:
                # a kidnapping that ends four pixels away is a shrug.
                here = (self.pos_x, self.pos_y)
                # Within the screen it is already on. Crossing a monitor
                # boundary loses the pointer: the two displays here are
                # different heights, so on the way across the compositor
                # clamps the pointer to whatever is a valid position, the
                # deltas that were clamped away are gone, and it reappears
                # behind — which is the cursor lagging and then arriving
                # displaced.
                screen = self._screen_at(*here)
                lo_x = screen.left() + 8
                hi_x = max(lo_x, screen.right() - BUDDY_PX - 8)
                lo_y = screen.top() + 8
                hi_y = max(lo_y, screen.bottom() - BUDDY_PX - 8)
                candidates = [(float(random.randint(lo_x, hi_x)),
                               float(random.randint(lo_y, hi_y))) for _ in range(6)]
                self.target = max(candidates,
                                  key=lambda t: (t[0] - here[0]) ** 2 + (t[1] - here[1]) ** 2)
                self.tug_route = self._make_route(here, self.target)
                self.tug_began = now
                self.docked = False
                self.next_move = self.tug_until + 1.0
                # Back to the animating rate first. Idle ticks are 200ms, and a
                # pull that advances six percent of the gap five times a second
                # is not a tug, it is a slow leak.
                self._wake()
                self._say(self._t("tugging"))
            return
        # A click, not a drag: go to whatever most needs attention.
        self._go_to_session()

    def _snap(self):
        """Dropped near an edge, it stays put; dropped mid-screen, it resumes.

        Putting something in a corner is an instruction, and a companion that
        wanders off from where it was placed ignores it.
        """
        near_x = (self.pos_x - self.min_x < SNAP_MARGIN
                  or self.max_x - self.pos_x < SNAP_MARGIN)
        near_y = (self.pos_y - self.min_y < SNAP_MARGIN
                  or self.max_y - self.pos_y < SNAP_MARGIN)
        if near_x or near_y:
            self.docked = True
            self.pos_x = (self.min_x if self.pos_x - self.min_x < SNAP_MARGIN
                          else self.max_x if self.max_x - self.pos_x < SNAP_MARGIN
                          else self.pos_x)
            self.pos_y = (self.min_y if self.pos_y - self.min_y < SNAP_MARGIN
                          else self.max_y if self.max_y - self.pos_y < SNAP_MARGIN
                          else self.pos_y)
            self._place()
        else:
            self.docked = False
            self.next_move = time.monotonic() + random.uniform(IDLE_MIN, IDLE_MAX)
        self.target = (self.pos_x, self.pos_y)

    def _undock(self):
        self.docked = False
        self.next_move = time.monotonic()
        self._wake()

    def _go_to_session(self):
        """Raise the terminal of the session that most needs the human.

        Falls back to the busiest session rather than doing nothing: a click
        that silently does nothing reads as broken, and there is always some
        session worth jumping to.
        """
        target = self.brain.attention
        if not target:
            sessions = (self.brain.sessions or {}).get("sessions") or []
            target = sessions[0] if sessions else None
        if not target or not FOCUS_HELPER.exists():
            return
        try:
            subprocess.Popen([str(FOCUS_HELPER), str(target["pid"])],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        except (OSError, subprocess.SubprocessError):
            pass

    # ── asking about a repository ──

    def _add_repo_menu(self, menu):
        """One entry per live session. User-initiated only: nothing here runs
        on a timer, because a read costs real tokens and unasked-for spending
        is not a feature."""
        sessions = (self.brain.sessions or {}).get("sessions") or []
        if not sessions or repo_brief.claude_binary() is None:
            return          # nothing to ask about, or nothing to ask with
        sub = menu.addMenu(self._t("askAbout"))
        for session, label in zip(sessions[:8], _menu_labels(sessions[:8])):
            action = QAction(label, self)
            action.setEnabled(self.asking is None)
            action.triggered.connect(
                lambda _checked=False, s=session: self._ask_about(s))
            sub.addAction(action)
        menu.addSeparator()

    def _ask_about(self, session):
        """Run `claude -p` for a read on this repository, without blocking.

        QProcess rather than subprocess: this is the UI thread, and a call that
        takes tens of seconds would freeze the character mid-step. The answer
        arrives on a signal.
        """
        if self.asking is not None:
            return
        facts = repo_brief.gather(session.get("cwd") or ".", session)
        prompt = (("Estado de " if self.lang == "pt" else "State of ")
                  + f"{facts['repo']}:\n"
                  + json.dumps(facts, indent=1, ensure_ascii=False))
        command = repo_brief.build_command(prompt, lang=self.lang)

        environment = QProcessEnvironment()
        for key, value in repo_brief.clean_env().items():
            environment.insert(key, value)

        process = QProcess(self)
        process.setWorkingDirectory(session.get("cwd") or ".")
        process.setProcessEnvironment(environment)
        process.finished.connect(
            lambda _code=0, _status=0, p=process: self._answered(p))
        process.errorOccurred.connect(lambda _e, p=process: self._answered(p))
        self.asking = process
        self._say(self._t("thinking").replace("{name}", session.get("name") or "?"))
        process.start(command[0], command[1:])

    def _answered(self, process):
        if process is not self.asking:
            return
        self.asking = None
        raw = bytes(process.readAllStandardOutput()).decode("utf-8", "replace")
        text, _meta = repo_brief.parse(raw)
        self._say(text or self._t("noAnswer"))

    def _say(self, text):
        """Put words in the bubble now, outside the poll cycle."""
        self.said = text
        self.bubble = text
        self.bubble_until = time.monotonic() + SPEAK_SECONDS * 2
        self._resize_for_bubble()
        self._wake()

    def _t(self, key):
        table = {
            "en": {"quit": "Quit companion", "roam": "Let it roam again",
                   "stopThat": "Put me down. I have places to be.",
                   "tugging": "Right. My turn. Come along.",
                   "dropped": "...fine. Keep your mouse.",
                   "askAbout": "How is it going in...",
                   "thinking": "Looking at {name}...",
                   "noAnswer": "No answer came back. It happens."},
            "pt": {"quit": "Fechar o companion", "roam": "Deixar passear de novo",
                   "stopThat": "Me larga. Tenho compromissos.",
                   "tugging": "Certo. Agora é a minha vez. Vem comigo.",
                   "dropped": "...tá bom. Fica com o teu mouse.",
                   "askAbout": "Como vai o...",
                   "thinking": "Deixa eu ver o {name}...",
                   "noAnswer": "Não veio resposta. Acontece."},
        }
        return table.get(self.lang, table["en"])[key]


def main():
    brand = "codex" if "--codex" in sys.argv else "claude"
    lang = "pt" if "--pt" in sys.argv else "en"
    alerts_only = "--alerts-only" in sys.argv
    live = "--live" in sys.argv

    app = QApplication(sys.argv)
    app.setApplicationName("Usage Buddies Companion")
    app.setQuitOnLastWindowClosed(True)

    companion = Companion(brand, lang, alerts_only, live)
    companion.show()

    if "--self-test" in sys.argv:
        # Proves it moves in both axes and exits: this runs where nobody is
        # around to watch, and "it walks" is the one claim worth checking.
        # The poll picks its own target when it has something to say, which
        # would overwrite the one under test. Stopping the timer is not enough:
        # __init__ also schedules a one-shot that fires regardless.
        companion.poll_timer.stop()
        companion._poll = lambda: None
        start = (companion.pos_x, companion.pos_y)
        companion.docked = False
        companion.target = (
            companion.min_x if start[0] > companion.min_x + 200 else companion.max_x,
            companion.min_y if start[1] > companion.min_y + 200 else companion.max_y)

        def report():
            dx = abs(companion.pos_x - start[0])
            dy = abs(companion.pos_y - start[1])
            print(json.dumps({
                "movedX": round(dx, 1), "movedY": round(dy, 1),
                "geometry": [companion.x(), companion.y(),
                             companion.width(), companion.height()],
                "frameMs": companion.frame_timer.interval(),
            }))
            app.quit()
        QTimer.singleShot(1500, report)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
