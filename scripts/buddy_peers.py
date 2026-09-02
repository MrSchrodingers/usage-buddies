"""Two companions on one screen, and how each one finds out about the other.

The widget can run one companion per provider, so Clawd and Rex walk the same
desktop as two processes that share nothing. This module is the only channel
between them: a file per process in the cache, and the rules for what to do
when the distance between two of them gets small.

Everything that decides takes `now` as an argument and touches no clock and no
disk, in the shape of buddy_focus.py. The one part that does touch the disk is
`PeerDirectory`, and it is a thin wrapper over a pure reading so the awkward
cases can be tested without a filesystem.

Why files rather than the window tree — measured on this machine, both ways
working, with two companions up:

    $ xdotool search --classname usage-buddy-companion.py
    31457288
    27262984
    $ xprop -id 31457288 | grep -E 'WM_CLASS|_NET_WM_PID|_NET_WM_NAME'
    _NET_WM_NAME(UTF8_STRING) = "Usage Buddies Companion"
    _NET_WM_PID(CARDINAL) = 331882
    WM_CLASS(STRING) = "usage-buddy-companion.py", "Usage Buddies Companion"

So the X route exists: XWayland carries the windows, xdotool is installed, and
both companions are found with a pid each. It loses on three counts.

Cost. Timed from Python against those two live windows, 20 calls: the xdotool
route (one search plus getwindowpid and getwindowgeometry per window) took
23.898 ms per read, against 0.257 ms for writing one presence file and reading
the directory back — 93x. 23.9 ms is 72% of a 33 ms frame, spent on the thread
that draws the character, in three subprocess spawns.

Precision. The geometry X reports is the window, not the character. The same
two windows read 368x78 with a bubble open and 56x66 without, and the sprite
sits at the bottom-left of that box — so the X route infers a position from
another process's bubble layout, and gets it wrong by up to 300 px whenever the
other one is talking.

And it does not even remove the /proc dependency it was supposed to replace.
Brand is in no X property: both windows carry the identical class and title,
so telling Clawd from Rex still means reading /proc/<pid>/cmdline for --codex.

The presence file therefore carries what the window cannot, costs a hundredth
of the query, and works when nothing is listening on :0.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from collections import namedtuple
from pathlib import Path

SCRIPT_NAME = "usage-buddy-companion.py"

# python, python3, python3.14, pypy3 — the argv[0] of a script run through an
# interpreter. Anything else in that slot is a program operating *on* the
# file rather than running it.
_INTERPRETER = re.compile(r"^(python|pypy)[0-9.]*$")


# ── cadence ────────────────────────────────────────────────────────────────
#
# This runs inside the frame timer, which ticks at 33 ms while the character
# moves. Doing the round trip every frame would cost 0.257 ms x 30 = 7.7 ms per
# second of walking, permanently, for a joke. Once a second is 0.26 ms/s.
#
# The floor on the cadence is the distance the other one covers while the
# reading ages. A companion walks at 78 px/s (WALK_SPEED), and a position is
# stale by at most one publish interval plus one read interval, so at 1 s each
# the worst error is about 156 px. That is what sets NOTICE_RADIUS below: a
# radius near the staleness would have both sides deciding on a position the
# other has already left, and they would notice ghosts.
PUBLISH_SECONDS = 1.0
READ_SECONDS = 1.0

# How long a presence file is believed. Five publish intervals: a companion
# whose event loop is briefly busy — starting a subprocess, opening its menu —
# may miss a beat, and a corpse should still be gone within a few seconds.
# Age is checked as well as liveness because a pid can be reused, and a reused
# pid with an old file would otherwise put a peer at a position nobody is at.
STALE_SECONDS = 5.0

# A timestamp from the future is a file this machine did not write in this
# boot: monotonic clocks restart at zero on reboot, so a leftover from a long
# uptime reads as newer than anything current. The slack absorbs nothing but
# float noise between two processes reading the same clock.
CLOCK_SLACK = 1.0

MAX_BYTES = 4096          # a presence file is ~120 bytes; anything larger is junk
BRAND_MAX = 32            # a brand is "claude" or "codex"; this only bounds damage


# ── how close counts ───────────────────────────────────────────────────────
#
# Distances are between the published coordinates, which are the top-left of
# the sprite on both sides. Two sprites of the same size mean corner-to-corner
# and centre-to-centre are the same number, so this module never needs to know
# how big the character is.
#
# NOTICE_RADIUS is a bit over six sprite widths (56 px), and more than twice
# the 156 px of staleness the cadence allows.
NOTICE_RADIUS = 360.0
MEET_RADIUS = 96.0        # under two sprite widths: standing next to each other
FORGET_RADIUS = 480.0     # far enough apart to count as having walked away.
                          # Deliberately past NOTICE_RADIUS: with the two equal,
                          # a pair hovering on the boundary would alternate
                          # between parted and not on consecutive reads.

# An approach that never arrives has to end. Closing NOTICE_RADIUS takes 4.6 s
# at 78 px/s horizontally and 7.8 s at the 46 px/s climb rate, so 20 s covers a
# diagonal with room to spare. Past that the other one is not reachable — it
# was docked in a corner by the user, or it is walking away as fast as this one
# follows — and chasing it forever is worse than giving up.
APPROACH_SECONDS = 20.0

MEET_SECONDS = 6.0        # how long they stand there looking at each other

# Then they ignore each other. Without this, two characters parked side by side
# satisfy the meeting condition on every read and greet each other forever.
# The timer alone does not fix it — it makes the loop periodic instead of
# continuous — so re-noticing also requires having been apart by FORGET_RADIUS
# since. Two mascots dropped in the same corner meet exactly once.
DISINTEREST_SECONDS = 180.0

PHASE_APPROACH = "approach"   # one of them is walking over
PHASE_MEET = "meet"           # stop, turn, react
PHASE_PART = "part"           # emitted once, on the frame the meeting ends

ROLE_MOVER = "mover"          # this process is the one that walks
ROLE_WAITER = "waiter"        # this process stands still and lets it come


# What one companion knows about another. `at` is the monotonic timestamp the
# other process wrote, which is comparable here because CLOCK_MONOTONIC is
# system-wide on Linux: the same origin for every process on the machine, and
# unaffected by NTP stepping the wall clock. Measured — two unrelated python
# processes started a tenth of a second apart read 67809.915 and 67810.007.
Peer = namedtuple("Peer", "pid brand x y at")

# The pure result of reading a directory: the peers that are real, and the pids
# whose files can be deleted. The two are kept apart because a file that is
# merely old must not be deleted — its writer is alive and busy — while a file
# whose pid is not a companion any more is garbage that nobody else will clear.
Reading = namedtuple("Reading", "peers dead")

# What the companion is told about an encounter. The reaction is not decided
# here: `same_brand` and `peer.brand` are exposed so the character can pick its
# own line for meeting one of its own kind or the other provider's.
Meeting = namedtuple("Meeting", "peer phase role same_brand distance")


def presence_dir():
    """Where the presence files live. Read from the environment each call so a
    test can point XDG_CACHE_HOME somewhere harmless."""
    cache = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    return Path(cache) / "usage-buddies" / "peers"


# ── is that pid still one of us ────────────────────────────────────────────

def is_companion(pid, proc="/proc"):
    """Whether `pid` is a running companion. False for anything unclear.

    Two traps, both of which companion-ctl.sh paid for. A shebang script is
    exec'd as `/usr/bin/python3 /path/script.py`, so argv[0] is the interpreter
    and matching only argv[0] finds nothing — hence the scan over every
    argument. And a shell whose command line merely mentions the script matches
    a plain substring search; the shell that ran the measurements for this file
    was one. Matching on the basename of a whole argument rejects it, so a
    reused pid cannot make the character walk toward a window that is not there.
    """
    try:
        with open(f"{proc}/{int(pid)}/cmdline", "rb") as handle:
            argv = handle.read(MAX_BYTES)
    except (OSError, TypeError, ValueError):
        return False
    # Two shapes count, and position alone does not tell them apart. A shebang
    # script is exec'd as
    #   /usr/bin/python3 /path/usage-buddy-companion.py
    # so argv[0] is the interpreter and the script is argv[1]; matching only
    # argv[0] finds nothing, which is the mistake companion-ctl.sh documents.
    # Matching any argument is the opposite error:
    #   cp scripts/usage-buddy-companion.py ~/.local/bin/
    # is install.sh running, and it answers yes. So does `vim` on the file,
    # which is argv[1] like the real thing — the position is identical and
    # only argv[0] separates them. The rule is therefore about who is running:
    # the script as its own argv[0], or an interpreter running the script.
    parts = []
    for part in [p for p in argv.split(b"\0") if p][:2]:
        try:
            parts.append(os.path.basename(part.decode("utf-8", "replace")))
        except (AttributeError, UnicodeError):
            return False
    if not parts:
        return False
    if parts[0] == SCRIPT_NAME:
        return True
    return (len(parts) > 1 and parts[1] == SCRIPT_NAME
            and _INTERPRETER.match(parts[0]) is not None)


# ── reading the files, with no files ───────────────────────────────────────

def decode(pid, raw, now, stale=STALE_SECONDS):
    """One presence file as a Peer, or None. Never raises, for any input.

    This is called from a QTimer. An exception here does not print a stack and
    carry on — it stops the frame that was painting the character, so the
    mascot freezes because some other process was killed mid-write. Every
    reason to disbelieve a file therefore returns None: truncation, a partial
    write, a dict where a number was expected, a payload naming a different
    pid, a timestamp too old or from before the last reboot.

    NaN and Infinity parse fine as JSON — measured, `json.loads(b"NaN")`
    returns nan and `b"1e999"` returns inf — and a NaN coordinate makes every
    distance comparison false, which reads as the feature silently not working.
    Hence the isfinite check rather than a bare float().
    """
    if isinstance(raw, (bytes, bytearray)):
        raw = bytes(raw[:MAX_BYTES])
    elif isinstance(raw, str):
        raw = raw[:MAX_BYTES]
    else:
        return None
    try:
        row = json.loads(raw)
    except (ValueError, TypeError, RecursionError):
        # ValueError covers a truncated file, invalid utf-8 and nesting deep
        # enough to trip the scanner's own guard — all measured. RecursionError
        # is for the pure-Python fallback, which raises that instead.
        return None
    if not isinstance(row, dict):
        return None

    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    # The filename is the authority; a payload that disagrees with it is a file
    # that was copied rather than written, and its position belongs to nobody.
    if "pid" in row:
        try:
            if int(row["pid"]) != pid:
                return None
        except (TypeError, ValueError):
            return None

    brand = row.get("brand")
    if not isinstance(brand, str) or not brand or len(brand) > BRAND_MAX:
        return None

    numbers = []
    for key in ("x", "y", "at"):
        value = row.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        value = float(value)
        if not math.isfinite(value):
            return None
        numbers.append(value)
    x, y, at = numbers

    age = now - at
    if age > stale or age < -CLOCK_SLACK:
        return None
    return Peer(pid, brand, x, y, at)


def collect(entries, now, alive=is_companion, stale=STALE_SECONDS):
    """A Reading from `entries`, an iterable of (pid, raw) pairs.

    The whole of the reading logic, with the directory left to the caller. A
    pid that is not a live companion produces no peer and is reported as dead,
    which is the only condition under which a file is deleted: an old file
    belonging to a live companion is a busy process, not a corpse.
    """
    peers, dead = [], []
    for pid, raw in entries:
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            continue
        if not alive(pid):
            dead.append(pid)
            continue
        peer = decode(pid, raw, now, stale)
        if peer is not None:
            peers.append(peer)
    return Reading(peers, dead)


class PeerDirectory:
    """The files themselves: one per process, written by it and read by the rest.

    Both halves are on a cadence, and inside it neither one touches the disk.
    """

    def __init__(self, path=None, pid=None, proc="/proc"):
        self.path = Path(path) if path is not None else presence_dir()
        self.pid = int(pid) if pid is not None else os.getpid()
        self.proc = proc
        self._peers = []
        self._read_at = None
        self._wrote_at = None

    # -- writing ours --

    def publish(self, brand, x, y, now, interval=PUBLISH_SECONDS):
        """Say where this companion is, at most once per `interval`.

        Returns where it is either way, so the caller can hand the same value
        to `Encounter.update` without caring whether a write happened.

        Written to a temporary name in the same directory and renamed over the
        real one, because rename within a filesystem is atomic: a reader can
        see the old file or the new one, never half of either. Writing in place
        would hand a truncated file to whoever read during the write, several
        times a minute, forever.
        """
        me = Peer(self.pid, brand, float(x), float(y), float(now))
        if self._wrote_at is not None and now - self._wrote_at < interval:
            return me
        self._wrote_at = now
        payload = json.dumps({"pid": me.pid, "brand": me.brand,
                              "x": me.x, "y": me.y, "at": me.at})
        tmp = self.path / f".{self.pid}.tmp"
        try:
            # 0700 and 0600, which is what every other writer in this cache
            # uses. mkdir's mode applies only when it creates the directory,
            # and exist_ok leaves an existing one alone — so whichever program
            # gets there first on a fresh install decides the mode for good,
            # and this one was arriving with the default 0755.
            self.path.mkdir(parents=True, exist_ok=True, mode=0o700)
            with open(tmp, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path / f"{self.pid}.json")
        except OSError:
            # A read-only or missing cache is not worth a crash: without a file
            # this companion is invisible to the others and carries on alone.
            try:
                os.unlink(tmp)
            except OSError:
                pass
        return me

    def retire(self):
        """Remove our file on the way out, so nobody waits STALE_SECONDS for a
        companion the user has already closed."""
        try:
            os.unlink(self.path / f"{self.pid}.json")
        except OSError:
            pass

    # -- reading theirs --

    def peers(self, now, interval=READ_SECONDS):
        """Everyone else, from cache unless `interval` has passed.

        Inside the interval this performs no system call at all: the point of
        the cadence is that a character standing still costs nothing.
        """
        if self._read_at is not None and now - self._read_at < interval:
            return self._peers
        self._read_at = now
        reading = collect(self._entries(), now,
                          alive=lambda pid: is_companion(pid, self.proc))
        for pid in reading.dead:
            # Nobody else will clear these. A companion killed with SIGKILL
            # never runs `retire`, and left alone the directory grows one file
            # per pid that ever ran one, which the scan then pays for every
            # second. Only pids that failed the liveness check are removed, so
            # this cannot delete a live companion's file out from under it.
            try:
                os.unlink(self.path / f"{pid}.json")
            except OSError:
                pass
        self._peers = reading.peers
        return self._peers

    def _entries(self):
        """(pid, raw) for every presence file but ours. Errors are absences."""
        try:
            listing = list(os.scandir(self.path))
        except OSError:
            return []
        out = []
        for entry in listing:
            name = entry.name
            if not name.endswith(".json"):
                continue
            try:
                pid = int(name[:-5])
            except ValueError:
                continue
            if pid == self.pid:
                continue
            try:
                with open(entry.path, "rb") as handle:
                    out.append((pid, handle.read(MAX_BYTES)))
            except OSError:
                continue        # deleted between the scan and the open
        return out


# ── who is near, and who goes ──────────────────────────────────────────────

def distance(here, there):
    """Between two things with .x and .y. Infinite when either is unusable, so
    an unreadable peer is never the nearest one."""
    try:
        span = math.hypot(float(there.x) - float(here.x),
                          float(there.y) - float(here.y))
    except (AttributeError, TypeError, ValueError):
        return math.inf
    return span if math.isfinite(span) else math.inf


def nearby(me, peers, radius=NOTICE_RADIUS):
    """The peers close enough to be noticed, nearest first.

    Our own pid is dropped even though PeerDirectory already excludes it: a
    character that notices itself would stop dead and stare at nothing.
    """
    close = [p for p in (peers or [])
             if p.pid != me.pid and distance(me, p) <= radius]
    return sorted(close, key=lambda p: (distance(me, p), p.pid))


def approaches(mine, theirs):
    """Whether this process is the one that walks over.

    Two processes that both decide to approach chase each other across the
    screen, and two that both decide to wait stand there. The tie is broken by
    the smaller pid with no message between them: both sides compute this from
    the same pair of numbers and reach opposite, matching answers. Pids are
    unique among live processes, which is all this needs.
    """
    try:
        return int(mine) < int(theirs)
    except (TypeError, ValueError):
        return False


class Encounter:
    """The meeting, as a state machine one poll wide.

    Approach, meet, part, then a stretch of not caring. The last one is the
    whole reason this is a state machine rather than a distance check: without
    it every read of two adjacent characters is a fresh introduction.
    """

    def __init__(self):
        self._pid = None          # the peer this is about, if any
        self._phase = None
        self._since = 0.0
        self._closed = {}         # pid -> [when it ended, have they parted since]

    @property
    def busy(self):
        """Whether an encounter is in flight. The companion suspends its own
        wandering while this is true."""
        return self._pid is not None

    def update(self, me, peers, now):
        """One call per frame: a Meeting to act on, or None.

        `me` is a Peer for this process — `PeerDirectory.publish` returns one.
        """
        seen = {p.pid: p for p in (peers or []) if p.pid != me.pid}
        self._age_cooldowns(me, seen, now)

        if self._pid is not None:
            meeting = self._continue(me, seen, now)
            if meeting is not None:
                return meeting

        return self._begin(me, seen, now)

    # -- internals --

    def _age_cooldowns(self, me, seen, now):
        """Track separation, and forget pairs that no longer need remembering.

        A peer that has vanished from the directory counts as parted: it walked
        off, or the process is gone. Entries are dropped once both conditions
        are satisfied, so a companion left running for days does not keep one
        record per pid it has ever stood next to.
        """
        for pid, state in list(self._closed.items()):
            peer = seen.get(pid)
            if peer is None or distance(me, peer) > FORGET_RADIUS:
                state[1] = True
            if state[1] and now - state[0] >= DISINTEREST_SECONDS:
                del self._closed[pid]

    def _blocked(self, pid, now):
        state = self._closed.get(pid)
        if state is None:
            return False
        return not state[1] or now - state[0] < DISINTEREST_SECONDS

    def _close(self, me, peer, now):
        """End the encounter and start ignoring that peer. Returns the one
        PHASE_PART the caller gets, so the character knows to walk on."""
        self._pid = None
        self._phase = None
        span = distance(me, peer)
        self._closed[peer.pid] = [now, span > FORGET_RADIUS]
        return Meeting(peer, PHASE_PART, self._role(me, peer),
                       peer.brand == me.brand, span)

    def _role(self, me, peer):
        return ROLE_MOVER if approaches(me.pid, peer.pid) else ROLE_WAITER

    def _continue(self, me, seen, now):
        peer = seen.get(self._pid)
        if peer is None:
            # It stopped publishing: closed, killed, or its cache went away.
            # Ending the encounter is what releases the character to wander.
            # Recorded as parted, because a peer that is not there is not near.
            self._closed[self._pid] = [now, True]
            self._pid = None
            self._phase = None
            return None

        span = distance(me, peer)
        if self._phase == PHASE_APPROACH:
            if span <= MEET_RADIUS:
                self._phase, self._since = PHASE_MEET, now
            elif now - self._since >= APPROACH_SECONDS:
                return self._close(me, peer, now)
        elif self._phase == PHASE_MEET and (now - self._since >= MEET_SECONDS
                                            or span > FORGET_RADIUS):
            # Time is up, or one of them was picked up and carried off while
            # they were standing there.
            return self._close(me, peer, now)

        return Meeting(peer, self._phase, self._role(me, peer),
                       peer.brand == me.brand, span)

    def _begin(self, me, seen, now):
        for peer in nearby(me, list(seen.values())):
            if self._blocked(peer.pid, now):
                continue
            self._pid = peer.pid
            span = distance(me, peer)
            # Already touching: there is nothing to approach, and pretending
            # otherwise leaves the pair in APPROACH until it times out.
            self._phase = PHASE_MEET if span <= MEET_RADIUS else PHASE_APPROACH
            self._since = now
            return Meeting(peer, self._phase, self._role(me, peer),
                           peer.brand == me.brand, span)
        return None


def now():
    """The clock the timestamps are on, in one place. Monotonic rather than
    wall: NTP stepping the clock backwards would put every peer in the future
    and make the whole desktop's companions invisible to each other."""
    return time.monotonic()
