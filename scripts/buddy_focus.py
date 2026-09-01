"""Focus mode: the decisions, with no Qt, no timers and no files of its own.

Every function here takes `now` as an argument instead of reading a clock. A
companion whose logic reads the time internally can only be tested by sleeping,
and nobody runs a suite that waits ten minutes to watch an insistence ladder
climb. The engine answers questions; the companion owns the timers, the
painting and the subprocesses.

Two of the five parts were cut down by measurement rather than by design. The
idle probe and the notification inhibition both have an interface on this
machine and no working implementation behind it — see `user_idle_seconds` and
the note at the end of the file. Shipping either as if it worked would produce
code that passes with a mock and does nothing on the desktop.
"""
from __future__ import annotations

import ctypes

# ── a block of time the companion stays out of ─────────────────────────────

FOCUS_MINUTES = 25       # default block; the length a person asks for by habit
ENDING_SECONDS = 60.0    # the last minute counts as its own phase

PHASE_IDLE = "idle"
PHASE_RUNNING = "running"
PHASE_ENDING = "ending"
PHASE_DONE = "done"


class FocusSession:
    """A stretch of time during which almost nothing is worth saying.

    Four phases, not three. `idle` — no block was ever asked for — is kept
    apart from `done` — a block ran and reached its end. A clock cannot tell
    them apart and the character has opposite instructions for them: done is
    when it walks back and says the block is over, idle is when it has nothing
    to say at all. Folding them together makes the companion announce the end
    of a block that was never started, once per poll, forever.

    `ending` exists because the end of a block has to be visible before it
    happens. The companion may be parked in a corner, dozing, with its frame
    timer at the idle rate; a block that flips straight from running to done
    gives it no frames to walk back in, so the end reads as a bubble appearing
    out of nowhere. The last minute is also the window in which everything the
    block silenced can be queued up, so the alerts land as the block ends
    rather than all at once a minute later.
    """

    # What still gets through. A session with a question on screen is blocked
    # on a human being and stays blocked until one arrives; nothing else here
    # is. Quota warnings, diagnostics and ambient jokes all keep. A focus mode
    # that still tells jokes is not a focus mode, it is a smaller font.
    ALLOWED = frozenset({"asking"})

    def __init__(self):
        self.started_at = None
        self.duration = 0.0

    def start(self, now, minutes=FOCUS_MINUTES):
        """Begin a block of `minutes`. Restarting replaces the one in flight."""
        self.started_at = now
        self.duration = max(0.0, float(minutes) * 60.0)
        return self

    def cancel(self):
        """Give the block up. Back to `idle`, not to `done`: a block that was
        called off did not finish, and the character has nothing to celebrate."""
        self.started_at = None
        self.duration = 0.0

    @property
    def active(self):
        return self.started_at is not None

    def remaining(self, now):
        """Seconds left, never negative. Zero when there is no block."""
        if self.started_at is None:
            return 0.0
        return max(0.0, self.duration - (now - self.started_at))

    def fraction(self, now):
        """How much of the block is behind, 0.0 to 1.0.

        Zero with no block running, so a progress ring drawn from this is empty
        rather than full when there is nothing to show. A zero-length block is
        already over, and reads 1.0.
        """
        if self.started_at is None:
            return 0.0
        if self.duration <= 0:
            return 1.0
        return min(1.0, max(0.0, (now - self.started_at) / self.duration))

    def expired(self, now):
        if self.started_at is None:
            return False
        return now - self.started_at >= self.duration

    def phase(self, now):
        if self.started_at is None:
            return PHASE_IDLE
        if self.expired(now):
            return PHASE_DONE
        if self.remaining(now) <= ENDING_SECONDS:
            return PHASE_ENDING
        return PHASE_RUNNING

    def silences(self, now=None):
        """Whether the block is holding the companion's tongue right now.

        An expired block silences nothing: between the moment it runs out and
        the moment the companion acknowledges it there is at least one poll,
        and staying quiet through it delays every alert the block was holding.
        Called without `now` the answer is based only on a block existing,
        which is the honest reading when the caller has no time to offer.
        """
        if self.started_at is None:
            return False
        return now is None or not self.expired(now)

    def allows(self, signal_key, now=None):
        """Whether a line keyed `signal_key` may be spoken."""
        if not self.silences(now):
            return True
        return signal_key in self.ALLOWED


# ── one session at a time ──────────────────────────────────────────────────

def _same_pid(left, right):
    """Pids arrive as ints from sessions.json and as strings from anything
    that has been through a command line. Comparing them raw silently never
    matches, which looks exactly like a session that is not there."""
    if left is None or right is None:
        return False
    return str(left) == str(right)


class Escort:
    """Lock onto one session and talk about nothing else.

    The rotation in the companion's Brain is right for surveillance — with
    three sessions waiting, always naming the first turns a signal into noise
    about one repository. It is wrong for concentration: a person who has
    decided to deal with one session does not want to be told about the other
    two on the next poll.
    """

    def __init__(self):
        self._pid = None
        self._state = None

    @property
    def locked_on(self):
        return self._pid

    def lock(self, pid, state=None):
        """Hold onto `pid`. With `state` given, the hold ends by itself when
        the session leaves that state — the escort exists to see one thing
        through, and once it is through there is nothing to escort."""
        self._pid = pid
        self._state = state

    def release(self):
        self._pid = None
        self._state = None

    def filter(self, sessions):
        """The list reduced to the locked session, or the whole list.

        This is also where the lock is let go, because it is the only place the
        escort ever sees the world.

        A lock does not survive the session disappearing. Pids get reused and
        sessions.json goes stale, but neither cost compares with the failure on
        the other side: a lock on a pid that never comes back filters every
        list down to nothing, and the companion goes mute for good with no way
        for the user to tell why. Releasing on absence is self-healing, and the
        worst it does is drop an escort that has to be asked for again.
        """
        rows = list(sessions or [])
        if self._pid is None:
            return rows
        for row in rows:
            if not _same_pid(row.get("pid"), self._pid):
                continue
            if self._state is not None and row.get("state") != self._state:
                self.release()
                return rows
            return [row]
        self.release()
        return rows


# ── how hard to insist ─────────────────────────────────────────────────────

# The ladder. Each rung costs the user more than the one below it, so each one
# is bought with more waiting.
#
# 1 speak — immediately. The state has already waited: sessions-probe only
#   calls a stopped session `waiting` after SETTLED_SECONDS (20 s), so anything
#   that reaches here has been quiet long enough not to be a blink.
# 2 walk over — 2 min. Longer than a glance away for coffee; below that the
#   person is probably still at the keyboard and the bubble is enough. It is
#   also six poll cycles at POLL_MS = 20 s, so the rung cannot be reached by a
#   single bad reading.
# 3 wave over the taskbar — 5 min. This costs screen space over other windows,
#   so it should cost five minutes of a session sitting on a question.
# 4 carry the pointer — 10 min, and only if asked for. This one takes the mouse
#   out of the user's hand; ten minutes is the point at which the session is
#   plainly forgotten rather than merely waiting.
SPEAK_AFTER = 0.0
APPROACH_AFTER = 120.0
WAVE_AFTER = 300.0
POINTER_AFTER = 600.0

# The states that mean a human is the missing piece. `background` and `working`
# are the machine's problem; `idle` is news, not a summons.
WANTS_HUMAN = ("asking", "waiting")

MAX_LEVEL = 4
MAX_LEVEL_WITHOUT_POINTER = 3

# How much of a session's own reported wait counts the first time it is seen.
# A companion started at four in the afternoon may find a session that has been
# sitting on a question since lunch; beginning that one at rung 1 spends ten
# minutes talking politely about the most stuck thing on the desktop. Capped at
# the wave rung, so the pointer is never handed out on the strength of a number
# read out of a file — it has to be earned while the companion is watching.
SEED_CAP = WAVE_AFTER


def _seed(session):
    """How long this session says it has already been waiting, in seconds.

    Clamped at both ends. sessions-probe writes idleSeconds -1 when it cannot
    tell, and subtracting that puts the start of the wait a second into the
    future — the ladder would answer 0 for a session that is asking, which is
    the one state that must never be silent.
    """
    try:
        waited = float(session.get("idleSeconds"))
    except (TypeError, ValueError):
        waited = 0.0
    return min(max(waited, 0.0), SEED_CAP)


def insistence_level(seconds, allow_pointer=False):
    """The rung for a session that has wanted a human for `seconds`.

    `allow_pointer` is the opt-in for rung 4 and defaults off. Moving someone's
    pointer is destructive in the plain sense — it interrupts whatever they
    were doing with the mouse, and it cannot be undone by ignoring it — so it
    is the one rung that is never reached by waiting alone. Without the opt-in
    the ladder tops out at 3 no matter how long the session sits there.
    """
    if seconds < SPEAK_AFTER:
        return 0
    if allow_pointer and seconds >= POINTER_AFTER:
        return MAX_LEVEL
    if seconds >= WAVE_AFTER:
        return 3
    if seconds >= APPROACH_AFTER:
        return 2
    return 1


class Insistence:
    """The ladder with a memory, so it climbs and does not oscillate.

    The elapsed time cannot be read from the session's own `idleSeconds` every
    cycle: the probe recomputes that number, and it falls whenever the session
    emits anything at all, which would drop the companion from waving back to
    talking and up again. A rung that flickers produces a character having a
    seizure. So `idleSeconds` is read exactly once, to seed the clock the first
    time this sees the session in a state that wants a human, and from then on
    the clock is this one's own and the highest rung reached is remembered.
    """

    def __init__(self, allow_pointer=False):
        self.allow_pointer = allow_pointer
        self._seen = {}          # pid -> [first seen at, state, highest rung]

    def update(self, sessions, now):
        """One call per poll: {pid: rung} for every session given.

        Sessions that are gone are forgotten here rather than in a separate
        sweep, so a companion left running for days cannot accumulate an entry
        per pid that ever existed.
        """
        levels = {}
        live = set()
        for row in sessions or []:
            pid = row.get("pid")
            if pid is None:
                continue
            live.add(pid)
            state = row.get("state")
            if state not in WANTS_HUMAN:
                # Out of the state that qualified it: the ladder resets, and
                # the next summons starts from talking rather than from waving.
                self._seen.pop(pid, None)
                levels[pid] = 0
                continue
            entry = self._seen.get(pid)
            if entry is None or entry[1] != state:
                # asking -> waiting is a different summons, not a continuation:
                # the question was answered and now it has finished. Starting
                # over is the point.
                entry = [now - _seed(row), state, 0]
                self._seen[pid] = entry
            entry[2] = max(entry[2], insistence_level(now - entry[0],
                                                      self.allow_pointer))
            # Remembering the highest rung also survives a caller that hands in
            # a wall clock instead of a monotonic one and has it stepped
            # backwards by NTP. Capping on the way out rather than on the way
            # in means turning the opt-in off takes effect at once, instead of
            # leaving a remembered 4 to be handed back after the setting
            # changed.
            ceiling = MAX_LEVEL if self.allow_pointer else MAX_LEVEL_WITHOUT_POINTER
            levels[pid] = min(entry[2], ceiling)
        for pid in list(self._seen):
            if pid not in live:
                del self._seen[pid]
        return levels


# ── the hours this person actually works ───────────────────────────────────

# `lifetime.peakHours` in ~/.claude/widget-data.json is a count per hour of the
# day, as strings: {"0": 7, "9": 19, ..., "14": 76}. Hours with no activity are
# absent rather than zero.
#
# The thresholds exist to stop the companion going quiet on someone who has no
# history yet. On the machine this was written on the history reads 538
# observations over 18 distinct hours, peak 76 at 14:00 — plenty. On day one it
# reads two hours and a handful of counts, and any rule applied to that would
# declare twenty-two hours of the day out of bounds. So: below either bar the
# answer is "no idea", and no idea means do not silence anything.
QUIET_MIN_SAMPLES = 40   # about two per hour of the day, over the whole history
QUIET_MIN_HOURS = 6      # a quarter of the clock touched, so the shape means something
QUIET_SHARE = 0.10       # an hour counts as worked at a tenth of the busiest one


def peak_hours(usage):
    """{hour: count} from a widget-data payload, junk dropped.

    Every level is checked by type rather than by `or {}`. That idiom only
    catches the falsy: a collector caught mid-write, or a payload hand-edited
    to `"lifetime": 1`, is valid JSON and truthy, and `.get` on an int raises.
    This is called from the companion's poll, and the failure is not one bad
    frame — the same file is on disk next tick, so it raises every twenty
    seconds and the character never speaks again.
    """
    lifetime = usage.get("lifetime") if isinstance(usage, dict) else None
    raw = lifetime.get("peakHours") if isinstance(lifetime, dict) else None
    hours = {}
    if not isinstance(raw, dict):
        return hours
    for key, value in raw.items():
        try:
            hour, count = int(key), int(value)
        except (TypeError, ValueError):
            continue
        if 0 <= hour <= 23 and count > 0:
            hours[hour] = count
    return hours


def working_hours(hours):
    """The hours the history says are worked, or None when it cannot say.

    None rather than an empty set: "nobody works at any hour" and "there is not
    enough history to tell" are the same value otherwise, and the first one
    silences the companion around the clock.

    The share is taken against the busiest hour rather than against the total,
    so the verdict does not drift as the history grows.
    """
    if not hours:
        return None
    if sum(hours.values()) < QUIET_MIN_SAMPLES or len(hours) < QUIET_MIN_HOURS:
        return None
    floor = max(hours.values()) * QUIET_SHARE
    worked = {hour for hour, count in hours.items() if count >= floor}
    # A single hour below the bar inside a worked stretch is lunch, not the end
    # of the day. Left alone it produces a companion that shuts up for exactly
    # one hour in the middle of the afternoon, which reads as a bug rather than
    # as tact. Filled from the frozen set, so two-hour gaps cannot cascade shut.
    return worked | {hour for hour in range(24)
                     if hour not in worked
                     and (hour - 1) % 24 in worked
                     and (hour + 1) % 24 in worked}


def quiet_now(hours, hour):
    """Whether the companion should hold back at this hour of the day."""
    worked = working_hours(hours)
    if worked is None:
        return False
    return hour % 24 not in worked


# ── is the person even at the keyboard ─────────────────────────────────────

class _XScreenSaverInfo(ctypes.Structure):
    _fields_ = [("window", ctypes.c_ulong),
                ("state", ctypes.c_int),
                ("kind", ctypes.c_int),
                ("til_or_since", ctypes.c_ulong),
                ("idle", ctypes.c_ulong),
                ("event_mask", ctypes.c_ulong)]


# None = not tried, False = measured unavailable, tuple = usable handles.
# Cached because the answer cannot change while the process lives and because
# opening a display connection on a poll timer is a round trip per cycle for a
# number that would be the same.
_probe = None


def _screensaver():
    global _probe
    if _probe is not None:
        return _probe or None
    _probe = False
    try:
        x11 = ctypes.CDLL("libX11.so.6")
        xss = ctypes.CDLL("libXss.so.1")
    except OSError:
        return None
    try:
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        x11.XDefaultRootWindow.restype = ctypes.c_ulong
        x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        xss.XScreenSaverQueryExtension.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
        xss.XScreenSaverAllocInfo.restype = ctypes.POINTER(_XScreenSaverInfo)
        xss.XScreenSaverQueryInfo.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(_XScreenSaverInfo)]
        display = x11.XOpenDisplay(None)
        if not display:
            return None
        event, error = ctypes.c_int(), ctypes.c_int()
        # The extension is checked before anything is asked of it. Xlib prints
        #   Xlib: extension "MIT-SCREEN-SAVER" missing on display ":0".
        # to stderr for every QueryInfo call made without it — measured, one
        # line per call — and this runs on a timer, so the unguarded version
        # fills the journal at three lines a minute forever.
        if not xss.XScreenSaverQueryExtension(display, ctypes.byref(event),
                                              ctypes.byref(error)):
            x11.XCloseDisplay(display)
            return None
        info = xss.XScreenSaverAllocInfo()
        if not info:
            x11.XCloseDisplay(display)
            return None
    except (OSError, AttributeError, ValueError):
        return None
    _probe = (x11, xss, display, x11.XDefaultRootWindow(display), info)
    return _probe


def user_idle_seconds():
    """Seconds since the last input, or None when it cannot be measured.

    None is not zero, and the difference is the whole point. Zero means the
    person just typed, so do not interrupt. None means no idea, and the caller
    has to fall through to what it would have done without a reading. Returning
    zero for a failed measurement is how a companion goes permanently silent on
    a machine where the extension is missing — which is this machine.

    MEASURED on the desktop this was written for (Plasma on Wayland,
    XWayland display :0): libXss.so.1 is present, XOpenDisplay succeeds, and
    XScreenSaverQueryExtension returns 0. XWayland here does not carry
    MIT-SCREEN-SAVER, so this returns None on this desktop, always. The code
    stays because it is correct and costs nothing on a real X11 session, and
    because the obvious alternative measured worse: KWin publishes
    org.freedesktop.ScreenSaver.GetSessionIdleTime and answers every call to it
    with org.freedesktop.DBus.Error.NotSupported, "GetSessionIdleTime is not
    supported on this platform". There is no working idle source on this
    machine, over ctypes or over D-Bus.

    So the failing path is the measured one and the working path is not: with
    no X server on this machine carrying the extension, and no Xvfb to make
    one, nothing here has ever returned a number. Treat the reading itself as
    untested until it runs on a session that has the extension.

    Two further limits, unverifiable here for the same reason. The value the
    extension reports is milliseconds since the last input *seen by the X
    server*, so on a session where XWayland does carry the extension it still
    counts only what reached X — a native Wayland client with the keyboard may
    read as idle. And where it works at all it is per display, not per seat.
    """
    probe = _screensaver()
    if probe is None:
        return None
    _x11, xss, display, root, info = probe
    try:
        if not xss.XScreenSaverQueryInfo(display, root, info):
            return None
    except (OSError, ValueError):
        return None
    return info.contents.idle / 1000.0


# ── notification inhibition during a block: not shipped, and why ───────────
#
# Asked for: inhibit desktop notifications while a focus block runs, so the
# block is quiet all the way down rather than only in the companion's bubble.
# Not delivered, on measurement.
#
# The interface is there. org.freedesktop.Notifications, owned by plasmashell,
# introspects with Inhibit(s desktop_entry, s reason, a{sv} hints) -> u cookie
# and UnInhibit(u), and calling Inhibit returns a cookie with exit code 0.
#
# What is not there is any way for this module to hold one. An inhibition on
# these servers is bound to the caller's D-Bus connection and is dropped the
# moment it closes. Measured against the same KDE server stack, on
# org.freedesktop.PowerManagement.Inhibit because it is the one that will say
# what it is holding: HasInhibit false, Inhibit from a short-lived gdbus call
# returns cookie 67, HasInhibit false again as soon as that process exits. A
# fire-and-forget subprocess therefore returns a cookie and inhibits nothing —
# code that passes every test with a mock and does nothing on the desktop.
#
# Holding it needs a connection that outlives the call, which means QtDBus in
# the companion process, not a Qt-free engine. That is where it belongs if it
# is built.
#
# Worth knowing before it is: on this machine notifications are already
# globally inhibited. ~/.config/plasmanotifyrc has [DoNotDisturb] Until set to
# 2027-05-04, and the Inhibited property reads true with nothing of ours
# holding it — so the effect of an inhibition could not be observed here at
# all, and the feature would be a no-op on this desktop.
