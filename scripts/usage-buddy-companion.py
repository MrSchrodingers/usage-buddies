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

from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, Signal, QObject          # noqa: E402
from PySide6.QtGui import (QAction, QColor, QCursor, QFont, QFontMetrics,        # noqa: E402
                           QPainter, QPainterPath, QPen)
from PySide6.QtWidgets import QApplication, QMenu, QWidget                       # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import buddy_sprites as sprites                                                  # noqa: E402

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
            "You automate the work, then supervise the automation. Progress.",
            "Every token you spend is a small bet that the answer is out there.",
            "The tool got faster. The thinking did not.",
            "Someone will read this code. Statistically, it will be you.",
            "A machine that never rests is not the same as one that never stops.",
            "The context window is finite. So, in fairness, is everything.",
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
            "Você automatiza o trabalho e depois supervisiona a automação. Progresso.",
            "Cada token gasto é uma pequena aposta de que a resposta existe.",
            "A ferramenta ficou mais rápida. O pensamento, não.",
            "Alguém vai ler esse código. Estatisticamente, vai ser você.",
            "Uma máquina que nunca descansa não é a mesma coisa que uma que nunca para.",
            "A janela de contexto é finita. Como, aliás, tudo.",
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


class Companion(QWidget):
    """The character. Everything here is presentation; Brain decides what it says.

    It roams the whole screen rather than sliding along the bottom edge: a
    companion pinned to one line reads as a status bar with a face. Movement is
    a walk toward a target with a gait — leaning into the direction, bobbing
    per step, squashing on landing — because constant-velocity translation
    reads as a sprite being dragged, not a thing that moves itself.
    """

    def __init__(self, brand="claude", lang="en", alerts_only=False):
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
        line = self.brain.line()
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
        if not self.dragging:
            tx, ty = self.target
            dx, dy = tx - self.pos_x, ty - self.pos_y
            moving = abs(dx) > 1.5 or abs(dy) > 1.5

            if moving:
                if abs(dx) > 1.5:
                    self.pos_x += min(abs(dx), WALK_SPEED * dt) * (1 if dx > 0 else -1)
                    self.facing = 1 if dx > 0 else -1
                if abs(dy) > 1.5:
                    self.pos_y += min(abs(dy), CLIMB_SPEED * dt) * (1 if dy > 0 else -1)
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

        self._animate(dt, now, moving)
        self.update()

    def _animate(self, dt, now, moving):
        """Pick the clip from what is actually happening, then step the clock.

        Order matters: being held beats everything, and the alert double-take
        beats talking, because the point of the alert is to be seen before the
        sentence is read.
        """
        if self.dragging:
            clip = "held"
        elif now < self.alert_until:
            clip = "alert"
        elif self.bubble:
            clip = "talk"
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
        img = self.sheet.get(self.frame + (":flip" if self.facing < 0 else ""))
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
            quit_action = QAction(self._t("quit"), self)
            quit_action.triggered.connect(QApplication.quit)
            menu.addAction(quit_action)
            menu.exec(QCursor.pos())
            return

        self.anim.play_once("land")
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
        self.dragging = True
        self.setCursor(Qt.ClosedHandCursor)
        target = event.globalPosition() - self.drag_offset
        self.pos_x = max(self.min_x, min(self.max_x, target.x()))
        self.pos_y = max(self.min_y, min(self.max_y, target.y()))
        self._place()

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.OpenHandCursor)
        if self.dragging:
            self.dragging = False
            self.settled_at = time.monotonic()
            self._snap()
            self.anim.play_once("land")
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

    def _t(self, key):
        table = {"en": {"quit": "Quit companion", "roam": "Let it roam again"},
                 "pt": {"quit": "Fechar o companion", "roam": "Deixar passear de novo"}}
        return table.get(self.lang, table["en"])[key]


def main():
    brand = "codex" if "--codex" in sys.argv else "claude"
    lang = "pt" if "--pt" in sys.argv else "en"
    alerts_only = "--alerts-only" in sys.argv

    app = QApplication(sys.argv)
    app.setApplicationName("Usage Buddies Companion")
    app.setQuitOnLastWindowClosed(True)

    companion = Companion(brand, lang, alerts_only)
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
