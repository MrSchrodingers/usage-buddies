"""Four things the companion can do, with the decisions kept out of Qt.

Same shape as buddy_focus: no Qt, no timers, time and geometry arrive as
arguments, and anything the module cannot know is None rather than a plausible
number. The companion owns the frame clock, the window and the subprocesses;
this owns the arithmetic and the verdicts.

The four:

  throw      — a release in mid-drag becomes a velocity, and a velocity becomes
               a fall with bounces that ends.
  drop       — a folder dragged onto the character becomes a path, or a reason
               why it did not. Everything here is untrusted input: what comes
               out is used as a working directory and pasted into a prompt.
  perch      — where to sit so the character reads as resting on a window, and
               how to get that window's geometry from KWin.
  delivery   — where to walk so a carried pointer lands on the window that
               wants a human, and when not to take the pointer at all.

The coordinate convention is the companion's own and is the same throughout:
positions are the sprite's top-left corner, and `bounds` is the rectangle of
allowed top-left corners, (min_x, min_y, max_x, max_y) — already inset by the
sprite size, exactly as Companion.min_x .. max_y are. The visible area is that
rectangle grown by one sprite on the right and bottom.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
from collections import namedtuple
from urllib.parse import unquote, urlsplit

# ── throwing it across the room ────────────────────────────────────────────

# How much of the drag counts. A person who drags slowly and whips at the end
# is throwing; the average of the whole drag says they were strolling, and the
# character leaves the hand at walking pace. Ninety milliseconds is three
# frames at the companion's active rate (33 ms) and five or six mouse move
# events at 60 Hz — long enough not to be one jittery reading, short enough
# that only the last gesture is in it.
THROW_WINDOW = 0.09

# What the caller has to keep. At 60 Hz this is a quarter of a second of
# history, which is more than THROW_WINDOW needs even when frames are dropped.
THROW_HISTORY = 16

# Below this the release was a placement, not a throw. The number is the
# companion's own WALK_SPEED (78 px/s) rounded up: a hand moving slower than
# the character walks was putting it down, and launching it from there looks
# like the sprite slipping out of your fingers.
THROW_MIN_SPEED = 90.0

# The ceiling, and why it is not optional. Three pixels in one millisecond
# extrapolates to 3000 px/s, and at the active frame rate that is 99 px per
# frame — nearly two sprites — so the character crosses the desktop measured
# here (4115 px across two monitors) in 1.4 s and is off the far edge before
# anyone sees it leave. 2400 px/s covers that same desktop in 1.7 s and moves
# 79 px per frame, which is a fast blur rather than a teleport.
THROW_MAX_SPEED = 2400.0

# Downward pull. Chosen from the arc rather than from physics: at the speed
# ceiling a straight-up throw rises 1516 px (v^2/2g), which just clears the
# tallest screen here (1234 px), so even the hardest throw comes back inside
# about a second and a half. Weaker gravity parks the character on the ceiling
# and reads as floating; stronger makes every throw a short hop.
GRAVITY = 1900.0

# Air, per 1/60 s so the feel does not change with the frame rate — the same
# convention as SWING_DAMPING and WOBBLE_DAMP in the companion. 0.995 leaves
# 74% of the speed after a second, which is enough to guarantee the flight
# ends without collisions and little enough to be invisible during one.
AIR_DRAG = 0.995

# What a wall gives back. Below 1 or it bounces for ever; 0.55 means a drop
# from the top of a 1234 px screen bounces about five times over three and a
# half seconds before the floor rule below ends it.
RESTITUTION = 0.55

# What a wall takes from the direction it did not reflect: an impact scrubs
# speed along the surface as well as into it, so a throw into the floor slides
# rather than skating off at the speed it arrived with.
WALL_FRICTION = 0.86

# Ground friction while resting on the floor, again per 1/60 s. 0.95 leaves 5%
# of the speed after a second, so a landing skids for about half a second.
GROUND_DRAG = 0.95

# An impact slower than this does not bounce, it lands. 120 px/s is the speed
# reached by falling 3.8 px; a bounce that small is under two sprite pixels and
# reads as the character vibrating on the floor, not bouncing on it.
SETTLE_BOUNCE = 120.0

# And resting on the floor slower than this is stopped. The companion snaps its
# window to the 2 px sprite grid and animates at 33 ms, so 60 px/s is one grid
# step per frame: below it two consecutive frames round to the same position
# and the movement cannot be drawn at all.
SETTLE_SPEED = 60.0

# The longest step that gets integrated in one go. The idle frame timer runs at
# 200 ms and a stalled process can hand in far worse; at 2400 px/s a 200 ms
# step moves 480 px, which tunnels straight through a wall and out of the
# screen. 0.05 s is three frames at the active rate — a hitch, not a stall.
MAX_STEP = 0.05

Step = namedtuple("Step", "x y vx vy resting bounced")


def _samples(rows):
    """(t, x, y) triples that are actually numbers, in the order given."""
    clean = []
    for row in rows or ():
        try:
            t, x, y = row[0], row[1], row[2]
            clean.append((float(t), float(x), float(y)))
        except (TypeError, ValueError, IndexError, KeyError):
            continue
    return clean


def throw_velocity(samples, window=THROW_WINDOW, cap=THROW_MAX_SPEED):
    """Speed at the moment of release, in px/s, from recent drag samples.

    Zero, never None. Releasing without having moved is a legitimate thing to
    do and its answer is a number — it means "no throw" — while None would
    mean "cannot tell" and force every caller to invent a fallback for a case
    that is not ambiguous at all.

    The estimate is a displacement over the time it took, taken over the last
    `window` seconds of the drag and no more. Fitting the whole drag, or
    averaging every sample in it, makes the slow part of a slow-then-fast
    gesture cancel the fast part, which is precisely backwards: the last thing
    the hand did is the throw.

    Walking back until the window is covered, rather than taking the last two
    samples, is also what keeps the time base honest. Two events a millisecond
    apart are a legitimate reading of nothing, and dividing three pixels by
    them produces a launch. Where there is nothing older to widen to, `cap`
    is the remaining defence.
    """
    rows = _samples(samples)
    if len(rows) < 2:
        return (0.0, 0.0)

    last_t, last_x, last_y = rows[-1]
    first = rows[0]
    for row in reversed(rows[:-1]):
        first = row
        if last_t - row[0] >= window:
            break

    span = last_t - first[0]
    if span <= 0:
        # Time did not advance, or went backwards. No division is defensible.
        return (0.0, 0.0)

    vx = (last_x - first[1]) / span
    vy = (last_y - first[2]) / span
    speed = math.hypot(vx, vy)
    if speed < THROW_MIN_SPEED:
        return (0.0, 0.0)
    if speed > cap:
        # Scaled, not clamped per axis: clamping each axis on its own turns a
        # diagonal throw into a differently angled one.
        vx, vy = vx * cap / speed, vy * cap / speed
    return (vx, vy)


def integrate(pos, vel, dt, bounds):
    """One step of the flight: gravity, air, walls, and knowing when to stop.

    Deterministic — nothing in here is random — so a test can assert the whole
    trajectory rather than a property of it.

    Returns the new position and velocity, plus two flags. `resting` is the
    caller's signal to stop stepping and hand the character back to walking; it
    has to exist, because restitution alone leaves the body bouncing at ever
    smaller amplitude for ever and a companion that never stops falling never
    walks again. `bounced` marks a real impact — the ones worth a squash — and
    is deliberately not raised by the every-frame contact of a body already
    lying on the floor, or the landing clip would replay for ever too.
    """
    min_x, min_y, max_x, max_y = (float(b) for b in bounds)
    x, y = float(pos[0]), float(pos[1])
    vx, vy = float(vel[0]), float(vel[1])
    dt = min(max(float(dt), 0.0), MAX_STEP)
    if dt <= 0:
        return Step(x, y, vx, vy, False, False)

    vy += GRAVITY * dt
    damp = AIR_DRAG ** (dt * 60.0)
    vx *= damp
    vy *= damp

    x += vx * dt
    y += vy * dt

    # A wall reflects what is coming at it and scrubs what is sliding along it,
    # but only above SETTLE_BOUNCE. Below that an impact is a landing: reflect
    # it and the body hums against the floor for ever, because gravity puts
    # back every frame most of what the floor just took, and scrub along it and
    # a throw that skims the ground stops dead in a fifth of a second.
    bounced = False
    if x <= min_x and vx < 0:
        x = min_x
        if -vx >= SETTLE_BOUNCE:
            vx, vy, bounced = -vx * RESTITUTION, vy * WALL_FRICTION, True
        else:
            vx = 0.0
    elif x >= max_x and vx > 0:
        x = max_x
        if vx >= SETTLE_BOUNCE:
            vx, vy, bounced = -vx * RESTITUTION, vy * WALL_FRICTION, True
        else:
            vx = 0.0
    if y <= min_y and vy < 0:
        y = min_y
        if -vy >= SETTLE_BOUNCE:
            vy, vx, bounced = -vy * RESTITUTION, vx * WALL_FRICTION, True
        else:
            vy = 0.0
    elif y >= max_y and vy > 0:
        y = max_y
        if vy >= SETTLE_BOUNCE:
            vy, vx, bounced = -vy * RESTITUTION, vx * WALL_FRICTION, True
        else:
            vy = 0.0

    x = max(min_x, min(max_x, x))
    y = max(min_y, min(max_y, y))

    on_floor = y >= max_y and vy == 0.0
    if on_floor:
        vx *= GROUND_DRAG ** (dt * 60.0)
    resting = on_floor and abs(vx) < SETTLE_SPEED
    if resting:
        vx = 0.0
    return Step(x, y, vx, vy, resting, bounced)


# ── a folder dropped on the character ──────────────────────────────────────

# How many folders one drop may start work on. The right-click menu already
# stops at eight sessions, so eight is this codebase's existing idea of how
# many things a person picks at once; and each accepted folder becomes a
# `claude -p` run that costs money, so a selection of four hundred must not be
# four hundred processes.
DROP_LIMIT = 8

# Rejection reasons are keys, not sentences: the companion speaks two
# languages and the wording belongs in its table, not here.
REASON_NOT_LOCAL = "notLocal"           # not file://, or a file:// on a host
REASON_UNSAFE = "unsafePath"            # relative, .. inside it, control chars
REASON_MISSING = "missing"              # nothing at that path
REASON_NOT_A_FOLDER = "notAFolder"      # a file, a socket, a device
REASON_NOT_A_REPOSITORY = "notARepo"    # a folder, but not one with a .git
REASON_UNREADABLE = "unreadable"        # there, and refused to be looked at
REASON_TOO_MANY = "tooMany"             # past DROP_LIMIT in one drop

Drop = namedtuple("Drop", "accepted rejected")


def _uri_lines(uris):
    """The drop payload as a list of URIs.

    QMimeData hands this over either as a list of URL strings or as one
    text/uri-list blob, which is CRLF separated and may carry comment lines.
    Both arrive here, so both are handled; splitting on any newline also means
    a single string that smuggled a second URI into itself cannot be treated
    as one path.
    """
    if isinstance(uris, (str, bytes)):
        raw = uris.decode("utf-8", "replace") if isinstance(uris, bytes) else uris
        items = raw.splitlines()
    else:
        items = []
        for item in uris or ():
            text = item.decode("utf-8", "replace") if isinstance(item, bytes) else item
            if not isinstance(text, str):
                continue
            items.extend(text.splitlines())
    return [line.strip() for line in items
            if line.strip() and not line.strip().startswith("#")]


def _path_from_uri(uri):
    """(path, reason). Exactly one of the two is None.

    String rules only — no filesystem is touched here, so a drop of four
    hundred URIs costs four hundred string operations and nothing else.

    Nothing in here expands anything. `~`, `$HOME` and `%USERPROFILE%` are
    ordinary characters in a path; a URI that contains them is a URI that
    names a directory with a strange name, and expanding it would let the
    contents of a dropped string choose a directory it never named.
    """
    # Before urlsplit, because urlsplit answers by discarding. A path that
    # contains `#` or `?` comes back truncated at that character, and the
    # truncation is not an error: `file:///work/src/#scratch` parses to
    # `/work/src`, which exists, is a repository, and is not what anyone
    # dragged. Rejecting is the same choice `..` gets below and for the same
    # reason — a URI whose meaning depends on how it was split is one this
    # module must not resolve on the dropper's behalf. A conforming file
    # manager percent-encodes both characters, so a raw one means the URI was
    # assembled by something else.
    if "#" in uri or "?" in uri:
        return None, REASON_UNSAFE

    parts = urlsplit(uri)
    if parts.scheme != "file":
        # Covers http, data, and a bare relative path, which has no scheme.
        return None, REASON_NOT_LOCAL
    if parts.netloc and parts.netloc.lower() != "localhost":
        # file://host/path is a file on `host`. There is no such directory
        # here, and resolving it locally would silently open a different one.
        return None, REASON_NOT_LOCAL

    path = unquote(parts.path)
    if not path.startswith("/"):
        return None, REASON_UNSAFE
    if any(ch in path for ch in ("\x00", "\n", "\r")):
        # A newline in a path breaks every line-oriented thing downstream, and
        # this string ends up inside a prompt. A NUL truncates it in C.
        return None, REASON_UNSAFE
    if any(ch == ".." for ch in path.split("/")):
        # Rejected rather than normalised. No file manager emits a drop with
        # `..` in it, so its presence means the URI was assembled by something
        # else, and a path that has to be normalised before it can be checked
        # is one whose meaning depends on when you look at it.
        return None, REASON_UNSAFE
    return path, None


def dropped_repositories(uris, limit=DROP_LIMIT, require_repo=True):
    """Which of these dropped URIs are repositories, and why the rest are not.

    Returns (accepted, rejected): a list of absolute paths, and a list of
    (uri, reason) pairs. The reasons exist so the character can say "that is
    not a repository" — a drop that is ignored in silence is indistinguishable
    from one the mascot did not notice.

    Symlinks are resolved and the target is accepted, not the link. Dropping a
    link to a repository is a normal way to keep one, so refusing it would
    reject real work; but what comes back is the resolved path, so the caller
    hands the subprocess the directory that was actually checked rather than a
    name that can be repointed between the check and the use.

    `require_repo` is what keeps this from being a way to run `claude -p` in
    an arbitrary directory: `/`, `/etc` and a downloads folder all fail it. A
    caller that turns it off gets any existing directory and owns that choice.
    """
    accepted, rejected = [], []
    looked = 0
    for uri in _uri_lines(uris):
        path, reason = _path_from_uri(uri)
        if reason is not None:
            rejected.append((uri, reason))
            continue
        if looked >= limit:
            # Counted against what was looked at, not against what passed. The
            # comment here used to promise that past the limit nothing touches
            # the disk, and the code counted accepted entries — so a drop of
            # twenty thousand ordinary folders accepted none, never reached the
            # limit, and made eighty thousand filesystem calls in 433 ms on the
            # Qt thread. That is the stat storm this exists to prevent, and it
            # was measured doing it.
            rejected.append((uri, REASON_TOO_MANY))
            continue
        looked += 1
        try:
            real = os.path.realpath(path)
            if not os.path.exists(real):
                rejected.append((uri, REASON_MISSING))
                continue
            if not os.path.isdir(real):
                rejected.append((uri, REASON_NOT_A_FOLDER))
                continue
            if require_repo and not os.path.exists(os.path.join(real, ".git")):
                # A file rather than a directory when the repository is a
                # worktree or a submodule, so `exists` and not `isdir`.
                rejected.append((uri, REASON_NOT_A_REPOSITORY))
                continue
        except OSError:
            rejected.append((uri, REASON_UNREADABLE))
            continue
        if real not in accepted:
            accepted.append(real)
    return Drop(accepted, rejected)


# ── sitting on a window ────────────────────────────────────────────────────

# How far the feet sink into the title bar. At SCALE 2 this is two source
# pixels of overlap, which is the difference between sitting on the bar and
# hovering above it.
PERCH_SINK = 4


def _rect(window):
    """(left, top, width, height) from a geometry mapping or a 4-sequence."""
    if window is None:
        return None
    try:
        if hasattr(window, "get"):
            left = float(window["x"])
            top = float(window["y"])
            width = float(window["width"])
            height = float(window["height"])
        else:
            left, top, width, height = (float(v) for v in window)
    except (TypeError, ValueError, KeyError, IndexError):
        return None
    if width <= 0 or height <= 0:
        return None
    return left, top, width, height


def perch_position(window, sprite_px, bounds):
    """Where to stand so the character reads as sitting on this window.

    None when there is nothing to sit on: no geometry, a degenerate rectangle,
    a minimised window, or one entirely off the visible area. The caller has a
    perfectly good default — carry on walking — and a made-up position would
    put the character on empty desktop looking like a bug.

    The hard cases, and what each one does:

      maximised          — the title bar is at the very top of the screen and
                           there is no room above it, so the clamp leaves the
                           character sitting *in* the bar rather than on it,
                           which is the only visible option.
      partly off-screen  — it perches over the middle of the part that can be
                           seen, not the middle of the window, so it does not
                           walk off the edge to sit above a corner nobody has.
      narrower than the
      sprite             — centred anyway, overhanging both ends evenly. A
                           sprite pushed inside a 40 px window would sit off
                           the bar entirely.
      bar off-screen     — clamped back into bounds; a perch nobody can see is
                           the same as no perch, and the character would be
                           missing for as long as it lasted.
    """
    rect = _rect(window)
    if rect is None:
        return None
    if hasattr(window, "get") and window.get("minimized"):
        return None
    sprite = float(sprite_px)
    min_x, min_y, max_x, max_y = (float(b) for b in bounds)
    left, top, width, height = rect

    # bounds holds top-left corners, so the visible area extends one sprite
    # further right and further down than the last legal corner.
    screen_left, screen_top = min_x, min_y
    screen_right, screen_bottom = max_x + sprite, max_y + sprite
    if left + width <= screen_left or left >= screen_right:
        return None
    if top + height <= screen_top or top >= screen_bottom:
        return None

    visible_left = max(left, screen_left)
    visible_right = min(left + width, screen_right)
    x = (visible_left + visible_right) / 2.0 - sprite / 2.0
    y = top - sprite + PERCH_SINK
    return (max(min_x, min(max_x, x)), max(min_y, min(max_y, y)))


# ── which window belongs to a session ──────────────────────────────────────
#
# MEASURED on this machine, Plasma 6 on Wayland, and the measurement is why the
# route below is not the one focus-session.sh uses.
#
# focus-session.sh loads a KWin script and that works for *acting* on a window.
# It has no way of getting an answer back: a script that collects geometry and
# prints it was loaded (loadScript returned an id) and started, and no line of
# its output appeared anywhere in the journal — kwin_wayland's own logging is
# there, but script print() is not in it. The scripting engine has no file
# access, so there is nothing else to write to.
#
# What does answer, over plain D-Bus, is two calls that need no script at all:
#
#   busctl --user call org.kde.KWin /WindowsRunner org.kde.krunner1 \
#          Match s "" --json=short
#   -> {"type":"a(sssida{sv})","data":[[["0_{79b1c95a-...}", "caption", ...]]]}
#
#   busctl --user call org.kde.KWin /KWin org.kde.KWin \
#          getWindowInfo s "{79b1c95a-...}" --json=short
#   -> {"pid":{"type":"i","data":30547}, "x":{"type":"d","data":0.0},
#       "width":{"type":"d","data":2194.285714285714}, ...}
#
# An empty query to the windows runner enumerates every window, with duplicates
# (18 rows, 10 distinct ids here) and a couple of ids that are desktops rather
# than windows and answer getWindowInfo with an empty map. Timed here: 22 ms
# for the enumeration and about 6 ms per window, 38-54 ms end to end for a real
# session pid, which is fine on a poll and far too slow for a frame.
#
# busctl rather than qdbus-qt6 because of --json=short. qdbus-qt6 cannot print
# the runner's return type at all ("I don't know how to display an argument of
# type 'a(sssida{sv})'"), and its output for the geometry map is `key: value`
# lines — a window caption is attacker-influenced text that can contain a
# newline, and a caption carrying "pid: 1" would be indistinguishable from the
# real field. JSON has one unambiguous parse.
#
# The coordinate spaces agree, which is the other thing that had to be checked.
# KWin reports this desktop as HDMI-A-1 at (0, 0, 2194.3, 1234) — a 0.875 scale
# on a 1920x1080 panel, rotated — and eDP-1 at (2195, 0, 1920, 1200). Qt on the
# xcb platform, which is what the companion runs on, reports exactly the same
# two rectangles: (0,0,2194,1234) and (2195,0,1920,1200). So geometry from KWin
# can be compared with the companion's own position without conversion.

KWIN_SERVICE = "org.kde.KWin"
RUNNER_PATH, RUNNER_IFACE = "/WindowsRunner", "org.kde.krunner1"
KWIN_PATH, KWIN_IFACE = "/KWin", "org.kde.KWin"

# Each call is a round trip to the compositor; two seconds is far past the
# 6-22 ms measured and still short enough that a wedged KWin cannot hang the
# caller for long.
BUSCTL_TIMEOUT = 2.0

# The same depth focus-session.sh walks: claude -> shell -> terminal is two
# levels, and eight is room for tmux, a wrapper and a login shell on top.
ANCESTOR_DEPTH = 8

# At about 6 ms a window, this caps the lookup at roughly a third of a second
# on a desktop with an implausible number of windows open.
WINDOW_SCAN_LIMIT = 60


def session_ancestors(pid, depth=ANCESTOR_DEPTH):
    """The pid and its ancestors, closest first.

    The chain is claude -> shell -> terminal emulator and only the last of
    those owns a window, which is why the pid from sessions.json never matches
    a window by itself. Read from /proc rather than by running ps: this can be
    called while the companion is drawing.
    """
    chain, current = [], None
    try:
        current = int(pid)
    except (TypeError, ValueError):
        return chain
    for _ in range(max(0, int(depth))):
        if current <= 1:
            break
        chain.append(current)
        try:
            with open(f"/proc/{current}/stat", "rb") as handle:
                raw = handle.read().decode("utf-8", "replace")
            # comm sits in parentheses and may contain spaces and parentheses
            # of its own, so the fields are counted from the last ')'.
            current = int(raw[raw.rindex(")") + 1:].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return chain


def parse_match(raw):
    """Window ids from the windows runner's reply, deduplicated, in order.

    Split from the call so it can be tested against captured output. The ids
    come back as "0_{uuid}"; the prefix is the runner's own category and
    getWindowInfo wants what follows it.
    """
    ids = []
    try:
        rows = json.loads(raw)["data"][0]
    except (TypeError, ValueError, KeyError, IndexError):
        return ids
    for row in rows or ():
        try:
            match_id = row[0]
        except (TypeError, IndexError):
            continue
        if not isinstance(match_id, str) or "_" not in match_id:
            continue
        uuid = match_id.split("_", 1)[1]
        if uuid and uuid not in ids:
            ids.append(uuid)
    return ids


def parse_window_info(raw):
    """A geometry mapping from getWindowInfo's reply, or None.

    None for the ids that are not windows: the runner also answers with
    virtual desktops, and getWindowInfo returns an empty map for those.
    """
    try:
        data = json.loads(raw)["data"][0]
    except (TypeError, ValueError, KeyError, IndexError):
        return None
    if not isinstance(data, dict) or not data:
        return None
    try:
        plain = {key: value["data"] for key, value in data.items()}
    except (TypeError, KeyError):
        return None
    try:
        info = {
            "pid": int(plain["pid"]),
            "x": float(plain["x"]),
            "y": float(plain["y"]),
            "width": float(plain["width"]),
            "height": float(plain["height"]),
        }
    except (TypeError, ValueError, KeyError):
        return None
    info["caption"] = str(plain.get("caption") or "")
    info["uuid"] = str(plain.get("uuid") or "")
    info["minimized"] = bool(plain.get("minimized"))
    info["fullscreen"] = bool(plain.get("fullscreen"))
    info["skipTaskbar"] = bool(plain.get("skipTaskbar"))
    # KWin reports the maximise state as the enum bits it matched, 2 for
    # horizontal and 1 for vertical, not as booleans; anything non-zero on
    # both axes is a fully maximised window.
    info["maximized"] = bool(plain.get("maximizeHorizontal")) and \
        bool(plain.get("maximizeVertical"))
    return info


def _busctl(path, interface, method, *args, timeout=BUSCTL_TIMEOUT):
    """One D-Bus call to KWin as JSON text, or None. Never raises."""
    command = ["busctl", "--user", "call", KWIN_SERVICE, path, interface, method]
    # Options go before the separator, values after it. busctl permutes its
    # arguments, so a value beginning with a dash is read as an option:
    #   busctl ... getWindowInfo s --version --json=short
    # prints the systemd version instead of calling the method. The values
    # here are window ids taken from the compositor's own reply, so this is
    # hardening rather than a fix for an id seen in the wild, but they are the
    # one part of this command that this process did not write.
    command.append("--json=short")
    if args:
        command.append("--")
        command.append("s" * len(args))
        command.extend(args)
    try:
        done = subprocess.run(command, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout


def window_geometry(pid, runner=None):
    """The window belonging to this session's process tree, or None.

    None covers every way this can fail — no busctl, no KWin, a session in a
    terminal that has since closed, a session whose window is on another
    machine's display — and the caller treats all of them the same way, by
    not perching.

    `runner` is the D-Bus call, injectable so the parse can be exercised
    without a compositor. It is called as runner(path, interface, method,
    *args) and returns the JSON text or None.

    Blocking: 38-54 ms measured, and worse with many windows open. This
    belongs on the poll timer, never on the frame path.
    """
    call = runner or _busctl
    ancestors = session_ancestors(pid)
    if not ancestors:
        return None
    raw = call(RUNNER_PATH, RUNNER_IFACE, "Match", "")
    if raw is None:
        return None
    fallback = None
    for uuid in parse_match(raw)[:WINDOW_SCAN_LIMIT]:
        reply = call(KWIN_PATH, KWIN_IFACE, "getWindowInfo", uuid)
        if reply is None:
            continue
        info = parse_window_info(reply)
        if info is None or info["pid"] not in ancestors:
            continue
        if info["skipTaskbar"]:
            # Tooltips and menus of the same process carry the same pid and
            # would be perched on for the half second they exist.
            continue
        if not info["minimized"]:
            return info
        # A minimised window is still the answer to "which window is it",
        # and the caller can see the flag; but a visible one wins.
        fallback = fallback or info
    return fallback


# ── carrying the pointer to it ─────────────────────────────────────────────

def _screen_of(point, screens):
    """The index of the screen rectangle containing a point, or None."""
    for index, screen in enumerate(screens or ()):
        try:
            left, top, width, height = (float(v) for v in screen)
        except (TypeError, ValueError):
            continue
        if left <= point[0] < left + width and top <= point[1] < top + height:
            return index
    return None


def delivery_target(window, sprite_px, bounds, origin, screens):
    """Where to walk so a carried pointer ends up on this window, or None.

    The point is the character's own top-left, in the companion's coordinates,
    ready to hand to the existing route builder — the pointer is carried by
    the character's per-frame delta, so where the character goes is where the
    pointer goes, and the sprite ends up centred on the window.

    None is the verdict, and it is the answer to more cases than the point is,
    because this is the rung that takes the mouse out of someone's hand:

      no geometry     — nothing is known about where to go, and the middle of
                        the screen is not a guess worth taking a pointer for.
      minimised       — there is nothing on screen to deliver to.
      off-screen      — same.
      another monitor — measured on this desktop: the two screens are 1234 and
                        1200 pixels tall, so a run between them passes through
                        rows that exist on one and not the other. The
                        compositor clamps the pointer to a valid position
                        there, the clamped part of each delta is gone for
                        good, and the pointer arrives displaced from the
                        character by however much was thrown away.
      unknown layout  — no origin or no screen list means the monitor question
                        cannot be answered, and an unanswered question about
                        the destructive rung is a no.
    """
    if origin is None or not screens:
        return None
    rect = _rect(window)
    if rect is None:
        return None
    if hasattr(window, "get") and window.get("minimized"):
        return None
    sprite = float(sprite_px)
    min_x, min_y, max_x, max_y = (float(b) for b in bounds)
    left, top, width, height = rect

    screen_right, screen_bottom = max_x + sprite, max_y + sprite
    visible_left = max(left, min_x)
    visible_right = min(left + width, screen_right)
    visible_top = max(top, min_y)
    visible_bottom = min(top + height, screen_bottom)
    if visible_right <= visible_left or visible_bottom <= visible_top:
        return None

    # The middle of what can be seen of the window, not the title bar: the
    # right end of a title bar is the close button, and parking someone's
    # pointer on it invites the click that kills the session.
    centre = ((visible_left + visible_right) / 2.0,
              (visible_top + visible_bottom) / 2.0)
    here = _screen_of(origin, screens)
    there = _screen_of(centre, screens)
    if here is None or there is None or here != there:
        return None

    x = centre[0] - sprite / 2.0
    y = centre[1] - sprite / 2.0
    return (max(min_x, min(max_x, x)), max(min_y, min(max_y, y)))
