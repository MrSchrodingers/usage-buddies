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
from PySide6.QtSvg import QSvgRenderer                                           # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu, QWidget                       # noqa: E402

CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "usage-buddies"
SESSIONS_FILE = CACHE / "sessions.json"
WIDGET_DATA = Path.home() / ".claude" / "widget-data.json"
ICONS = Path(__file__).resolve().parent.parent / "plasmoid" / "contents" / "icons"
INSTALLED_ICONS = (Path.home() / ".local/share/plasma/plasmoids"
                   / "org.kde.plasma.usagebuddies/contents/icons")
FOCUS_HELPER = Path.home() / ".local" / "bin" / "focus-session.sh"

BUDDY_PX = 56
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
CLICK_ANIM = 0.45        # squash-and-stretch, seconds
SNAP_MARGIN = 26         # how close to an edge a drop counts as "put me here"


LINES = {
    "en": {
        "asking":     ["{name} asked you something and is just sitting there.",
                       "{name} needs a decision. It will wait forever — that is the problem."],
        "waiting":    ["{name} finished. Go look before you forget it existed.",
                       "{name} is done and idling. Your move.",
                       "{name} wrapped up {idle} ago. Still waiting."],
        "idle":       ["{name} has done nothing for {idle}. Existential, really.",
                       "{name} is idle. Contemplating the void, presumably."],
        "twoRed":     ["Two quotas in the red. This is fine."],
        "compaction": ["{n} compactions today. You keep forgetting things and calling it progress."],
        "readRatio":  ["{n}:1 read per output. Reading a library to write a postcard."],
        "bashHeavy":  ["{n}% of your calls are Bash. There are other tools. Allegedly."],
        "cacheDrop":  ["Cache hit down to {n}%. Something is invalidating the prefix."],
        "nightOwl":   ["It is late. The commit will still be broken tomorrow."],
    },
    "pt": {
        "asking":     ["{name} te perguntou algo e está lá, parado.",
                       "{name} precisa de uma decisão. Ele espera pra sempre — esse é o problema."],
        "waiting":    ["{name} terminou. Vai lá conferir antes de esquecer que existe.",
                       "{name} acabou e está de bobeira. É sua vez.",
                       "{name} fechou há {idle}. Continua esperando."],
        "idle":       ["{name} não faz nada há {idle}. Existencial, no fundo.",
                       "{name} está ocioso. Contemplando o vazio, presumo."],
        "twoRed":     ["Duas cotas no vermelho. This is fine."],
        "compaction": ["{n} compactações hoje. Você esquece tudo e chama de progresso."],
        "readRatio":  ["{n}:1 de leitura por saída. Lendo uma biblioteca pra escrever um bilhete."],
        "bashHeavy":  ["{n}% das suas chamadas são Bash. Existem outras ferramentas. Dizem."],
        "cacheDrop":  ["Cache caiu pra {n}%. Alguma coisa está invalidando o prefixo."],
        "nightOwl":   ["Tá tarde. O commit vai continuar quebrado amanhã."],
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
    """Decides what is worth saying, in the same order the widget uses."""

    def __init__(self, lang="en", alerts_only=False):
        super().__init__()
        self.lang = lang if lang in LINES else "en"
        self.alerts_only = alerts_only
        self.sessions = {}
        self.usage = {}

    def refresh(self):
        self.sessions = _read_json(SESSIONS_FILE)
        self.usage = _read_json(WIDGET_DATA)

    @property
    def attention(self):
        return (self.sessions or {}).get("attention")

    def _pick(self, key, **vars_):
        table = LINES[self.lang].get(key) or []
        if not table:
            return None
        text = random.choice(table)
        for k, v in vars_.items():
            text = text.replace("{" + k + "}", str(v))
        return text

    def line(self):
        """The current thing worth saying, or None. Silence is the default."""
        a = self.attention
        if a and a.get("state") == "asking":
            return self._pick("asking", name=a.get("name", "?"))
        if a and a.get("state") == "waiting":
            return self._pick("waiting", name=a.get("name", "?"),
                              idle=_fmt_idle(a.get("idleSeconds", 0)))

        idle = [s for s in (self.sessions.get("sessions") or [])
                if s.get("state") == "idle"]
        if idle:
            return self._pick("idle", name=idle[0].get("name", "?"),
                              idle=_fmt_idle(idle[0].get("idleSeconds", 0)))

        if self.alerts_only:
            return None

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

        if 0 <= time.localtime().tm_hour < 5:
            return self._pick("nightOwl")
        return None


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

        icon_dir = INSTALLED_ICONS if INSTALLED_ICONS.is_dir() else ICONS
        svg = icon_dir / ("rex.svg" if brand == "codex" else "clawd.svg")
        self.renderer = QSvgRenderer(str(svg)) if svg.exists() else None

        self.brain = Brain(lang, alerts_only)
        self.lang = lang
        self.bubble = ""
        self.bubble_until = 0.0
        self.said = ""
        self.bubble_size = (0, 0)

        screen = QApplication.primaryScreen().availableGeometry()
        self.bounds = screen
        self.min_x = screen.left() + 8
        self.max_x = screen.right() - BUDDY_PX - 8
        self.min_y = screen.top() + 8
        self.max_y = screen.bottom() - BUDDY_PX - 8

        self.pos_x = float(random.randint(self.min_x, self.max_x))
        self.pos_y = float(self.max_y)
        self.target = (self.pos_x, self.pos_y)
        self.facing = 1
        self.step_phase = 0.0
        self.click_at = 0.0
        self.next_move = time.monotonic() + random.uniform(IDLE_MIN, IDLE_MAX)

        # Drag state. `docked` survives a drop near an edge: put down in a
        # corner, it stays there instead of wandering off, because that is what
        # putting something in a corner means.
        self.dragging = False
        self.drag_offset = QPointF(0, 0)
        self.docked = False

        self.resize(BUDDY_PX, BUDDY_PX)
        self.move(int(self.pos_x), int(self.pos_y))

        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self._tick)
        self.frame_timer.start(FRAME_MS_ACTIVE)
        self._active = True

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll)
        self.poll_timer.start(POLL_MS)
        QTimer.singleShot(200, self._poll)

    # ── what it says ──

    def _poll(self):
        self.brain.refresh()
        line = self.brain.line()
        if line and line != self.said:
            self.said = line
            self.bubble = line
            self.bubble_until = time.monotonic() + SPEAK_SECONDS
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
        """Anywhere on screen, biased toward the lower half.

        Uniform placement puts it over whatever is being read as often as not;
        weighting downward keeps it out of the way without confining it to one
        line.
        """
        x = random.randint(self.min_x, self.max_x)
        span = self.max_y - self.min_y
        y = self.min_y + int(span * (random.random() ** 0.55))
        return float(x), float(y)

    def _tick(self):
        now = time.monotonic()
        dt = self.frame_timer.interval() / 1000.0

        if self.bubble and now > self.bubble_until:
            self.bubble = ""
            self.resize(BUDDY_PX, BUDDY_PX + 10)

        if self.dragging:
            self.update()
            return

        tx, ty = self.target
        dx, dy = tx - self.pos_x, ty - self.pos_y
        moving = abs(dx) > 1.5 or abs(dy) > 1.5

        if moving:
            step_x = min(abs(dx), WALK_SPEED * dt)
            step_y = min(abs(dy), CLIMB_SPEED * dt)
            if abs(dx) > 1.5:
                self.pos_x += step_x * (1 if dx > 0 else -1)
                self.facing = 1 if dx > 0 else -1
            if abs(dy) > 1.5:
                self.pos_y += step_y * (1 if dy > 0 else -1)
            self.step_phase += dt * 9.0
            self._wake()
        else:
            self.step_phase += dt * 1.6
            if self.docked:
                self._doze()
            elif now >= self.next_move:
                self.target = self._pick_target()
                self.next_move = now + random.uniform(IDLE_MIN, IDLE_MAX)
                self._wake()
            elif not self.bubble and now - self.click_at > CLICK_ANIM:
                self._doze()

        self.pos_x = max(self.min_x, min(self.max_x, self.pos_x))
        self.pos_y = max(self.min_y, min(self.max_y, self.pos_y))
        self.move(int(self.pos_x), int(self.pos_y))
        self.update()

    # ── painting ──

    def paintEvent(self, _event):
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        tx, ty = self.target
        moving = (abs(tx - self.pos_x) > 1.5 or abs(ty - self.pos_y) > 1.5) and not self.dragging

        # Gait. Two bobs per stride and a slight lean into the direction of
        # travel; standing still it breathes instead.
        bob = math.sin(self.step_phase * 2) * (3.4 if moving else 1.4)
        lean = math.sin(self.step_phase) * (0.09 if moving else 0.0)

        # Squash and stretch on click: down fast, back slowly.
        squash = 1.0
        since = time.monotonic() - self.click_at
        if since < CLICK_ANIM:
            t = since / CLICK_ANIM
            squash = 1.0 - 0.28 * math.sin(math.pi * t) * (1.0 - t * 0.4)

        if self.dragging:
            # Held: hangs and swings a little.
            bob = math.sin(self.step_phase * 3) * 2.0
            lean = math.sin(self.step_phase * 3) * 0.14

        if self.bubble:
            self._paint_bubble(p)

        if self.renderer:
            h = BUDDY_PX * squash
            w = BUDDY_PX / max(0.7, squash) ** 0.5
            x = (BUDDY_PX - w) / 2
            y = self.height() - h + bob
            p.save()
            p.translate(x + w / 2, y + h)
            p.rotate(lean * 57.3)
            if self.facing < 0:
                p.scale(-1, 1)
            self.renderer.render(p, QRectF(-w / 2, -h, w, h))
            p.restore()
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

        self.click_at = time.monotonic()
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
        self.move(int(self.pos_x), int(self.pos_y))

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.OpenHandCursor)
        if self.dragging:
            self.dragging = False
            self._snap()
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
            self.move(int(self.pos_x), int(self.pos_y))
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
