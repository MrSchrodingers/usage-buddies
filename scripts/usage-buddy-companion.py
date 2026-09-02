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

import argparse
import json
import os
import random
import subprocess
import sys
import time
from collections import namedtuple
from datetime import datetime, timezone
from pathlib import Path

# Must be set before QtGui is imported, or the platform is already chosen.
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from PySide6.QtCore import (Qt, QTimer, QPointF, QRectF, QObject,               # noqa: E402
                            QFileSystemWatcher, QProcess, QProcessEnvironment)
from PySide6.QtGui import (QAction, QColor, QCursor, QFont, QFontMetrics,        # noqa: E402
                           QPainter, QPainterPath, QPen)
from PySide6.QtWidgets import QApplication, QMenu, QWidget                       # noqa: E402

# QtDBus is a separate module in some PySide6 packagings, and the whole of it
# is optional here: without it the focus block loses its notification
# inhibition and keeps everything else. An ImportError at module scope would
# instead cost the companion entirely.
try:                                                                             # noqa: E402
    from PySide6.QtDBus import QDBusConnection, QDBusInterface
except ImportError:                                                              # pragma: no cover
    QDBusConnection = QDBusInterface = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
import buddy_sprites as sprites                                                  # noqa: E402
import repo_brief                                                                # noqa: E402
import buddy_voice                                                               # noqa: E402
import buddy_signals as signals                                                  # noqa: E402
import buddy_focus as focus_engine                                               # noqa: E402
import buddy_actions as actions                                                  # noqa: E402
import buddy_peers as peers                                                      # noqa: E402
import buddy_hoop                                                                # noqa: E402
from buddy_lines import LINES                                                    # noqa: E402
import virtual_pointer                                                           # noqa: E402

CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "usage-buddies"
SESSIONS_FILE = CACHE / "sessions.json"
# Written by the widget, read here. See CommandChannel below for why it carries
# a timestamp and why it is replaced by a rename rather than written in place.
COMMAND_FILE = CACHE / "companion-command.json"
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
# Seconds since the last keystroke below which a remark is an interruption
# rather than a remark. Short on purpose: the poll runs every twenty seconds,
# so this only ever catches a reading taken while the hands are actually on
# the keys. A wide window would silence a companion belonging to anyone who
# types in bursts, which is everyone, and a mute mascot looks exactly like a
# broken one.
TYPING_SECONDS = 5.0
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

# Being thrown, and the basket offered instead of retaliating for it. The
# arithmetic of both is buddy_hoop's; what lives here is the drawing, the
# window it goes in, and the frame clock they are stepped on.
#
# The scale is the sprite's, and it is passed to the drawing rather than left
# to each side to assume. buddy_hoop.rim_width() converts HOOP_RIM with
# buddy_sprites.SCALE, so a window drawn at any other scale is one size to look
# at and another size to hit — the hit area at half the drawing's width is not
# a visible bug, it is a basket that merely feels impossible.
HOOP_SCALE = sprites.SCALE
# The frame the basket rests on between the one-shots. Named once, because it
# is both what is drawn when it appears and what the score clip returns to.
HOOP_RESTING = "hoop_hang"
# How long the run at the pointer may take before the getaway starts anyway.
# The character has just been let go of, so the cursor is normally within a
# sprite or two of it and the leg is over in a few frames; the ceiling is for
# the case where it is not, and it is there so the getaway cannot be lost by
# a run that never arrives.
CHASE_SECONDS = 3.0

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

# Insistence. How long a gesture is held, and how long the pointer is carried
# for. The carry is shorter than the drag retaliation's: that one is a joke and
# wants to be watched, this one is a summons and wants to be over.
INSIST_GESTURE_SECONDS = 4.0
INSIST_TUG_SECONDS = 3.0

# The focus block's readout, drawn inside the character's own square. Deliberate:
# the window's size and position carry the docking, the side the bubble opens on
# and the pointer carry, and a strip added above the sprite would move all three.
FOCUS_BAR_H = 4
FOCUS_BAR_INSET = 5

# Clips the art may not have yet. The poses for focus and insistence are drawn
# separately from this code, and buddy_sprites.Animator looks its clip up in
# CLIPS on every frame — so naming one that has not landed raises inside the
# frame timer and takes the companion down for good. Names are resolved through
# clip_or_fallback, which means the art starts being used the moment it exists
# and nothing breaks while it does not.
CLIP_FALLBACK = {
    "sit": "idle",
    "wave": "alert",
    "point": "alert",
    "panic": "furious",
    "celebrate": "alert",
    "nod": "idle",
    "shake": "idle",
    "yawn": "sleep",
    "peek": "idle",
    "turn": "idle",
    "type": "idle",
}


def clip_or_fallback(name, default="idle"):
    """`name` if the sheet has it, otherwise the closest clip that exists."""
    if name in sprites.CLIPS:
        return name
    alternative = CLIP_FALLBACK.get(name)
    if alternative in sprites.CLIPS:
        return alternative
    return default if default in sprites.CLIPS else next(iter(sprites.CLIPS))


# How long a mood clip holds the sprite after a line that earned one. The same
# length as the insistence gesture: long enough to be read next to the sentence
# that caused it, short enough that the character is not still panicking while
# the bubble is halfway through its sixteen seconds.
MOOD_SECONDS = 4.0

# Which lines are delivered in a panic, taken off buddy_signals' own priority
# table rather than listed here. Everything from twoRed to creditsLow is the
# band that means the ability to keep working is about to end; a list of keys
# in this file would be one more place to forget when a signal joins that band,
# which is how twoRed spent its whole life written and unreachable.
PANIC_BAND = (signals.PRIORITY["twoRed"], signals.PRIORITY["creditsLow"])

# And the one signal that means a session finished and left nothing running.
CELEBRATE_KEY = "allQuiet"

# The shortest gap between two turn-around one-shots. The facing is recomputed
# every frame while the getaway drives, and a route that doubles back flips it
# repeatedly; without a floor the turn would replay on every flip.
TURN_MIN_GAP = 1.0

# Where one companion stands to talk to another: a sprite of clear air between
# them, so neither is drawn on top of the other.
MEET_GAP = BUDDY_PX + 12

# Why a refused drop gets a sentence. A drop that is rejected in silence is
# indistinguishable from one the character never noticed, and the person tries
# again with the same folder. The keys are buddy_actions' seven reasons; the
# wording lives in _t with the rest of the chrome.
DROP_REASON_LINE = {
    actions.REASON_NOT_LOCAL: "dropNotLocal",
    actions.REASON_UNSAFE: "dropUnsafe",
    actions.REASON_MISSING: "dropMissing",
    actions.REASON_NOT_A_FOLDER: "dropNotAFolder",
    actions.REASON_NOT_A_REPOSITORY: "dropNotARepo",
    actions.REASON_UNREADABLE: "dropUnreadable",
    actions.REASON_TOO_MANY: "dropTooMany",
}


# ── the command line ───────────────────────────────────────────────────────

# The ladder the widget names, and the ceiling each name puts on it. `off` is
# not "rung 0 exists": it is the companion never doing more than putting a
# sentence in its bubble.
INSISTENCE_STEPS = ("off", "speak", "walk", "wave", "pointer")
INSISTENCE_CEILING = {"off": 0, "speak": 1, "walk": 2, "wave": 3, "pointer": 4}

# How often a spoken line is delivered holding something, which is what the
# widget's own labels for this setting describe: "plain sprite, no props", "a
# prop now and then", "a prop on most lines". The prop is the book that
# buddy_sprites bakes into the `read` pose — the only one that exists — so the
# setting is a frequency over that clip rather than a wardrobe. Rolled once per
# line; see Companion.prop_line.
MEME_LEVELS = ("off", "light", "full")
MEME_PROP_CHANCE = {"off": 0.0, "light": 0.15, "full": 0.6}

# Defaults are the widget's defaults (plasmoid/contents/config/main.xml), so a
# companion started by hand behaves like one started by the applet. The
# switches follow the same rule, which is why the two that default to on are
# spelled as negatives: a --quiet-hours that had to be passed to switch a
# default-on setting on would mean the widget saying nothing and the setting
# being off, so the widget's "off" would be unsendable.
DEFAULT_INSISTENCE = "walk"
DEFAULT_MEMES = "light"
DEFAULT_FOCUS_MINUTES = focus_engine.FOCUS_MINUTES

# A block shorter than a minute is a typo, and one longer than four hours is
# not a focus block. Both ends clamp rather than reject: see _one_of.
FOCUS_MINUTES_MIN, FOCUS_MINUTES_MAX = 1, 240

Options = namedtuple(
    "Options",
    "brand lang alerts_only live self_test focus_minutes insistence "
    "quiet_hours memes shadow escort")


def _one_of(value, allowed, default):
    """A value fixed to the enum it has to be in.

    Everything on this command line arrives from a KDE config file — a text
    file a person can edit — by way of a shell command line. A typo in it has
    to cost the setting and nothing else: a mascot that will not start because
    someone wrote `pointr` is worse than a mascot running on the default, and
    the failure is invisible from the widget, which never sees the exit code.
    """
    text = str(value or "").strip().lower()
    return text if text in allowed else default


def _clamped_int(value, low, high, default):
    """An integer inside its range, or the default. Same contract as _one_of."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def parse_args(argv):
    """The command line, resolved and clamped, never exiting.

    argparse's own validation is deliberately not used: `choices` and
    `type=int` both answer a bad value with parser.error(), which is
    SystemExit(2) — the process is gone before it draws anything, over a
    setting. The options are read as plain strings and fixed afterwards.

    parse_known_args, allow_abbrev=False and add_help=False for the same
    reason. A flag this version has not heard of is a newer widget talking to
    an older companion, which should cost that flag rather than the companion;
    an abbreviation is ambiguous-by-accident and argparse exits on it; and
    --help is one more exit path on a program whose caller is a shell script.
    """
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--codex", action="store_true")
    parser.add_argument("--pt", action="store_true")
    parser.add_argument("--alerts-only", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    # nargs="?" so a flag left without its value is a missing value rather
    # than "expected one argument", which is another exit.
    parser.add_argument("--focus-minutes", nargs="?", default=None, const=None)
    parser.add_argument("--insistence", nargs="?", default=None, const=None)
    parser.add_argument("--no-quiet-hours", action="store_true")
    parser.add_argument("--memes", nargs="?", default=None, const=None)
    parser.add_argument("--no-shadow", action="store_true")
    parser.add_argument("--escort", action="store_true")
    known, _unknown = parser.parse_known_args(list(argv))
    return Options(
        brand="codex" if known.codex else "claude",
        lang="pt" if known.pt else "en",
        alerts_only=known.alerts_only,
        live=known.live,
        self_test=known.self_test,
        focus_minutes=_clamped_int(known.focus_minutes, FOCUS_MINUTES_MIN,
                                   FOCUS_MINUTES_MAX, DEFAULT_FOCUS_MINUTES),
        insistence=_one_of(known.insistence, INSISTENCE_STEPS, DEFAULT_INSISTENCE),
        quiet_hours=not known.no_quiet_hours,
        memes=_one_of(known.memes, MEME_LEVELS, DEFAULT_MEMES),
        shadow=not known.no_shadow,
        escort=known.escort,
    )


def default_options(**over):
    """The options a companion built without a command line runs on."""
    return parse_args([])._replace(**over)


# ── commands from the widget ───────────────────────────────────────────────

def read_command(path):
    """The command file's contents as a dict, or None.

    Invalid JSON is not an error on this path. The widget writes to a
    temporary file and renames it over the target, so a complete file is what
    a reader normally sees — but a directory watcher fires on the temporary
    file appearing too, and that one is read mid-write. This runs inside a Qt
    slot: an exception here does not lose a command, it loses the channel.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def parse_issued_at(text):
    """The widget's ISO 8601 stamp as an aware datetime, or None.

    `new Date().toISOString()` ends in Z, which datetime.fromisoformat only
    learned to read in 3.11; this has to run on whatever python3 the desktop
    has, so the Z is translated rather than relied on. A stamp without a zone
    is read as UTC, which is what the widget writes.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    raw = text.strip()
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    try:
        stamp = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=timezone.utc)


# ── holding the desktop's notifications back ───────────────────────────────

class NotificationInhibitor:
    """Keeps notifications inhibited for as long as a focus block runs.

    Why this is here rather than in the Qt-free engine: an inhibition on these
    servers is bound to the caller's D-Bus connection and dropped the moment it
    closes. Measured against the same KDE stack on
    org.freedesktop.PowerManagement.Inhibit, the one that reports what it is
    holding — HasInhibit false, a short-lived gdbus call returns cookie 67,
    HasInhibit false again as soon as that process exits. A fire-and-forget
    subprocess therefore returns a cookie and inhibits nothing. Holding one
    needs a connection that outlives the call.

    That connection is this class's own, not the process's shared session bus,
    because closing it is how the hold is given back. MEASURED here: the server
    exports UnInhibit(u), PySide6 marshals a Python int as `i`, and the call
    comes back "No such method 'UnInhibit' ... (signature 'i')" with the
    inhibition still held — there is no way from PySide6 to send a uint32. So
    the same connection-bound lifetime that makes a stray `gdbus call` useless
    is what makes this work: one connection per hold, and dropping it is the
    release. Closing the shared bus instead would take the rest of the
    process's D-Bus with it.

    Every failure is silent and costs only the inhibition: a desktop with no
    session bus, no notification server, or a server that does not implement
    Inhibit still gets a focus block, just a noisier one.
    """

    SERVICE = "org.freedesktop.Notifications"
    PATH = "/org/freedesktop/Notifications"
    # The desktop entry the server attributes the inhibition to. It is the
    # applet's, because that is the thing the user switched on.
    APP_ID = "org.kde.plasma.usagebuddies"
    CONNECTION = "usage-buddies-companion-inhibit"

    def __init__(self):
        self.cookie = None
        self._connection = None

    def _connect(self):
        """A named D-Bus connection and an interface on it, or None.

        The name carries this object's id so two inhibitors cannot land on one
        connection: Qt keys connections by name, and the second connectToBus
        with a name already in use returns the first one — closing either would
        then take both holds with it.
        """
        if QDBusConnection is None or QDBusInterface is None:
            return None
        name = f"{self.CONNECTION}-{id(self)}"
        try:
            bus = QDBusConnection.connectToBus(QDBusConnection.SessionBus, name)
            if not bus.isConnected():
                self._close(name)
                return None
            iface = QDBusInterface(self.SERVICE, self.PATH, self.SERVICE, bus)
            if not iface.isValid():
                self._close(name)
                return None
        except Exception:
            self._close(name)
            return None
        return name, iface

    @staticmethod
    def _close(name):
        if QDBusConnection is not None:
            QDBusConnection.disconnectFromBus(name)

    @staticmethod
    def _cookie_of(reply):
        """The cookie out of whatever the bus handed back, or None.

        An error is not an exception in QtDBus: it comes back as a message of
        type ErrorMessage carrying no arguments, so reading argument zero off
        it is an IndexError on a path that must never raise.
        """
        if isinstance(reply, int) and not isinstance(reply, bool):
            return reply
        arguments = getattr(reply, "arguments", None)
        values = arguments() if callable(arguments) else None
        if not values:
            return None
        try:
            return int(values[0])
        except (TypeError, ValueError):
            return None

    def hold(self, reason):
        """Ask for the inhibition. Returns the cookie, or None."""
        if self.cookie is not None:
            return self.cookie
        opened = self._connect()
        if opened is None:
            return None
        name, iface = opened
        try:
            cookie = self._cookie_of(iface.call("Inhibit", self.APP_ID, str(reason), {}))
        except Exception:
            cookie = None
        # The interface has to go before the connection does, or Qt keeps the
        # connection alive for it and warns about active objects on close.
        del iface
        if cookie is None:
            self._close(name)
            return None
        self.cookie, self._connection = cookie, name
        return cookie

    def release(self):
        """Give it back. Returns whether there was one to give back.

        A block that ends with the process needs nothing here — every
        connection it owns goes down with it — but a block that is cancelled
        leaves this process alive, and without this the hold outlives the block
        it belonged to and stays until the mascot is closed.
        """
        cookie, self.cookie = self.cookie, None
        name, self._connection = self._connection, None
        if name is not None:
            self._close(name)
        return cookie is not None


def _read_json(path):
    """The file as a mapping, or an empty one.

    A payload that is valid JSON but not an object — `1`, `[]`, `"broken"` —
    is what a file caught mid-write or edited by hand looks like, and every
    reader here goes on to call .get on it. Rejecting it at the door is one
    check instead of one per reader, and the readers still check the fields
    they take out: this only guarantees the outermost shape.
    """
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _session_rows(payload):
    """The session rows of a sessions payload, by type rather than truthiness.

    `or []` catches only the falsy, and `{"sessions": 1}` is valid JSON,
    truthy, and a TypeError as soon as anything iterates it. The failure is
    not one bad frame: the same file is still on disk at the next poll, so it
    raises every twenty seconds — with the traceback going to a log nobody
    reads and the character walking around as if nothing were wrong, having
    stopped speaking and stopped escalating for good.

    The rows are filtered as well as the list, because a single integer inside
    it breaks the .get that every reader does next.
    """
    rows = payload.get("sessions") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _fmt_remaining(seconds):
    """Seconds left in a focus block, in the width the sprite has for them.

    Minutes are rounded up while any part of one is left, so a block does not
    read "0m" for the last fifty-nine seconds of it.
    """
    seconds = int(max(0.0, seconds))
    if seconds >= 60:
        return f"{seconds // 60 + (1 if seconds % 60 else 0)}m"
    return f"{seconds}s"


def _count(value):
    """A number out of a field the collector may have left null or textual."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


class Brain(QObject):
    """Decides what is worth saying, in the same order the widget uses.

    The ladder itself lives in buddy_signals, which is pure and has no opinion
    about wording: it reads the two payloads and answers with every signal that
    fires, most urgent first. What stays here is everything that needs memory
    or a language — the no-repeat window, the rotation between sessions, the
    focus gate, and the fallback for when nothing fires at all.

    Two rules keep it from becoming wallpaper. It remembers what it recently
    said and will not repeat inside that window — the previous version rotated
    two lines and so effectively said one. And when several sessions qualify it
    rotates between them, because "ti finished" for an hour is the same
    complaint whether the sentence changes or not.
    """

    RECENT = 12          # lines to remember before allowing a repeat
    SUBJECT_RECENT = 3   # sessions to cycle past before returning to one

    # What counts as an alert, by priority rather than by a list of keys.
    # `background` is the last signal in the band that is about a session or
    # about the ability to keep working; everything numerically after it is
    # diagnosis, still true in ten minutes. Reading the boundary off the table
    # means a signal added to that band is an alert without anyone having to
    # remember to add it here too — which is how "twoRed" spent its whole life
    # written and unreachable.
    ALERT_PRIORITY = signals.PRIORITY["background"]

    # Which sessions a signal could have been about. buddy_signals.detect is
    # stateless and fills its vars from the first qualifying row, so the
    # rotation has to re-pick the subject from the same candidate set the
    # detector used. Without this, three sessions waiting become an hour of
    # complaint about whichever one sorts first.
    SUBJECT_STATES = {
        "asking": ("asking",),
        "waiting": ("waiting",),
        "idle": ("idle",),
        "allQuiet": ("idle",),
        "background": ("background",),
    }

    def __init__(self, lang="en", alerts_only=False, focus=None, escort=None,
                 quiet_hours=False):
        super().__init__()
        self.lang = lang if lang in LINES else "en"
        self.alerts_only = alerts_only
        self.quiet_hours = quiet_hours
        # Owned by the companion in the running program and created here when
        # there is none, so a Brain built on its own still answers.
        self.focus = focus if focus is not None else focus_engine.FocusSession()
        self.escort = escort if escort is not None else focus_engine.Escort()
        self.sessions = {}
        self.usage = {}
        # Seconds since the person last touched a key or the mouse, or None
        # for "no reading". Refreshed with the rest of the world, never in the
        # middle of a decision, so a Brain built by hand decides with no
        # reading at all instead of with whatever the machine running it
        # happens to report.
        self.idle = None
        # The key behind the last line, for the half of the reaction that is
        # not words. The text alone cannot be read backwards into a category —
        # the tables are prose, and with --live the wording comes from the
        # model — so the sprite would have no way of knowing what it just said.
        self.spoke = None
        self._recent = []
        self._subjects = []

    def refresh(self):
        self.sessions = _read_json(SESSIONS_FILE)
        self.usage = _read_json(WIDGET_DATA)
        # Taken here for the same reason `now` and `wall` are arguments to
        # line(): a decision that reads the world from inside itself can only
        # be tested on the machine it is running on. Once per poll is also as
        # often as it is worth asking — the probe is one round trip to the X
        # server, and on a desktop without the extension it is a cached False.
        self.idle = focus_engine.user_idle_seconds()

    @property
    def attention(self):
        """The session the collector says needs a human, or None.

        Typed here rather than at each caller, because both of them treat it
        as a session and one hands its pid to a subprocess: `"attention": "ti"`
        in the file is a TypeError inside a click handler, and an entry with no
        pid is a KeyError in the same place. A row without a pid is no answer
        to "which session", so it is None like the rest.
        """
        payload = self.sessions if isinstance(self.sessions, dict) else {}
        row = payload.get("attention")
        if not isinstance(row, dict) or row.get("pid") is None:
            return None
        return row

    def _all(self, *states):
        """Sessions in the named states — all of them when none is named —
        after the escort has had its say.

        The escort filters here, ahead of the rotation, because a lock is a
        decision about what to look at. Narrowing after the fact would leave
        the rotation cycling over sessions the user asked it to ignore and
        then discarding the result, which is a companion that goes quiet
        instead of one that concentrates.
        """
        rows = self.escort.filter(_session_rows(self.sessions))
        if states:
            rows = [s for s in rows if s.get("state") in states]
        return rows

    def payload(self):
        """The sessions payload as the detectors should see it: escorted."""
        payload = dict(self.sessions) if isinstance(self.sessions, dict) else {}
        payload["sessions"] = self._all()
        return payload

    def visible_sessions(self):
        """The sessions the companion is currently looking at, escort and all.

        The insistence ladder runs off this rather than the raw file, so an
        escort narrows what the companion escalates about as well as what it
        talks about.
        """
        return self._all()

    def quiet(self, wall=None):
        """Whether this is outside the hours this person is known to work."""
        when = time.time() if wall is None else wall
        return focus_engine.quiet_now(focus_engine.peak_hours(self.usage),
                                      time.localtime(when).tm_hour)

    def _candidates(self, key):
        """The rows the rotation may choose between for a signal."""
        states = self.SUBJECT_STATES.get(key)
        if not states:
            return []
        rows = self._all(*states)
        # idle and allQuiet come from the same state and are told apart by
        # whether an agent is still running, exactly as the detector does it.
        if key == "idle":
            return [r for r in rows if _count(r.get("background")) > 0]
        if key == "allQuiet":
            return [r for r in rows if _count(r.get("background")) <= 0]
        return rows

    def _subject_vars(self, key, row):
        """The placeholders a session-shaped category needs, for this row."""
        vars_ = {"name": str(row.get("name") or "?"),
                 "idle": signals.format_idle(row.get("idleSeconds"))}
        if key == "background":
            vars_["n"] = int(_count(row.get("background")) or 1)
        return vars_

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

    def _interrupts_typing(self, key):
        """Whether saying this now would land in the middle of a sentence.

        `self.idle` is seconds since the last input and None means the reading
        could not be taken. None is not zero and the difference is the whole
        gate: a failed probe answering zero reads as "typing right now" and
        would silence the companion permanently on every desktop without an
        idle source, which is this one. So None holds nothing back, and it
        releases nothing either — the decision falls through to what it would
        have been with no probe at all.

        A question on screen is exempt. That session is blocked on a human and
        stays blocked until one arrives, so somebody being at the keyboard is
        the moment it is most worth saying rather than least. The exempt set is
        read off the focus block instead of listed again here: two lists of
        what counts as urgent enough to interrupt drift apart, and the one that
        drifts is the one nobody is looking at.
        """
        if self.idle is None or self.idle >= TYPING_SECONDS:
            return False
        return key not in self.focus.ALLOWED

    def _pick(self, key, now=None, **vars_):
        """A line from a category, or None when there is nothing to say.

        The focus gate is here rather than around line(): every route to a
        sentence passes through this method, including the ambient fallback,
        so one check covers all of them. Putting it in line() would leave the
        caller having to know which keys a block silences, and making line()
        return the key alongside the text would change the contract of every
        caller for the benefit of one. The typing gate is here for the same
        reason and on the same terms.

        No category takes a placeholder called `now` — tests/test_companion.py
        pins that, because one would be swallowed by this signature and print
        its own braces on screen.
        """
        if not self.focus.allows(key, now):
            return None
        if self._interrupts_typing(key):
            return None
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

    def line(self, now=None, wall=None):
        """The current thing worth saying, or None. Silence is the default.

        `now` is monotonic and only the focus block reads it; `wall` is a Unix
        timestamp and only the hour-of-day signals read it. Both are arguments
        so the whole decision can be tested without waiting for midnight or for
        a block to run out.
        """
        now = time.monotonic() if now is None else now
        self.spoke = None
        quiet = self.quiet_hours and self.quiet(wall)
        for signal in signals.detect(self.payload(), self.usage, wall):
            # The list is sorted by priority, so the first signal past the
            # alert boundary means every remaining one is past it too.
            if (self.alerts_only or quiet) and signal.priority > self.ALERT_PRIORITY:
                break
            vars_ = dict(signal.vars)
            chosen = self._rotate(self._candidates(signal.key))
            if chosen is not None:
                vars_.update(self._subject_vars(signal.key, chosen))
            text = self._pick(signal.key, now=now, **vars_)
            if text:
                self.spoke = signal.key
                return text
            # Silenced by the block, or a category with no lines: try the next
            # signal down rather than jumping straight to a joke.

        if self.alerts_only or quiet:
            return None
        # Nothing is wrong. Alternate between saying so and saying something
        # else entirely, so silence has texture. Still through _pick, so a
        # focus block silences this too.
        key = random.choice(("ambient", "philosophy"))
        text = self._pick(key, now=now)
        if text:
            self.spoke = key
        return text


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


# ── the basket's own window ────────────────────────────────────────────────

def _stick_to_all_desktops(widget):
    """Show a window on every virtual desktop.

    Without this it lives on whichever desktop it was launched from and has
    to be hunted for. KWin's own scripting sets it, but the X property has
    to be written too — KWin reported onAllDesktops=true while the window
    still carried desktop 0, and only the property made it follow.

    A function rather than a method because there are two windows now, and a
    second copy of the incantation is a second thing to get wrong. Every
    failure is silent and costs the stickiness: this is reached from a timer
    slot, where raising ends the process.
    """
    try:
        wid = int(widget.winId())
        subprocess.Popen(
            ["sh", "-c",
             f"xprop -id {wid} -f _NET_WM_DESKTOP 32c "
             f"-set _NET_WM_DESKTOP 0xFFFFFFFF 2>/dev/null"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        return


class HoopWindow(QWidget):
    """The basket: a second top-level window, and scenery in every other way.

    Its own window because it is 192 by 144 while the character's is 56 by 56
    and moves every frame. One window cannot be both, and a window grown to
    hold the drawing would take the sprite's position, the side the bubble
    opens on and the drop target with it — all three are measured off this
    window's own geometry.

    It does not take the mouse. WA_TransparentForMouseEvents is the whole of
    that promise and it is not decoration: a frameless always-on-top window of
    this size over somebody's editor would otherwise swallow every click that
    landed inside it, which is a defect wearing the costume of a game. Nothing
    here has a mouse handler either, so there is no second way in.

    The clip table is walked here rather than handed to sprites.Animator: the
    Animator resolves names against CLIPS, which is the character's, and a
    hoop frame looked up there resolves to nothing. Every name is checked
    against this window's own sheet before it is drawn, so a table naming a
    frame the art does not have costs that frame and not the process.
    """

    def __init__(self, scale=HOOP_SCALE):
        super().__init__(None)
        # The character's flags, for the character's reasons: no frame, above
        # the windows it is drawn over, out of the taskbar, and never taking
        # the focus away from whatever is being typed into.
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.scale = int(scale)
        self.sheet = sprites.build_hoop_sheet(self.scale)
        self.frame = HOOP_RESTING
        self._frames = []
        self._at = 0
        self._elapsed = 0.0
        self._stuck = False
        image = self.sheet.get(HOOP_RESTING)
        if image is not None:
            self.resize(image.width(), image.height())

    @property
    def opening(self):
        """The centre of the drawn hole, as an offset from the top-left.

        Read off the art's own HOOP_RIM at this window's scale. The number is
        never written down here: the basket is positioned by the middle of its
        opening, because that is the point buddy_hoop measures a throw
        against, and a second copy of where the hole is would put the drawing
        and the hit area in two different places.
        """
        left, top, width, height = sprites.HOOP_RIM
        return ((left + width / 2.0) * self.scale,
                (top + height / 2.0) * self.scale)

    @staticmethod
    def duration(name):
        """How long a hoop clip runs for, in seconds. Zero if there is none."""
        clip = getattr(sprites, "HOOP_CLIPS", {}).get(name) or {}
        return sum(ms for _frame, ms in clip.get("frames", ())) / 1000.0

    def place(self, centre):
        """Move so the middle of the opening lands on `centre`.

        Snapped to the drawing's own scale, for the reason Companion._place
        gives: a grid that sits on half a source pixel does not look blurry,
        it looks like the picture is crawling.
        """
        ox, oy = self.opening
        step = max(1, self.scale)
        self.move(int(round((centre[0] - ox) / step) * step),
                  int(round((centre[1] - oy) / step) * step))

    def rest(self):
        """Back to the hanging net, with nothing playing."""
        self._frames = []
        self._at = 0
        self._elapsed = 0.0
        self.frame = HOOP_RESTING
        self.update()

    def play(self, name):
        """Start a one-shot from HOOP_CLIPS, skipping frames the sheet lacks."""
        clip = getattr(sprites, "HOOP_CLIPS", {}).get(name) or {}
        self._frames = [(frame, ms) for frame, ms in clip.get("frames", ())
                        if frame in self.sheet]
        self._at = 0
        self._elapsed = 0.0
        if self._frames:
            self.frame = self._frames[0][0]
        self.update()

    def advance(self, dt):
        """Step whatever is playing. Nothing here loops, and nothing repaints
        when nothing is playing: a still basket costs no frames at all."""
        if not self._frames:
            return
        self._elapsed += max(0.0, float(dt))
        while self._frames:
            _frame, ms = self._frames[self._at]
            if self._elapsed < ms / 1000.0:
                break
            self._elapsed -= ms / 1000.0
            self._at += 1
            if self._at >= len(self._frames):
                self._frames = []
                self._at = 0
                break
        self.frame = self._frames[self._at][0] if self._frames else HOOP_RESTING
        self.update()

    def appear(self, centre):
        """Put it up at a point, hanging still, on every virtual desktop."""
        self.rest()
        self.place(centre)
        self.show()
        if not self._stuck:
            self._stuck = True
            # After the window is mapped, or there is nothing to set the
            # property on. The same delay the character's own window uses.
            QTimer.singleShot(600, lambda: _stick_to_all_desktops(self))

    def paintEvent(self, _event):
        image = self.sheet.get(self.frame)
        if image is None:
            return
        p = QPainter(self)
        # Pixel art, like everything else drawn here: no antialiasing and no
        # smoothing, or the hard edges that carry the style become gradients.
        p.setRenderHint(QPainter.Antialiasing, False)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        p.drawImage(0, 0, image)
        p.end()


class Companion(QWidget):
    """The character. Everything here is presentation; Brain decides what it says.

    It roams the whole screen rather than sliding along the bottom edge: a
    companion pinned to one line reads as a status bar with a face. Movement is
    a walk toward a target with a gait — leaning into the direction, bobbing
    per step, squashing on landing — because constant-velocity translation
    reads as a sprite being dragged, not a thing that moves itself.
    """

    def __init__(self, brand="claude", lang="en", alerts_only=False, live=False,
                 options=None):
        super().__init__(None)
        # The four positional arguments predate the settings and are kept
        # because tests and callers construct a plain Companion() with them;
        # `options` carries the whole command line and wins where both say
        # something, so there is one source of truth in the running program.
        self.options = options if options is not None else default_options(
            brand=brand, lang=lang, alerts_only=alerts_only, live=live)
        brand = self.options.brand
        lang = self.options.lang
        alerts_only = self.options.alerts_only
        live = self.options.live
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
        # A folder dropped on the character is a question about that
        # repository; dropEvent is where the payload is judged.
        self.setAcceptDrops(True)

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

        # The focus block, the escort and the insistence ladder are owned here
        # and handed to the Brain, so both halves are reading the same one.
        self.focus = focus_engine.FocusSession()
        self.escort = focus_engine.Escort()
        # Rung 4 takes the mouse out of someone's hand, so it is reached only
        # when it was asked for by name. The ceiling below is the second half
        # of the same opt-in: the engine will not report a 4 without this, and
        # the companion will not act on one above the ceiling either.
        self.insistence = focus_engine.Insistence(
            allow_pointer=self.options.insistence == "pointer")
        self._insisted = {}          # pid -> the highest rung already acted on
        self.insist_until = 0.0
        self.insist_clip = ""
        self._focus_phase = focus_engine.PHASE_IDLE
        self.inhibitor = NotificationInhibitor()

        self.brain = Brain(lang, alerts_only, focus=self.focus, escort=self.escort,
                           quiet_hours=self.options.quiet_hours)
        # Decided once per line rather than per frame: rolled every tick, the
        # book would appear and vanish thirty times a second.
        self.prop_line = False
        self.lang = lang
        self.bubble = ""
        self.bubble_until = 0.0
        self.said = ""
        self.bubble_size = (0, 0)
        # How far the window extends to the left of the character, which is
        # non-zero only while a bubble is open on that side. Everything that
        # converts between the window and the character goes through it.
        self.bubble_pad = 0

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
        # Thrown rather than put down. The samples are the last few hand
        # positions, which buddy_actions turns into a velocity at the moment of
        # release; `flying` is the flag that says the character is in the air
        # under its own momentum instead of being carried by something.
        self.throw_samples = []
        self.flying = False

        # The temper and the basket. buddy_hoop owns both, and the rim it is
        # built with is the drawing's own opening converted once — None when
        # the art has no basket in it, which turns the game off and leaves the
        # temper working. `hoop_enabled` is the one switch that disarms all of
        # it: the failure path sets it, and so does --self-test, because a
        # second window appearing on a desktop nobody is watching is exactly
        # what that mode exists to prevent.
        self.game = buddy_hoop.HoopGame(BUDDY_PX, buddy_hoop.rim_width())
        self.hoop_enabled = True
        self.hoop_window = None
        self.hoop_hide_at = 0.0      # the score clip is allowed to finish
        self.hoop_tries_at = 0       # misses at the moment this one went up
        # The first leg of the getaway: running to where the pointer is, so
        # the carry starts on it rather than a body's length away from it.
        self.chasing = False
        self.chase_until = 0.0
        self.chase_seconds = 0.0

        # The other mascot. One presence file per process, both halves on a
        # one-second cadence inside PeerDirectory, and the state machine of an
        # encounter in Encounter; all this class does is act on the verdict.
        self.yard = peers.PeerDirectory()
        self.encounter = peers.Encounter()
        self.greeted = None      # the peer already reacted to, once per meeting
        self.meeting = False     # whether one was in flight on the last frame

        # Written by the poll, read on the frame path: the pose the last line
        # was delivered in, and whether anything is running right now.
        self.mood_clip = ""
        self.mood_until = 0.0
        self.working = False
        # The facing the turn-around one-shot last fired for.
        self._faced = self.facing
        self._turned_at = 0.0

        self.resize(BUDDY_PX, BUDDY_PX)
        self._place()

        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self._tick)
        self.frame_timer.start(FRAME_MS_ACTIVE)
        self._active = True

        # Commands from the widget. Set up before any timer that reads it: the
        # instant the process came up has to be recorded before the file is
        # ever looked at, because that is what a command's issuedAt is
        # compared against, and _poll re-checks the watch on every cycle.
        self.started_at = datetime.now(timezone.utc)
        self.last_command_at = None
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._command_changed)
        self.watcher.directoryChanged.connect(self._command_changed)
        self._rewatch_command()

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll)
        self.poll_timer.start(POLL_MS)
        QTimer.singleShot(200, self._poll)
        # After the window is mapped, or there is nothing to set the property on.
        QTimer.singleShot(600, self._make_sticky)
        # And one read of whatever is already in the file, for a companion
        # started while a block was meant to be running. Stale contents are
        # rejected by the timestamp, so this can only ever act on a command
        # written in the moment between starting and here.
        QTimer.singleShot(250, self._command_changed)

        # The presence file has to go when the process does. Without this a
        # companion closed from its own menu stays visible to the other one
        # for buddy_peers.STALE_SECONDS, which is five seconds of the survivor
        # walking over to greet a mascot that is not there.
        application = QApplication.instance()
        if application is not None:
            application.aboutToQuit.connect(self._retire)

    # ── commands from the widget ──

    def _rewatch_command(self):
        """(Re-)watch the command file and the directory holding it.

        Two known failure modes, both of which cost every command after the
        first. The widget writes to a temporary file and renames it over the
        target — the only way a reader cannot see a half-written file — so the
        inode the watcher holds is replaced each time, and QFileSystemWatcher
        drops a path whose file was removed. And the file may not exist at all
        when the companion starts, so there is nothing to add a watch to yet;
        the directory watch is what notices it being created, and this is
        called again from every poll to pick up a directory created later.
        """
        if self.watcher is None:
            return
        watched = set(self.watcher.files()) | set(self.watcher.directories())
        for path in (str(COMMAND_FILE.parent), str(COMMAND_FILE)):
            if path not in watched and os.path.exists(path):
                self.watcher.addPath(path)

    def _command_changed(self, _path=None):
        self.apply_command(read_command(COMMAND_FILE))
        self._rewatch_command()

    def apply_command(self, payload):
        """Act on a command from the widget. Returns whether one was acted on.

        The file is state, not an event: it keeps whatever was written last
        until the next command replaces it. A companion restarted the next
        morning that does not compare the timestamp re-enters the focus block
        someone asked for yesterday, which is the reason issuedAt is in the
        format at all. A command with no readable timestamp is dropped for the
        same reason — there is nothing to tell it apart from that stale one.

        Everything else is ignored rather than raised. An unknown verb is a
        newer widget talking to an older companion, and a malformed payload is
        a half-written file; neither is worth losing the channel over.
        """
        if not isinstance(payload, dict):
            return False
        issued = parse_issued_at(payload.get("issuedAt"))
        if issued is None or issued <= self.started_at:
            return False
        # A watcher fires more than once for one write — the rename shows up
        # on both the file and the directory — and re-running focus.start
        # would restart the block from zero each time.
        if self.last_command_at is not None and issued <= self.last_command_at:
            return False
        self.last_command_at = issued
        command = payload.get("command")
        if command == "focus.start":
            self.start_focus(_clamped_int(payload.get("minutes"), FOCUS_MINUTES_MIN,
                                          FOCUS_MINUTES_MAX,
                                          self.options.focus_minutes))
            return True
        if command == "focus.stop":
            self.stop_focus()
            return True
        return False

    # ── the focus block ──

    def start_focus(self, minutes=None):
        """Begin a block: settle down, go quiet, hold the notifications."""
        now = time.monotonic()
        minutes = self.options.focus_minutes if minutes is None else minutes
        self.focus.start(now, minutes)
        self._focus_phase = self.focus.phase(now)
        self.inhibitor.hold(self._t("focusReason"))
        # It stays where it is for the block rather than roaming through it.
        self.target = (self.pos_x, self.pos_y)
        self.insist_until = 0.0
        self._say(self._t("focusStarted").replace("{n}", str(int(minutes))))

    def stop_focus(self):
        """Call the block off. Cancelled, not finished: nothing to celebrate."""
        if not self.focus.active:
            return False
        self.focus.cancel()
        self._focus_phase = focus_engine.PHASE_IDLE
        self.inhibitor.release()
        self._say(self._t("focusStopped"))
        return True

    def _focus_tick(self, now):
        """Move the block through its phases, once per poll."""
        phase = self.focus.phase(now)
        if phase == self._focus_phase:
            return
        self._focus_phase = phase
        if phase == focus_engine.PHASE_ENDING:
            # The end of a block has to be visible before it happens. Parked in
            # a corner it is dozing at 200ms a frame, and a block that flips
            # straight from running to done gives it no frames to walk back in
            # — the end reads as a bubble appearing out of nowhere.
            self.docked = False
            self.target = self._approach_target()
            self._wake()
        elif phase == focus_engine.PHASE_DONE:
            # cancel() rather than leaving it expired: `done` is a state a
            # clock stays in, so an announcement bound to it repeats once per
            # poll forever. Back to idle, having said it once.
            self.focus.cancel()
            self._focus_phase = focus_engine.PHASE_IDLE
            self.inhibitor.release()
            self.docked = False
            self._say(self._t("focusOver"))
            self._wake()

    # ── what it says ──

    def _poll(self):
        now = time.monotonic()
        self.brain.refresh()
        # Read once per poll rather than on the frame path: it comes out of a
        # file the collector writes, and the idle pose is the only thing that
        # wants it.
        self.working = any(row.get("state") == "working"
                           for row in self.brain.visible_sessions())
        # A directory that did not exist when this started does now, once the
        # collector has run; the watch is cheap to re-check and lost otherwise.
        self._rewatch_command()
        self._maybe_auto_escort()
        self._focus_tick(now)
        self._maybe_refill()
        line = self.brain.line(now=now)
        self._insist(now)
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
            self.prop_line = self._roll_prop()
            self.bubble_until = now + SPEAK_SECONDS
            # The pose the line arrives in, which is the sprite's half of what
            # the sentence says. Bounded rather than tied to the bubble: the
            # bubble is up for sixteen seconds, and nothing panics for sixteen
            # seconds without becoming wallpaper.
            mood = self._mood_for(self.brain.spoke)
            self.mood_clip = clip_or_fallback(mood) if mood else ""
            self.mood_until = now + MOOD_SECONDS if mood else 0.0
            # The double-take only fires for something that wants the human.
            # Ambient remarks get no jump, or the jump stops meaning anything.
            if self.brain.attention:
                self.alert_until = now + ALERT_SECONDS
            self._resize_for_bubble()
            if not self.docked and not self.focus.silences(now):
                # Step away from the edges so the bubble has room to open.
                self.target = (
                    max(self.min_x + 160, min(self.max_x - 160, self.pos_x + random.uniform(-140, 140))),
                    max(self.min_y + 60, min(self.max_y, self.pos_y)))
            self._wake()
        elif not line:
            self.said = ""

    @staticmethod
    def _mood_for(key):
        """The clip a spoken line is delivered in, or "" for most of them.

        Two triggers, both measured elsewhere and neither invented here: the
        band of signals that means the work is about to stop being possible,
        and the one signal that means a session finished with nothing of its
        own left running.
        """
        if not key:
            return ""
        if key == CELEBRATE_KEY:
            return "celebrate"
        priority = signals.PRIORITY.get(key)
        if priority is not None and PANIC_BAND[0] <= priority <= PANIC_BAND[1]:
            return "panic"
        return ""

    def _corner_bounds(self):
        """The rectangle of legal top-left corners, in buddy_actions' order."""
        return (self.min_x, self.min_y, self.max_x, self.max_y)

    def _screen_rects(self):
        """The screens as plain rectangles, for the modules that have no Qt."""
        return [(g.x(), g.y(), g.width(), g.height()) for g in self.screens]

    def _session_window(self, pid):
        """KWin's geometry for a session's window, or None.

        Blocking — 38-54 ms measured, worse with many windows open — so this
        belongs on the poll and never on a frame. None is ordinary rather than
        exceptional: no busctl, no KWin, a terminal that has since closed, or a
        session whose window is on another machine's display.
        """
        return actions.window_geometry(pid)

    def _approach_target(self):
        """Somewhere on the current screen it cannot be missed.

        Not the pointer. QCursor.pos() under this compositor returns
        XWayland's shadow of the pointer rather than the pointer — the same
        reading that makes _tug send deltas instead of positions — so walking
        to it walks to wherever an X client last saw the cursor, which may be
        another monitor. The middle of the screen it is already on is a
        coarser aim and a true one.
        """
        screen = self._screen_at(self.pos_x, self.pos_y)
        x = screen.center().x() - BUDDY_PX / 2
        y = screen.top() + (screen.height() - BUDDY_PX) * 0.6
        return (float(max(self.min_x, min(self.max_x, x))),
                float(max(self.min_y, min(self.max_y, y))))

    def _insist(self, now):
        """Escalate on a session that has been wanting a human for a while.

        `now` is monotonic, which buddy_focus.Insistence requires: on the wall
        clock an NTP correction steps backwards and the rung freezes at
        whatever it had reached.

        Nothing above the first rung happens during a focus block or in the
        quiet hours. The ladder exists to interrupt, and both of those are a
        decision not to be interrupted.
        """
        ceiling = INSISTENCE_CEILING.get(self.options.insistence, 0)
        levels = self.insistence.update(self.brain.visible_sessions(), now)
        # Forget sessions the engine has forgotten, so a companion left running
        # for days does not keep an entry per pid that ever existed.
        self._insisted = {pid: rung for pid, rung in self._insisted.items()
                          if pid in levels}
        if ceiling <= 1 or not levels:
            return
        if self.focus.silences(now) or (self.options.quiet_hours and self.brain.quiet()):
            return
        pid, level = max(levels.items(), key=lambda item: item[1])
        level = min(level, ceiling)
        if level <= 1:
            return
        # Only when the rung goes up. Re-running the same rung every twenty
        # seconds is a character that walks to the middle of the screen three
        # times a minute and never gets anywhere.
        if self._insisted.get(pid, 0) >= level:
            return
        self._insisted[pid] = level
        self.docked = False
        self.target = self._approach_target()
        # From rung 3 up this is an escalation about one particular session, so
        # it is worth what KWin charges to find that session's window. Asked
        # for here because this runs on the poll: on the frame path the same
        # call would cost a second of animation.
        window = self._session_window(pid) if level >= 3 else None
        if level >= 3:
            perch = actions.perch_position(window, BUDDY_PX, self._corner_bounds())
            if perch is not None:
                # Sitting on the window that wants a human says which one it
                # is. The middle of the screen only says that one of them does.
                self.target = perch
            self.insist_clip = clip_or_fallback("wave")
            self.insist_until = now + INSIST_GESTURE_SECONDS
        if level >= 4:
            # The same machine the drag retaliation uses, and deliberately the
            # only one: a second way to move the cursor is a second way to get
            # it wrong. _ensure_pointer is a no-op after the first call.
            self._ensure_pointer()
            if self.pointer:
                # Where the pointer has to end up, when that can be answered.
                # None covers every case buddy_actions will not deliver into —
                # no geometry, minimised, off-screen, the other monitor — and
                # the fallback is the behaviour this rung already had: the
                # middle of the screen it is standing on. The rung's safety was
                # never in the destination (it is the time cap, the small
                # deltas and the route that stays on one screen), so an unknown
                # window costs the aim rather than the summons.
                #
                # Known and not corrected here: the pointer arrives displaced
                # by the gap between the cursor and the character at the moment
                # the run began. There is no way to read the pointer's absolute
                # position under XWayland to measure that gap — see _tug.
                aim = actions.delivery_target(window, BUDDY_PX,
                                              self._corner_bounds(),
                                              (self.pos_x, self.pos_y),
                                              self._screen_rects())
                if aim is not None:
                    self.target = aim
                self.insist_clip = clip_or_fallback("point")
                self.insist_until = now + INSIST_TUG_SECONDS
                self._begin_tug(now, INSIST_TUG_SECONDS, self.target)
        self._wake()

    def _maybe_refill(self):
        """Buy another batch of lines, if the desktop has actually changed.

        Runs at most one call at a time and never blocks: the answer arrives on
        a signal, and until it does the companion keeps talking from the table.
        """
        if self.voice is None or self.refilling is not None:
            return
        state = buddy_voice.situation(self.brain.sessions, self.brain.usage)
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
        # Destroyed here rather than on the signal, and this is the only place
        # it can be. A QProcess parented to the widget outlives its run and is
        # freed with the companion, which for --live is one object every four
        # minutes for as long as the desktop session lasts. Both `finished` and
        # `errorOccurred` can arrive for one process, so a deleteLater bound to
        # either signal would schedule the same object twice; the guard above
        # is what makes this run exactly once.
        process.deleteLater()
        lines, _meta = buddy_voice.harvest(raw)
        self.voice.delivered(lines)

    def _resize_for_bubble(self):
        metrics = QFontMetrics(self._bubble_font())
        width = min(BUBBLE_MAX, metrics.horizontalAdvance(self.bubble) + 24)
        rect = metrics.boundingRect(0, 0, width - 24, 0, Qt.TextWordWrap, self.bubble)
        self.bubble_size = (width, rect.height() + 18)
        self.bubble_pad = self._bubble_pad_for(width)
        self.resize(BUDDY_PX + width + 12, max(BUDDY_PX + 10, self.bubble_size[1] + 24))
        self._place()

    def _bubble_pad_for(self, width):
        """How far left of the character the window has to reach, in pixels.

        The bubble used to be drawn at a fixed offset to the right of the
        sprite while the window grew to the right as well, and max_x only ever
        reserves the character's own width — so parked against the right-hand
        edge of a screen, the bubble was laid out past the end of it and was
        simply not on screen. The dodge in _poll that steps away from the
        edges before speaking does not cover it: that one only runs when it is
        not docked, and docked in a corner is exactly the case.

        The side is chosen from the room there actually is on the screen it is
        standing on, and the window is anchored so the character does not move
        when the bubble opens. Zero means the bubble opens to the right, which
        is the common case and the one that leaves the window where it was.
        """
        needed = width + 12
        screen = self._screen_at(self.pos_x, self.pos_y)
        room_right = screen.right() - (self.pos_x + BUDDY_PX)
        room_left = self.pos_x - screen.left()
        # Right unless the left genuinely has more: on a screen too narrow for
        # either side the bubble is clipped whatever happens, and clipped on
        # the side with less room is worse.
        if room_right >= needed or room_right >= room_left:
            return 0
        return int(needed)

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
        """Show on every virtual desktop. The basket's window asks for the
        same thing, so the incantation itself lives at module scope."""
        _stick_to_all_desktops(self)

    def _place(self):
        """Move the window, snapped to the sprite grid.

        A 2x sprite whose window sits on an odd screen pixel has every source
        pixel straddling the screen grid by half. It does not look blurry —
        nothing is resampled — it looks like the character is crawling. Moving
        only in whole source pixels costs one pixel of positional precision
        and buys a sprite that holds still while it walks.

        pos_x is the character, not the window. With a bubble open on the left
        the window starts bubble_pad pixels further left and the sprite is
        drawn that far into it, so the character stays where it was standing
        when it began to speak.
        """
        step = sprites.SCALE
        self.move(round((self.pos_x - self.bubble_pad) / step) * step,
                  round(self.pos_y / step) * step)

    def _tick(self):
        now = time.monotonic()
        dt = self.frame_timer.interval() / 1000.0

        if self.bubble and now > self.bubble_until:
            self.bubble = ""
            # The window shrinks back around the character, and the left-hand
            # anchor goes with it, or it would stay shifted by the width of a
            # bubble that is no longer drawn.
            self.bubble_pad = 0
            self.resize(BUDDY_PX, BUDDY_PX + 10)
            self._place()

        self._mingle(now)

        moving = False
        if self.dragging and self.hand is not None:
            self._swing(dt)
        elif self.flying:
            self._fly(dt, now)
            moving = True
            self._wake()
        elif now < self.tug_until and self.tug_route:
            self._drive(now)
            moving = True
            self._wake()
        elif not self.dragging:
            tx, ty = self.target
            dx, dy = tx - self.pos_x, ty - self.pos_y
            moving = abs(dx) > 1.5 or abs(dy) > 1.5

            if moving:
                # The run at the pointer moves at the getaway's speed and not
                # at the walking one. It is the same movement in two legs, and
                # a character that strolls over to take your mouse is not
                # angry, it is browsing.
                running = now < self.tug_until or self.chasing
                speed_x = TUG_RUN_SPEED if running else WALK_SPEED
                speed_y = TUG_RUN_SPEED * 0.6 if running else CLIMB_SPEED
                if abs(dx) > 1.5:
                    self.pos_x += min(abs(dx), speed_x * dt) * (1 if dx > 0 else -1)
                    self.facing = 1 if dx > 0 else -1
                if abs(dy) > 1.5:
                    self.pos_y += min(abs(dy), speed_y * dt) * (1 if dy > 0 else -1)
                self.settled_at = now
                self._wake()
                if self.chasing and now >= self.chase_until:
                    # Still running when the leg ran out. Taking the pointer
                    # from here is worse aim and it is not nothing; a leg that
                    # never arrives losing the getaway altogether is.
                    self._chase_arrived(now)
            elif self.chasing:
                # Arrived. The pointer is under it, and the carry can start
                # without the displacement the second leg cannot correct.
                self._chase_arrived(now)
            elif self.docked:
                self._doze()
            elif self.focus.silences(now):
                # Settled for the block. Picking a new target here is a
                # character wandering off during the thing it is sitting out.
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
        self._hoop_tick(now, dt)
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

    def _launch(self, now, velocity):
        """Let go of it mid-gesture and it keeps the hand's speed.

        A tug in flight is called off here rather than left to run out, and a
        release that becomes a throw never starts one — the precedence is in
        mouseReleaseEvent, and this is the half of it that clears the state.
        """
        self.vel_x, self.vel_y = velocity
        self.flying = True
        self.docked = False
        self.tug_until = 0.0
        self.tug_route = None
        self.tug_from = None
        self.target = (self.pos_x, self.pos_y)
        self.next_move = now + IDLE_MAX
        self._wake()

    def _fly(self, dt, now):
        """One step of a throw. buddy_actions owns the arc; this owns the sprite.

        The landing releases it back into roaming rather than docking it. _snap
        is the answer to a placement, and a body that skidded to a halt against
        the bottom of the screen was not placed there — docking it would end
        every throw with the mascot asleep in whichever corner it rolled to.
        """
        was = (self.pos_x, self.pos_y)
        step = actions.integrate((self.pos_x, self.pos_y), (self.vel_x, self.vel_y),
                                 dt, self._corner_bounds())
        self.pos_x, self.pos_y = step.x, step.y
        self.vel_x, self.vel_y = step.vx, step.vy
        if abs(step.vx) > 1.0:
            self.facing = 1 if step.vx > 0 else -1
        if step.bounced:
            self._play_once("land")
        self._place()
        # Judged step by step and against the travel rather than against this
        # frame's position: a throw covers up to 120 px in one integration
        # step, which is more than two sprite widths, so asking only where it
        # is now misses every throw fast enough to be worth aiming.
        self._hoop_landed(was, (self.pos_x, self.pos_y), now)
        if step.resting:
            self.flying = False
            self.vel_x = self.vel_y = 0.0
            self.target = (self.pos_x, self.pos_y)
            self.settled_at = now
            self.next_move = now + random.uniform(IDLE_MIN, IDLE_MAX)
            self._play_once("land")
            self._hoop_ended(now)

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

    def _mingle(self, now):
        """Notice the other mascot, if there is one, and react to it once.

        Presence goes out on every frame and costs nothing on almost all of
        them: PeerDirectory writes and reads on a cadence of a second and
        answers from its cache in between.

        The encounter is suspended in six states, and all six are the same
        objection — the position this process is publishing is not where the
        character is going to be. Dragged and thrown it is wherever the hand or
        the arc puts it; during a tug, and during the run at the pointer that
        leads into one, it is covering 340 px/s, four times the walking speed
        the notice radius was measured against. Docked, it is somewhere it was
        put on purpose, and walking off to say hello is exactly what putting
        it in a corner says not to do. And a focus block is a decision not to
        be interrupted, which two mascots greeting each other in the middle of
        one plainly is.

        Publishing carries on through all five, because being seen costs
        nothing and going quiet would make this companion disappear from the
        other one's directory every time it was picked up.
        """
        me = self.yard.publish(self.options.brand, self.pos_x, self.pos_y, now)
        if (self.dragging or self.flying or self.docked or self.chasing
                or now < self.tug_until or self.focus.silences(now)):
            return
        meeting = self.encounter.update(me, self.yard.peers(now), now)
        if meeting is None or meeting.phase == peers.PHASE_PART:
            # Released back into wandering, and not by PHASE_PART alone. That
            # one is emitted when the pair walks apart or the meeting times
            # out, but the peer that stops publishing mid-meeting — closed
            # from its own menu, or killed — ends the encounter with a None
            # and no PART at all. `busy` is false in both cases, which is why
            # the ending is read off that rather than off the phase.
            if self.meeting and not self.encounter.busy:
                self.next_move = now
            self.meeting = False
            self.greeted = None
            return
        self.meeting = True
        # Neither of them wanders off mid-encounter: the roaming timer is held
        # ahead of now for as long as this lasts.
        self.next_move = max(self.next_move, now + IDLE_MIN)
        if meeting.phase == peers.PHASE_APPROACH:
            if meeting.role == peers.ROLE_MOVER:
                self.target = self._beside(meeting.peer)
            else:
                # The waiter stands still. Both walking is a chase and both
                # waiting is two statues; buddy_peers.approaches decides which
                # of the two this process is, from the pids alone and with no
                # message between them.
                self.target = (self.pos_x, self.pos_y)
            return
        # Standing next to each other: stop, turn to it, and react once.
        self.target = (self.pos_x, self.pos_y)
        self.facing = 1 if meeting.peer.x >= self.pos_x else -1
        self._greet(meeting)

    def _beside(self, peer):
        """Where to stand to be next to a peer, on the side it is already on."""
        x = peer.x - MEET_GAP if peer.x >= self.pos_x else peer.x + MEET_GAP
        return (max(self.min_x, min(self.max_x, x)),
                max(self.min_y, min(self.max_y, peer.y)))

    def _greet(self, meeting):
        """Say something to the other one, once per meeting.

        The reaction is this file's and not the module's: buddy_peers exposes
        same_brand and the peer's brand precisely so that meeting one of its
        own kind and meeting the other provider's are allowed to be two
        different things. A nod for its own, a shake of the head for the other.
        """
        if self.greeted == meeting.peer.pid:
            return
        self.greeted = meeting.peer.pid
        if meeting.same_brand:
            self._play_once("nod")
            self._say(self._t("greetSame"))
        else:
            self._play_once("shake")
            self._say(self._t("greetOther").replace("{name}",
                                                    str(meeting.peer.brand)))

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

    def _may_take_the_pointer(self):
        """Whether the setting allows the cursor to be moved at all.

        One truth and two callers — the getaway and the run that leads into
        one — because the check being at some of the call sites rather than at
        all of them is the defect this already paid for once: the insistence
        ladder asked and the drag retaliation did not, so a companion set to
        `off` still took the mouse when it was hauled around.
        """
        return INSISTENCE_CEILING.get(self.options.insistence, 0) > 0

    def _begin_tug(self, now, seconds, target):
        """Start a run that carries the pointer along with it, if allowed.

        One entry point, used by both the drag retaliation and the last rung of
        the insistence ladder. A second way of moving someone's cursor is a
        second way of getting it wrong, and this one is already the version
        that survived measurement: a curved route, a speed profile, and deltas
        rather than absolute positions.

        The permission check is here rather than at the call sites, and that is
        the whole point of there being one entry point. It was at one of the
        two: the ladder's top rung asked whether the pointer was opt-in, and
        the drag retaliation did not, so a companion configured with
        `--insistence off` still took the mouse when it was hauled around. The
        setting reads as "leave me alone" and the config page's own warning
        implies the cursor is off the table; anything else is a program
        contradicting its own switch.

        `off` is the only level that refuses. Every other one keeps the
        getaway: it answers being manhandled, not a session waiting, so
        gating it on the ladder's top rung would silently remove it from the
        default and from every level but one.
        """
        if not self._may_take_the_pointer():
            return
        self.tug_until = now + seconds
        self.tugged_at = now
        self.tug_from = None
        self.target = target
        self.tug_route = self._make_route((self.pos_x, self.pos_y), target)
        self.tug_began = now
        self.docked = False
        self.next_move = self.tug_until + 1.0
        # Back to the animating rate first. Idle ticks are 200ms, and a pull
        # that advances six percent of the gap five times a second is not a
        # tug, it is a slow leak.
        self._wake()

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

    # ── the run at the pointer ──

    def _far_target(self, here):
        """Somewhere on this screen worth running to.

        The furthest of a handful of candidates rather than a random one: a
        kidnapping that ends four pixels away is a shrug.

        Within the screen it is already on. Crossing a monitor boundary loses
        the pointer: the two displays this was measured on are different
        heights, so on the way across the compositor clamps the pointer to
        whatever is a valid position, the deltas that were clamped away are
        gone, and it reappears behind — which on screen is the cursor lagging
        and then arriving displaced.
        """
        screen = self._screen_at(*here)
        lo_x = screen.left() + 8
        hi_x = max(lo_x, screen.right() - BUDDY_PX - 8)
        lo_y = screen.top() + 8
        hi_y = max(lo_y, screen.bottom() - BUDDY_PX - 8)
        candidates = [(float(random.randint(lo_x, hi_x)),
                       float(random.randint(lo_y, hi_y))) for _ in range(6)]
        return max(candidates,
                   key=lambda t: (t[0] - here[0]) ** 2 + (t[1] - here[1]) ** 2)

    def _begin_chase(self, now, spot, seconds):
        """Leg one of the getaway: run to the pointer. True if it started.

        Why there is a first leg at all. _tug moves the pointer by the
        character's own per-frame delta and never by an absolute position —
        it cannot, there is no readable absolute position on this desktop —
        so the cursor arrives displaced from the character by exactly the gap
        between them when the carry began. A body's length of gap is a body's
        length of error, every time. Starting the run on the cursor makes the
        gap zero, and the two arrive together.

        Guarded by the same setting as the getaway itself: a run that ends in
        a carry that is not allowed to happen is a character lunging at
        somebody's cursor for no reason.
        """
        if not self._may_take_the_pointer():
            return False
        self.chasing = True
        self.chase_until = now + CHASE_SECONDS
        self.chase_seconds = float(seconds)
        self.target = spot
        self.docked = False
        # Held past both legs, so the wandering timer cannot pick a target of
        # its own halfway through.
        self.next_move = now + CHASE_SECONDS + seconds + 1.0
        self._wake()
        return True

    def _chase_arrived(self, now):
        """Standing on the pointer: drop the leg and take it."""
        seconds = self.chase_seconds
        self.chasing = False
        self.chase_until = 0.0
        self.chase_seconds = 0.0
        self._begin_tug(now, seconds, self._far_target((self.pos_x, self.pos_y)))

    # ── the basket ──

    def _hoop_off(self):
        """Turn the game off for good and take the drawing down.

        Reached from the two guards below. A failure inside a frame timer slot
        is the process rather than the frame, so the answer to one is to stop
        playing rather than to raise thirty times a second until somebody
        notices — which, on a mascot, is when it disappears.
        """
        self.hoop_enabled = False
        try:
            self.game.clear()
            if self.hoop_window is not None:
                self.hoop_window.hide()
        except Exception:
            return

    def _hoop_tick(self, now, dt):
        """Offer the basket, draw it, and take it away again.

        Everything the game does on a frame is inside this one guard, and the
        only part of it that can fail on a desktop rather than in arithmetic
        is the second window: a top-level window, a second sheet of images,
        and a property set on somebody else's compositor.
        """
        if not self.hoop_enabled:
            return
        try:
            self._hoop_frame(now, dt)
        except Exception:
            self._hoop_off()

    def _hoop_frame(self, now, dt):
        """One frame of the basket. See _hoop_tick for why it is wrapped."""
        if self.dragging:
            # Held long enough, and it offers a target instead of retaliating.
            # buddy_hoop answers with the basket on the frame it goes up and
            # with None on every other one, so the sentence below cannot
            # repeat once per frame for as long as the basket lasts.
            offered = self.game.offer(now, now - self.drag_started,
                                      (self.pos_x, self.pos_y),
                                      self._screen_rects())
            if offered is not None:
                self._hoop_ready().appear(offered.centre)
                self.hoop_hide_at = 0.0
                self.hoop_tries_at = self.game.state(now).misses
                self._say(self._t("hoopUp"))

        if self.game.expired(now):
            # It ran out. Which sentence depends on whether anybody threw at
            # it, and the module's own counter is what answers that: the
            # bookmark taken when it went up is the only thing kept here.
            tried = self.game.state(now).misses > self.hoop_tries_at
            self._say(self._t("hoopMissed" if tried else "hoopGone"))
            self.game.clear()
            self.hoop_hide_at = now

        window = self.hoop_window
        if window is None:
            return
        if self.game.live(now) or now < self.hoop_hide_at:
            # advance() repaints nothing while nothing is playing, so a basket
            # hanging still for twelve seconds costs no frames.
            window.advance(dt)
        elif window.isVisible():
            window.hide()

    def _hoop_ready(self):
        """The basket's window, made the first time one is offered.

        Lazily, so a companion that is never held long enough never builds a
        second window or a second sheet of images. A window that cannot be
        built raises here, which is what _hoop_tick's guard is for.
        """
        if self.hoop_window is None:
            self.hoop_window = HoopWindow()
        return self.hoop_window

    def _hoop_landed(self, start, end, now):
        """Judge one step of a flight against the basket.

        Guarded like _hoop_tick and for the same reason: this is reached from
        the frame timer, by way of _fly.
        """
        if not self.hoop_enabled:
            return
        try:
            if self.game.landed(start, end, now):
                self._hoop_scored(now)
        except Exception:
            self._hoop_off()

    def _hoop_scored(self, now):
        """It went in. The net, the pose, the sentence, and the debt cleared.

        The clearing is buddy_hoop's and not this file's: scoring is the only
        thing that forgives a throw, so playing along is the way out of the
        getaway and there is no other. Missing leaves every throw counted,
        which is why a miss says nothing here.
        """
        self.mood_clip = clip_or_fallback("celebrate")
        self.mood_until = now + MOOD_SECONDS
        self._say(self._t("hoopScored"))
        window = self.hoop_window
        if window is not None:
            window.play("score")
        # Long enough for the net to finish snapping back. The basket is
        # already gone as far as the game is concerned; this is the drawing
        # being allowed to say so.
        self.hoop_hide_at = now + HoopWindow.duration("score")

    def _hoop_ended(self, now):
        """A flight that came to rest. It scored on the way or it missed."""
        if not self.hoop_enabled or not self.game.live(now):
            return
        self.game.missed()

    def _play_once(self, name):
        """A one-shot clip, or nothing at all.

        Two guards in one place. Nothing raw ever reaches the Animator — the
        name goes through clip_or_fallback, because the sheet may not have the
        pose yet and Animator.advance looks its clip up on every frame. And a
        looping clip is never played as a one-shot: advance() leaves one only
        when its frames run out, so a fallback that resolved to a loop would
        leave the character stuck in it for good. Skipping is the same decision
        clip_or_fallback makes, one step further along.
        """
        clip = clip_or_fallback(name)
        if not sprites.CLIPS[clip]["loop"]:
            self.anim.play_once(clip)

    def _against_edge(self):
        """Whether it is standing right up against an edge of the desktop.

        Docking is what usually puts it there, and looking out past something
        only reads as looking when there is an edge to look past.
        """
        return (self.pos_x - self.min_x < SNAP_MARGIN
                or self.max_x - self.pos_x < SNAP_MARGIN
                or self.pos_y - self.min_y < SNAP_MARGIN
                or self.max_y - self.pos_y < SNAP_MARGIN)

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
        elif self.flying:
            # In the air under its own momentum. The dangle is the pose being
            # carried uses, for the same reason: nothing is under its feet.
            clip = "held"
        elif now < self.alert_until:
            clip = "alert"
        elif self.insist_clip and now < self.insist_until:
            # Above talking: the gesture is the escalation, and a session that
            # has been waiting ten minutes has already been talked at.
            clip = self.insist_clip
        elif self.chasing:
            # Running at the pointer. Above talking for the same reason the
            # mood is: the sentence and the pose are one statement, and this
            # is the leg where the pose is the whole of it — a character that
            # crosses the desktop to take your mouse wearing the walk cycle
            # is not angry, it is running an errand.
            clip = "furious"
        elif self.mood_clip and now < self.mood_until:
            # Also above talking: the pose and the sentence are one statement,
            # and the pose is the half that is read first.
            clip = self.mood_clip
        elif self.bubble:
            # `read` is the talking pose with the book in it; how often it is
            # chosen is the --memes setting, decided when the line arrived.
            clip = "read" if self.prop_line else "talk"
        elif now < self.tug_until:
            clip = "furious"
        elif moving:
            clip = "walk"
        elif self.docked and now - self.settled_at > SLEEP_AFTER:
            clip = "sleep"
        elif self.focus.silences(now):
            # Sitting out the block. Below moving, so it still walks back when
            # the block is ending.
            clip = "sit"
        elif self.docked and self._against_edge():
            # Parked against an edge, it looks out over it. Docked in a corner
            # it otherwise stands facing the wallpaper until SLEEP_AFTER.
            clip = "peek"
        elif self.working:
            # Something is running, so it types along with it, and goes back to
            # plain idle the moment nothing is.
            clip = "type"
        else:
            clip = "idle"

        # Never a raw name: the poses for focus and insistence are drawn
        # separately from this file, and the animator raises on a clip the
        # sheet has not got — inside the frame timer, which ends the process.
        clip = clip_or_fallback(clip)
        if clip == "sleep" and self.anim.base != "sleep":
            # The way into sleep, not the sleep itself. Before set_clip, so the
            # one-shot resumes into the clip that is about to be set: it used
            # to cut from standing to curled up between two frames.
            self._play_once("yawn")
        self.anim.set_clip(clip)
        # Turning around is a one-shot over whatever it is doing rather than a
        # state of its own. Without it the sprite is replaced by its own mirror
        # image between one frame and the next; with no floor under it, the
        # facing the getaway recomputes every frame would replay it endlessly.
        if self.facing != self._faced:
            self._faced = self.facing
            if not self.dragging and now - self._turned_at >= TURN_MIN_GAP:
                self._turned_at = now
                self._play_once("turn")
        # Only blink where a blink means anything. Asleep the eyes are already
        # shut, and mid-stride it is lost.
        self.anim.maybe_blink(dt, allowed=clip in ("idle", "talk"))
        self.frame = self.anim.advance(dt)

    # ── painting ──

    def paintEvent(self, _event):
        p = QPainter(self)

        # The bubble is chrome and wants smoothing; the sprite and its shadow
        # are pixel art and must not have it. Two states of the same painter,
        # in that order, with the shadow in the second one and under the feet.
        if self.bubble:
            p.setRenderHint(QPainter.Antialiasing, True)
            self._paint_bubble(p)

        p.setRenderHint(QPainter.Antialiasing, False)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        # A character being carried is off the ground and casts nothing.
        if self.options.shadow and not self.dragging:
            self._paint_shadow(p)
        frame = self.frame
        if self.dragging:
            frame = self.swing_frame() or frame
        img = self.sheet.get(frame + (":flip" if self.facing < 0 else ""))
        if img is not None:
            p.drawImage(self.bubble_pad, self.height() - BUDDY_PX, img)

        if self.focus.active:
            p.setRenderHint(QPainter.Antialiasing, True)
            self._paint_focus(p, time.monotonic())
        p.end()

    def _paint_shadow(self, p):
        """The contact shadow under the feet, which is what plants it on the desk.

        The image comes from the sheet rather than being drawn here. It is
        pixel art on the same grid as the body, so it is blitted with the same
        no-smoothing rules and lines up with the feet; an ellipse from the
        painter would be the one antialiased thing touching the sprite.

        It is a separate image and not rows inside the body grids precisely so
        that this method can decide when it appears: it must not shear with a
        dragged sprite, and a character in the air has no contact to cast it.
        Switched off entirely by --no-shadow.
        """
        image = self.sheet.get("shadow")
        if image is None:
            return          # a sheet built before the art existed
        left = self.bubble_pad + (BUDDY_PX - image.width()) // 2
        top = self.height() - image.height()
        p.drawImage(left, top, image)

    def _paint_bubble(self, p):
        w, h = self.bubble_size
        # The tail points at the character, so it turns with the side the
        # bubble opens on: on the left the bubble ends where the sprite starts.
        if self.bubble_pad:
            x, tail_in, tail_out = 0, w, w + 9
        else:
            x = BUDDY_PX + 12
            tail_in, tail_out = x, x - 9
        rect = QRectF(x, 2, w, h)

        path = QPainterPath()
        path.addRoundedRect(rect, 10, 10)
        path.moveTo(tail_in, h / 2 - 5)
        path.lineTo(tail_out, h / 2 + 2)
        path.lineTo(tail_in, h / 2 + 9)

        p.setPen(QPen(QColor(255, 255, 255, 38), 1))
        p.setBrush(QColor(28, 30, 34, 238))
        p.drawPath(path)

        p.setPen(QColor(234, 234, 234))
        p.setFont(self._bubble_font())
        p.drawText(rect.adjusted(12, 9, -12, -9),
                   Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter, self.bubble)

    def _paint_focus(self, p, now):
        """How much of the block is left, drawn inside the character's square.

        Inside it on purpose. The window's size and position carry the docking,
        the side the bubble opens on and the pointer carry; a strip added above
        the sprite would move all three for a readout. The bar drains rather
        than fills, because what the person wants off it is how long is left.
        """
        left = self.bubble_pad
        top = self.height() - BUDDY_PX
        remaining = 1.0 - self.focus.fraction(now)
        ending = self.focus.phase(now) == focus_engine.PHASE_ENDING
        colour = QColor(255, 176, 92) if ending else QColor(120, 190, 255)

        track = QRectF(left + FOCUS_BAR_INSET,
                       top + BUDDY_PX - FOCUS_BAR_H - 2,
                       BUDDY_PX - FOCUS_BAR_INSET * 2, FOCUS_BAR_H)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(18, 20, 24, 210))
        p.drawRoundedRect(track, 2, 2)
        filled = QRectF(track)
        filled.setWidth(track.width() * max(0.0, min(1.0, remaining)))
        p.setBrush(colour)
        p.drawRoundedRect(filled, 2, 2)

        label = _fmt_remaining(self.focus.remaining(now))
        font = QFont()
        font.setPointSizeF(7.0)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(18, 20, 24, 220))
        box = QRectF(left, top + 1, BUDDY_PX, 11)
        # Drawn twice, dark then light, so the number stays readable over both
        # the sprite and whatever wallpaper shows through around it.
        p.drawText(box.adjusted(1, 1, 1, 1), Qt.AlignRight | Qt.AlignVCenter, label)
        p.setPen(colour)
        p.drawText(box, Qt.AlignRight | Qt.AlignVCenter, label)

    # ── interaction ──

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            # Most important first, and the existing entries keep their order
            # below the new ones: focus is the thing the menu gets opened for.
            menu = QMenu(self)
            self._add_focus_menu(menu)
            self._add_escort_menu(menu)
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

        self._play_once("land")
        self._ensure_pointer()
        # Caught in mid-air. The flight is the character moving under its own
        # momentum, and a hand on it is the end of that by definition. The run
        # at the pointer ends the same way and for a sharper reason: the leg
        # is aimed at where the pointer was at the last release, and a hand on
        # the character means that reading is now old. The release that
        # follows decides again, with a reading of its own.
        self.flying = False
        self.chasing = False
        self.chase_until = 0.0
        self.press_pos = event.globalPosition()
        # Against the character's own top-left, not the window's. With a bubble
        # open on the left the two are a bubble's width apart, and the offset
        # taken from the window would make the sprite jump that far on the
        # first drag event.
        self.drag_offset = event.globalPosition() - QPointF(self.x() + self.bubble_pad,
                                                            self.y())
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
            self.throw_samples = []
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
        # The gesture, for the release to read a throw out of. Trimmed here
        # rather than in the module: buddy_actions.throw_velocity walks back
        # only as far as its own window, and an unbounded list would grow for
        # as long as somebody keeps dragging.
        self.throw_samples.append((time.monotonic(), new_hand[0], new_hand[1]))
        del self.throw_samples[:-actions.THROW_HISTORY]

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.OpenHandCursor)
        if self.dragging:
            self.dragging = False
            self.hand = None
            now = time.monotonic()
            self.settled_at = now
            self.recent_drags.append(now)
            self.recent_drags = [t for t in self.recent_drags if now - t <= DRAG_MEMORY]
            # A release is either a throw or a placement, and the hand's own
            # speed is what tells them apart. Below buddy_actions' floor —
            # which is this companion's walking pace — the character was being
            # put somewhere, and being put somewhere is what _snap answers,
            # docking included. Above it, it leaves the hand and falls.
            velocity = actions.throw_velocity(self.throw_samples)
            self.throw_samples = []
            thrown = velocity != (0.0, 0.0)
            if thrown:
                # Remembered, and by the module that decides what a pattern of
                # throws means. Once is the discovery that the character can
                # be thrown; twice inside buddy_hoop's memory is a decision,
                # and the answer to it is below.
                self.game.thrown(now)
                self._launch(now, velocity)
            else:
                self.vel_x = self.vel_y = 0.0
                self._snap()
                self._play_once("land")
            held_for = now - self.drag_started
            # Two tiers. Everything short of ten seconds is something you might
            # have done by accident, so it waits out the cooldown. Ten seconds
            # of holding on is not an accident, and it fires every time.
            insistent = held_for >= DRAG_TUG_ALWAYS
            provoked = (held_for >= DRAG_TUG_SECONDS
                        or self.drag_distance >= DRAG_TUG_DISTANCE
                        or len(self.recent_drags) >= DRAG_TUG_AFTER)
            # And the third: thrown more than once and it has had enough. It
            # is a provocation and not a tier of its own, under the same
            # cooldown as the drag one, because the temper remembers for
            # ninety seconds and is cleared by nothing but a basket scored —
            # so without the cooldown every release inside that window would
            # be another seven seconds of getaway.
            furious = self.game.should_chase(now)
            # A throw takes precedence over the tug within this release, and
            # _launch has already called off one that was running. Both want
            # the same position for the next few seconds — the tug drives it
            # along a Bézier at a bounded 340 px/s while a flight integrates up
            # to 2400, and the pointer is carried by whatever the character's
            # per-frame delta turns out to be — so a tug started out of a throw
            # would fling the cursor at ballistic speed, which is the one thing
            # the carry was measured not to do. What the throw no longer does
            # is forgive: it is counted above, and the next release that is not
            # itself a throw collects on it.
            #
            # The basket suspends all three while it is up. It was offered a
            # moment ago as the alternative to exactly this, and taking the
            # mouse before it has expired is the offer being withdrawn before
            # anybody could accept it. It does expire, which is what stops
            # holding the button down from being a way never to be retaliated
            # against at all.
            if (not thrown and not self.game.suspends_getaway(now)
                    and (insistent
                         or ((provoked or furious)
                             and now - self.tugged_at > TUG_COOLDOWN))):
                self.recent_drags = []
                here = (self.pos_x, self.pos_y)
                seconds = random.uniform(TUG_SECONDS - 1, TUG_SECONDS)
                # Angry, it runs to the pointer before it takes it. The
                # position is the one this release arrived with and the age is
                # measured from it, both of which buddy_hoop requires and
                # neither of which QCursor.pos() can supply: that reads
                # XWayland's shadow of the pointer, which stops following the
                # pointer while it is over a native Wayland window and cannot
                # be told apart from a pointer that is not moving. An age this
                # cannot vouch for is answered with None, and None means the
                # leg is skipped and the getaway starts from where it stands,
                # which is exactly the behaviour that shipped before this.
                spot = None
                if furious:
                    where = event.globalPosition()
                    spot = buddy_hoop.chase_target(
                        (where.x(), where.y()), time.monotonic() - now,
                        BUDDY_PX, self._corner_bounds())
                if spot is None or not self._begin_chase(now, spot, seconds):
                    self._begin_tug(now, seconds, self._far_target(here))
                self._say(self._t("tugging"))
            return
        # A click, not a drag: go to whatever most needs attention.
        self._go_to_session()

    def dragEnterEvent(self, event):
        """Take anything that carries paths; dropEvent decides what they are.

        Refusing here means no drop cursor over the character at all, which
        reads as a mascot that does not take drops. The verdict — and the
        sentence that explains it — belongs on the drop, where there is
        something concrete to say it about.
        """
        mime = event.mimeData()
        if mime is not None and mime.hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """A folder dropped on the character is a question about that repo.

        Everything in the payload is untrusted: it ends up as a working
        directory and inside a prompt. buddy_actions.dropped_repositories owns
        that judgement — what is here turns its verdict into a sentence and, at
        most, into one reading.

        Encoded rather than pretty: QUrl.toString() decodes percent escapes,
        and buddy_actions unquotes what it is given, so a folder with a literal
        % in its name would be decoded twice and name a different directory.
        """
        event.acceptProposedAction()
        mime = event.mimeData()
        uris = [] if mime is None else [bytes(url.toEncoded()) for url in mime.urls()]
        drop = actions.dropped_repositories(uris)
        if not drop.accepted:
            if drop.rejected:
                # The first reason, not all of them: a bubble is one sentence
                # wide, and a drop of six things that were all the wrong kind
                # has one thing wrong with it.
                self._say(self._drop_refusal(drop.rejected[0][1]))
            return
        if self.asking is not None:
            # The same one-at-a-time rule the menu has, and for the same
            # reason: each reading is a billed `claude -p`, and an impatient
            # hand would otherwise leave several in flight at once.
            self._say(self._t("dropBusy"))
            return
        if len(drop.accepted) > 1:
            # Refused rather than reading the first. Reading one of six and
            # ignoring the rest in silence is the same defect the rejection
            # lines exist to remove: from the outside it is indistinguishable
            # from a drop that half worked. One folder is also the only shape
            # the bubble can answer, since the answer is one paragraph about
            # one repository.
            self._say(self._t("dropOneAtATime"))
            return
        path = drop.accepted[0]
        self._ask_about({"cwd": path, "name": os.path.basename(path) or path})

    def _drop_refusal(self, reason):
        """The sentence for a rejected drop.

        Through a table with a fallback because _t looks its key up with no
        default: a reason this file has not heard of — a newer buddy_actions
        against an older companion — would otherwise be a KeyError raised
        inside a Qt event handler, which does not cost the drop, it costs the
        mascot.
        """
        return self._t(DROP_REASON_LINE.get(reason, "dropRejected"))

    def closeEvent(self, event):
        """Take the presence file with it.

        Not the same path as aboutToQuit: a window closed by the compositor
        does not necessarily end the process, and a file left behind keeps this
        companion visible to the other one for five seconds after it is gone.
        """
        self._retire()
        super().closeEvent(event)

    def _retire(self):
        """Give up the presence file.

        A method on the widget rather than the directory's own bound retire,
        which is what aboutToQuit was connected to first. PeerDirectory is not
        a QObject, so a connection to a method of one gives Qt no receiver to
        key the connection on: it would outlive the widget, and it would go on
        pointing at whichever directory object existed when it was made.
        """
        self.yard.retire()

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
        if target is None:
            rows = _session_rows(self.brain.sessions)
            target = rows[0] if rows else None
        # The pid is checked here and not left to the try below: a missing key
        # is a KeyError and a session that is a string is a TypeError, and
        # neither is in the tuple that except catches. Both are one left click
        # away, which is the mascot's only click.
        if target is None or target.get("pid") is None or not FOCUS_HELPER.exists():
            return
        try:
            subprocess.Popen([str(FOCUS_HELPER), str(target["pid"])],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        except (OSError, subprocess.SubprocessError):
            pass

    # ── the menu's own entries ──

    def _add_focus_menu(self, menu):
        """Start or end a block. The same entry either way, because there is
        never both a block to start and a block to end."""
        if self.focus.active:
            action = QAction(self._t("focusStop"), self)
            action.triggered.connect(lambda _checked=False: self.stop_focus())
        else:
            action = QAction(
                self._t("focusStart").replace("{n}", str(self.options.focus_minutes)),
                self)
            action.triggered.connect(lambda _checked=False: self.start_focus())
        menu.addAction(action)
        menu.addSeparator()

    def _add_escort_menu(self, menu):
        """Lock onto one session, or let go of the one it is locked onto.

        The lock is by pid rather than by name: two sessions open on the same
        directory have the same name, and picking one of those from a menu
        would be a coin toss over which one is escorted.
        """
        if self.escort.locked_on is not None:
            action = QAction(self._t("escortStop"), self)
            action.triggered.connect(lambda _checked=False: self._escort_release())
            menu.addAction(action)
            menu.addSeparator()
            return
        sessions = _session_rows(self.brain.sessions)
        if not sessions:
            return
        sub = menu.addMenu(self._t("escort"))
        for session, label in zip(sessions[:8], _menu_labels(sessions[:8])):
            action = QAction(label, self)
            action.triggered.connect(
                lambda _checked=False, s=session: self._escort_lock(s))
            sub.addAction(action)
        menu.addSeparator()

    def _maybe_auto_escort(self):
        """With --escort on, lock onto whatever most needs a human.

        Taken once and let go by Escort.filter itself, which releases when the
        session disappears or leaves the state it was locked in — so the next
        poll picks up the next one rather than holding a pid that is gone. A
        lock the user set by hand is never overwritten: locked_on being set is
        the whole condition.
        """
        if not self.options.escort or self.escort.locked_on is not None:
            return
        target = self.brain.attention
        if target is None:
            return
        self.escort.lock(target.get("pid"), target.get("state"))

    def _escort_lock(self, session):
        self.escort.lock(session.get("pid"))
        self._say(self._t("escorting").replace("{name}", str(session.get("name") or "?")))

    def _escort_release(self):
        self.escort.release()
        self._say(self._t("escortReleased"))

    # ── asking about a repository ──

    def _add_repo_menu(self, menu):
        """One entry per live session. User-initiated only: nothing here runs
        on a timer, because a read costs real tokens and unasked-for spending
        is not a feature."""
        sessions = _session_rows(self.brain.sessions)
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
        # After the output is read and once only: see _refilled.
        process.deleteLater()
        text, _meta = repo_brief.parse(raw)
        self._say(text or self._t("noAnswer"))

    def _say(self, text):
        """Put words in the bubble now, outside the poll cycle."""
        self.said = text
        self.bubble = text
        self.prop_line = self._roll_prop()
        self.bubble_until = time.monotonic() + SPEAK_SECONDS * 2
        self._resize_for_bubble()
        self._wake()

    def _roll_prop(self):
        """Whether this line is delivered holding something.

        Once per line, never per frame: rolled on the frame timer the book
        would flicker in and out thirty times a second. `off` never holds
        anything, which is the plain sprite the setting promises.
        """
        return random.random() < MEME_PROP_CHANCE.get(self.options.memes, 0.0)

    def _t(self, key):
        """The companion's own chrome, in both languages.

        Separate from buddy_lines.LINES on purpose: that table is what the
        character says about the desktop and is chosen by a signal. These are
        menu entries and acknowledgements of something the user just did, and
        they have exactly one wording each.
        """
        table = {
            "en": {"quit": "Quit companion", "roam": "Let it roam again",
                   "stopThat": "Put me down. I have places to be.",
                   "tugging": "Right. My turn. Come along.",
                   "hoopUp": "There is a basket over there. Use it.",
                   "hoopScored": "In. That settles it.",
                   "hoopMissed": "The basket is gone. So is your aim.",
                   "hoopGone": "Nobody threw. The basket is gone.",
                   "dropped": "...fine. Keep your mouse.",
                   "askAbout": "How is it going in...",
                   "thinking": "Looking at {name}...",
                   "noAnswer": "No answer came back. It happens.",
                   "focusStart": "Start a {n} minute focus block",
                   "focusStop": "End the focus block",
                   "focusStarted": "{n} minutes. I will be over here.",
                   "focusStopped": "Block called off. Back to it.",
                   "focusOver": "That is the block. How did it go?",
                   "focusReason": "Focus block",
                   "escort": "Stay with...",
                   "escortStop": "Stop staying with it",
                   "escorting": "Watching {name}, and nothing else.",
                   "escortReleased": "Looking around again.",
                   "dropBusy": "One at a time. I am still reading the last one.",
                   "dropOneAtATime": "One folder at a time. Pick the one you mean.",
                   "dropRejected": "I cannot open that one.",
                   "dropNotLocal": "That is not a folder on this machine.",
                   "dropUnsafe": "That path is not one I will open.",
                   "dropMissing": "There is nothing at that path any more.",
                   "dropNotAFolder": "That is a file. Drop the folder it is in.",
                   "dropNotARepo": "No .git in there. Not a repository.",
                   "dropUnreadable": "That folder will not let me look at it.",
                   "dropTooMany": "That is a lot of folders. One of them.",
                   "greetSame": "Look at that. There are two of us.",
                   "greetOther": "Well. {name} is out here too."},
            "pt": {"quit": "Fechar o companion", "roam": "Deixar passear de novo",
                   "stopThat": "Me larga. Tenho compromissos.",
                   "tugging": "Certo. Agora é a minha vez. Vem comigo.",
                   "hoopUp": "Tem uma cesta ali. Aproveita.",
                   "hoopScored": "Entrou. Ficamos quites.",
                   "hoopMissed": "A cesta foi embora. A tua mira também.",
                   "hoopGone": "Ninguém arremessou. A cesta foi embora.",
                   "dropped": "...tá bom. Fica com o teu mouse.",
                   "askAbout": "Como vai o...",
                   "thinking": "Deixa eu ver o {name}...",
                   "noAnswer": "Não veio resposta. Acontece.",
                   "focusStart": "Começar um foco de {n} minutos",
                   "focusStop": "Encerrar o foco",
                   "focusStarted": "{n} minutos. Fico aqui do lado.",
                   "focusStopped": "Foco cancelado. Voltando ao normal.",
                   "focusOver": "Acabou o bloco. Como foi?",
                   "focusReason": "Bloco de foco",
                   "escort": "Ficar de olho em...",
                   "escortStop": "Parar de acompanhar",
                   "escorting": "Só o {name}, mais nada.",
                   "escortReleased": "Voltando a olhar tudo.",
                   "dropBusy": "Uma de cada vez. Ainda estou lendo a anterior.",
                   "dropOneAtATime": "Uma pasta por vez. Escolhe qual.",
                   "dropRejected": "Essa aí eu não consigo abrir.",
                   "dropNotLocal": "Isso não é uma pasta desta máquina.",
                   "dropUnsafe": "Esse caminho eu não abro.",
                   "dropMissing": "Não tem mais nada nesse caminho.",
                   "dropNotAFolder": "Isso é um arquivo. Arrasta a pasta dele.",
                   "dropNotARepo": "Não tem .git aí dentro. Não é repositório.",
                   "dropUnreadable": "Essa pasta não me deixa olhar.",
                   "dropTooMany": "É pasta demais de uma vez. Uma só.",
                   "greetSame": "Olha só. Somos dois.",
                   "greetOther": "Opa. O {name} também anda por aqui."},
        }
        return table.get(self.lang, table["en"])[key]


def main():
    options = parse_args(sys.argv[1:])

    app = QApplication(sys.argv)
    app.setApplicationName("Usage Buddies Companion")
    app.setQuitOnLastWindowClosed(True)

    companion = Companion(options=options)
    companion.show()

    if options.self_test:
        # Proves it moves in both axes and exits: this runs where nobody is
        # around to watch, and "it walks" is the one claim worth checking.
        # The poll picks its own target when it has something to say, which
        # would overwrite the one under test. Stopping the timer is not enough:
        # __init__ also schedules a one-shot that fires regardless. The command
        # channel is silenced for the same reason: a focus block asked for by
        # the widget seconds ago would sit the character down mid-walk.
        companion.poll_timer.stop()
        companion._poll = lambda: None
        companion._command_changed = lambda *_a: None
        # And it does not mingle. A mascot already running on this desktop
        # publishes a position, and the walk under test would become a walk
        # over to say hello to it; silencing this also keeps a throwaway
        # process out of the other companions' presence directory.
        companion._mingle = lambda *_a: None
        # And no basket. Nothing drags it here, so none would be offered, but
        # the switch is set rather than reasoned about: this mode runs where
        # nobody is watching, and a second always-on-top window put up by a
        # throwaway process is the one thing it cannot be allowed to leave
        # behind on a desktop somebody is using.
        companion.hoop_enabled = False
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
