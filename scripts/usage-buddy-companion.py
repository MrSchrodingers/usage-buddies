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
FRAME_MS = 33            # ~30fps; enough for a pixel-art walk, cheap enough to ignore
WALK_SPEED = 42.0        # pixels per second
IDLE_MIN, IDLE_MAX = 6.0, 22.0
SPEAK_SECONDS = 14.0


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
    def __init__(self, brand="claude", lang="en", alerts_only=False):
        super().__init__(None)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus | Qt.BypassWindowManagerHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)

        icon_dir = INSTALLED_ICONS if INSTALLED_ICONS.is_dir() else ICONS
        svg = icon_dir / ("rex.svg" if brand == "codex" else "clawd.svg")
        self.renderer = QSvgRenderer(str(svg)) if svg.exists() else None

        self.brain = Brain(lang, alerts_only)
        self.bubble = ""
        self.bubble_until = 0.0
        self.said = ""

        screen = QApplication.primaryScreen().availableGeometry()
        self.floor = screen.bottom() - BUDDY_PX - 8
        self.min_x, self.max_x = screen.left() + 8, screen.right() - BUDDY_PX - 8
        self.x_pos = float(random.randint(self.min_x, self.max_x))
        self.target_x = self.x_pos
        self.facing = 1
        self.bob_phase = 0.0
        self.next_move = time.monotonic() + random.uniform(IDLE_MIN, IDLE_MAX)

        self.resize(BUDDY_PX, BUDDY_PX)
        self.move(int(self.x_pos), self.floor)

        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self._tick)
        self.frame_timer.start(FRAME_MS)

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll)
        self.poll_timer.start(POLL_MS)
        QTimer.singleShot(200, self._poll)

    # ── behaviour ──

    def _poll(self):
        self.brain.refresh()
        line = self.brain.line()
        if line and line != self.said:
            self.said = line
            self.bubble = line
            self.bubble_until = time.monotonic() + SPEAK_SECONDS
            # Walk toward the middle when it has something to say, so the
            # bubble is not clipped against a screen edge.
            centre = (self.min_x + self.max_x) / 2
            self.target_x = centre + random.uniform(-120, 120)
            self._resize_for_bubble()
        elif not line:
            self.said = ""

    def _resize_for_bubble(self):
        metrics = QFontMetrics(self._bubble_font())
        width = min(BUBBLE_MAX, metrics.horizontalAdvance(self.bubble) + 24)
        rect = metrics.boundingRect(0, 0, width - 24, 0, Qt.TextWordWrap, self.bubble)
        self.bubble_size = (width, rect.height() + 18)
        self.resize(BUDDY_PX + width + 10, max(BUDDY_PX, self.bubble_size[1] + 20))

    def _bubble_font(self):
        f = QFont()
        f.setPointSizeF(9.5)
        return f

    def _tick(self):
        now = time.monotonic()

        if self.bubble and now > self.bubble_until:
            self.bubble = ""
            self.resize(BUDDY_PX, BUDDY_PX)

        # Wander: pick a new destination now and then, walk to it, idle.
        if abs(self.target_x - self.x_pos) < 2:
            if now >= self.next_move:
                self.target_x = float(random.randint(self.min_x, self.max_x))
                self.next_move = now + random.uniform(IDLE_MIN, IDLE_MAX)
        else:
            step = WALK_SPEED * (FRAME_MS / 1000.0)
            direction = 1 if self.target_x > self.x_pos else -1
            self.facing = direction
            self.x_pos += step * direction
            self.x_pos = max(self.min_x, min(self.max_x, self.x_pos))

        self.bob_phase += 0.12 if abs(self.target_x - self.x_pos) >= 2 else 0.04
        self.move(int(self.x_pos), self.floor)
        self.update()

    # ── painting ──

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        walking = abs(self.target_x - self.x_pos) >= 2
        amplitude = 3.0 if walking else 1.6
        import math
        bob = math.sin(self.bob_phase) * amplitude
        y = self.height() - BUDDY_PX + bob

        if self.bubble:
            self._paint_bubble(p)

        if self.renderer:
            p.save()
            if self.facing < 0:
                p.translate(BUDDY_PX, 0)
                p.scale(-1, 1)
            self.renderer.render(p, QRectF(0, y, BUDDY_PX, BUDDY_PX))
            p.restore()
        p.end()

    def _paint_bubble(self, p):
        w, h = self.bubble_size
        x = BUDDY_PX + 10
        rect = QRectF(x, 0, w, h)

        path = QPainterPath()
        path.addRoundedRect(rect, 10, 10)
        # Tail toward the buddy.
        path.moveTo(x, h / 2 - 6)
        path.lineTo(x - 8, h / 2)
        path.lineTo(x, h / 2 + 6)

        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(QColor(28, 30, 34, 235))
        p.drawPath(path)

        p.setPen(QColor(232, 232, 232))
        p.setFont(self._bubble_font())
        p.drawText(rect.adjusted(12, 9, -12, -9),
                   Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter, self.bubble)

    # ── interaction ──

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            menu = QMenu(self)
            quit_action = QAction("Quit companion", self)
            quit_action.triggered.connect(QApplication.quit)
            menu.addAction(quit_action)
            menu.exec(QCursor.pos())
            return

        # Left click on a line about a session goes to that session.
        a = self.brain.attention
        if a and FOCUS_HELPER.exists():
            try:
                subprocess.Popen([str(FOCUS_HELPER), str(a["pid"])],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
            except (OSError, subprocess.SubprocessError):
                pass


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
        # Prove it moves, then exit: this runs in CI and on a headless check
        # where nobody is around to look at it.
        start = companion.x_pos
        companion.target_x = companion.min_x if start > companion.min_x + 100 else companion.max_x
        def report():
            moved = abs(companion.x_pos - start)
            print(json.dumps({"moved": round(moved, 1),
                              "geometry": [companion.x(), companion.y(),
                                           companion.width(), companion.height()]}))
            app.quit()
        QTimer.singleShot(1500, report)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
