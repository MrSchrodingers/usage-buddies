"""Pixel-art sprites for the desktop companion, authored as text.

Why text and not PNGs: a sprite sheet in the repository is a binary blob that
no diff can explain. Every frame here is an ASCII grid, so a change to the
walk cycle shows up in review as the pixels that moved.

── What pixel art requires, and what breaks it ────────────────────────────

The grid is the medium. Four operations destroy it, and the previous version
of the companion did all four to a vector file:

  1. Non-integer scale. When the destination is not a whole multiple of the
     source, some source pixels land on two screen pixels and their
     neighbours on one, and the pattern of which is which changes with the
     size. The old companion scaled an SVG into a box whose height and width
     were both computed from a squash factor every frame, so no two frames
     shared a grid. Fix: author at a fixed grid, scale by an integer.
  2. Smoothing. Antialiasing and SmoothPixmapTransform turn the hard edges
     that carry the whole style into gradients. Fix: both off for the sprite.
  3. Rotation. There is no correct rotation of a pixel grid except multiples
     of 90 degrees; anything else resamples. A "lean" of five degrees is a
     rotation. Fix: lean is a redrawn frame, never a transform.
  4. Sub-pixel translation. Moving a 2x-scaled sprite by one screen pixel
     slides the internal grid against the screen grid by half a source pixel.
     Fix: snap position to a multiple of SCALE.

Horizontal flip is the one transform that is safe, because mirroring a grid
maps pixel centres onto pixel centres exactly. It is done on the grid here
rather than with a painter scale, so it composes with the integer snap.

── What makes a sprite read as alive ──────────────────────────────────────

  Volume. Squash and stretch have to conserve area: two rows shorter means
  roughly two columns wider, or it reads as shrinking rather than compressing.
  Both are authored as their own frames.

  Non-uniform timing. A cycle at a constant frame rate reads mechanical. Each
  frame carries its own duration, so a walk can hold on contact and hurry
  through the pass position, and a blink can be two fast frames inside a slow
  idle.

  Irregularity. Blinks are inserted at random intervals rather than on a beat,
  because a metronome blink is worse than no blink.

  Parts that move on their own schedule. The body drawing is the same in all
  four walk frames; what changes is the legs and a one-row rise. Redrawing
  everything on every frame is more work and reads as a slideshow, because
  every part changes at once and the eye has nothing to hold on to.
"""
from __future__ import annotations

GRID = 28          # sprite is GRID x GRID source pixels
SCALE = 2          # integer; on-screen size is GRID * SCALE
SIZE = GRID * SCALE

# ── palettes ───────────────────────────────────────────────────────────────
# Three values per hue plus an outline. The outline is dark and warm rather
# than black: it has to survive on a pale wallpaper, and pure black next to a
# saturated body reads as a sticker rather than a drawing.
#
# Legend used by every grid below:
#   .  transparent      o  outline        h  highlight
#   b  base             s  shade          w  eye white
#   p  pupil            a  accent (beak, feet)

PALETTES = {
    "claude": {
        "o": "#4A2318", "s": "#B0563B", "b": "#D97757", "h": "#EFA183",
        "w": "#FFF1E8", "p": "#33170F", "a": "#F2B441",
    },
    "codex": {
        "o": "#0A2C42", "s": "#0B7CB2", "b": "#0EA5E9", "h": "#63CBF6",
        "w": "#F2FAFF", "p": "#0A2233", "a": "#F5A524",
    },
}

# ── Clawd: a wide octagonal body, two eye holes, four stubby legs ──────────
# The shape comes from the existing clawd.svg, which decodes to an 11x4 blob
# with two eye notches and four legs. Kept, because it is the character; given
# a shading ramp and room to move, which a flat one-colour silhouette has no
# way to express.
#
# Two rules the shapes have to obey, both learned by breaking them:
#
#   Every pose ends on the same ground row. A squash that also lifts off the
#   floor reads as the creature shrinking, not as weight landing on it.
#
#   No row may widen by more than two columns over the one above it. The
#   interior is found by flooding from the border, so a three-column step
#   leaves a gap the flood pours through, and the body renders hollow. The
#   `h` and `s` shading hints are load-bearing here: they occupy the second
#   column of a two-column step and close it.

CLAUDE_BODY = [
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
    ".........oooooooooo.........",
    ".......oh..........so.......",
    ".....oh..............so.....",
    "....oh................so....",
    "...oh..................so...",
    "...o....................o...",
    "...o....................o...",
    "...o....................o...",
    "...o....................o...",
    "...o....................o...",
    "...o....................o...",
    "...o...................so...",
    "....os................sso...",
    ".....osssssssssssssssso.....",
    "......oooooooooooooooo......",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
]

CLAUDE_SQUASH = [
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
    ".......oooooooooooooo.......",
    ".....oh..............so.....",
    "...oh..................so...",
    "..o......................o..",
    ".o........................o.",
    ".o........................o.",
    ".os......................so.",
    "..oss..................sso..",
    "...osssssssssssssssssssso...",
    "....oooooooooooooooooooo....",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
]

CLAUDE_STRETCH = [
    "............................",
    "............................",
    "............................",
    "............................",
    "..........oooooooo..........",
    "........oh........so........",
    "......oh............so......",
    ".....oh..............so.....",
    ".....o................o.....",
    ".....o................o.....",
    ".....o................o.....",
    ".....o................o.....",
    ".....o................o.....",
    ".....o................o.....",
    ".....o................o.....",
    ".....o................o.....",
    ".....o................o.....",
    ".....os..............so.....",
    ".....oss............sso.....",
    ".....osssssssssssssssso.....",
    "......oooooooooooooooo......",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
]

# ── legs ───────────────────────────────────────────────────────────────────
# Cropped bands: the legs occupy four rows and nothing else, and a four-row
# diff is legible where a 28-row one is not. Band row 0 sits on the body's
# ground row, so the seam stays covered when the body bobs up.
#
# The walk is a lift cycle, not a stride. At 28 pixels wide with four legs
# there is no room to swing them past each other — legs one column apart merge
# into a single block. So the planted pair keeps its third row while the
# swinging pair loses it and shifts one column forward. With the body rising
# on those same frames it reads as weight transferring, which is what a walk
# is.
#
# The shafts are shade rather than outline. Outline-coloured legs are correct
# against a pale wallpaper and invisible against a dark one, which is half the
# desktops this runs on.

LEG_ROW = 20

CLAUDE_LEGS = {
    "stand": [
        "......oooooooooooooooo......",
        "......ss..ss....ss..ss......",
        "......ss..ss....ss..ss......",
        "......oo..oo....oo..oo......",
    ],
    "walk0": [
        "......oooooooooooooooo......",
        "......ss...ss....ss.ss......",
        "......ss...oo....oo.ss......",
        "......oo............oo......",
    ],
    "walk1": [
        "......oooooooooooooooo......",
        "......ss..ss....ss..ss......",
        "......ss..ss....ss..ss......",
        "......oo..oo....oo..oo......",
    ],
    "walk2": [
        "......oooooooooooooooo......",
        ".......ss.ss....ss...ss.....",
        ".......oo.ss....ss...oo.....",
        "..........oo....oo..........",
    ],
    "walk3": [
        "......oooooooooooooooo......",
        "......ss..ss....ss..ss......",
        "......ss..ss....ss..ss......",
        "......oo..oo....oo..oo......",
    ],
    "dangle": [
        "......oooooooooooooooo......",
        "......ss..ss....ss..ss......",
        ".......ss..ss..ss..ss.......",
        ".......oo..oo..oo..oo.......",
    ],
    "tuck": [
        "......oooooooooooooooo......",
        ".......ssss......ssss.......",
        "........oo........oo........",
        "............................",
    ],
}

# ── eyes ───────────────────────────────────────────────────────────────────
# Holes in the body, as in the original. The anchor places the left eye; the
# right one is that same band mirrored, so a change to one is a change to both
# and they cannot drift apart.
#
# POSE_EYE_DY moves the face with the body: on a squash the head sits four
# rows lower, and eyes that stay put end up floating above it.

EYE_ROW, EYE_COL, EYE_GAP = 10, 7, 6

EYES = {
    "open":  ["wwww", "wppw", "wppw", "wwww"],
    "look":  ["wwww", "ppww", "ppww", "wwww"],
    "wide":  ["wwww", "wppw", "wppw", "wppw"],
    "half":  ["....", "wwww", "wppw", "wwww"],
    "shut":  ["....", "....", "oooo", "...."],
    "happy": ["....", "o..o", ".oo.", "...."],
    # The brow slants down toward the nose. Authored for the left eye only and
    # mirrored for the right, which is what keeps the two halves of a scowl
    # pointing at each other instead of both leaning the same way.
    "angry": ["oo..", "wwoo", "wppw", "wwww"],
}

POSE_EYE_DY = {
    "claude": {"squash": 4, "stretch": -2, "tuck": 1},
    "codex":  {"squash": 5, "stretch": -2, "tuck": 1},
}

# ── Rex: the Codex owl ─────────────────────────────────────────────────────
# Same construction, a different creature: taller than wide, ear tufts, two
# talons instead of four legs, and a beak in the accent hue. The beak is what
# makes the silhouette read as a bird at 56 pixels; without it the shape is an
# egg. The tufts are drawn as two hollow triangles with a notch between them
# — the earlier two-pixel nubs read as antennae, not ears.

CODEX_BODY = [
    "............................",
    "............................",
    "......oo............oo......",
    ".....o..o..........o..o.....",
    "....o....o........o....o....",
    "...o......o......o......o...",
    "...oooooooooooooooooooooo...",
    "..oh....................so..",
    "..o......................o..",
    "..o......................o..",
    "..o......................o..",
    "..o......................o..",
    "..o......................o..",
    "..o......................o..",
    "..o......................o..",
    "..o......................o..",
    "..o......................o..",
    "..o......................o..",
    "..os....................so..",
    "...os..................so...",
    "....osssssssssssssssssso....",
    "......oooooooooooooooo......",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
]

CODEX_SQUASH = [
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
    "......oo............oo......",
    ".....o..o..........o..o.....",
    "....o....o........o....o....",
    "...o......o......o......o...",
    "..oooooooooooooooooooooooo..",
    ".oh......................so.",
    ".o........................o.",
    "o..........................o",
    "o..........................o",
    "os........................so",
    ".oss....................sso.",
    "..osss................ssso..",
    "...osssssssssssssssssssso...",
    "....oooooooooooooooooooo....",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
]

CODEX_STRETCH = [
    "......oo............oo......",
    ".....o..o..........o..o.....",
    "....o....o........o....o....",
    "...o......o......o......o...",
    "...oooooooooooooooooooooo...",
    "...oh..................so...",
    "...o....................o...",
    "...o....................o...",
    "...o....................o...",
    "...o....................o...",
    "...o....................o...",
    "...o....................o...",
    "...o....................o...",
    "...o....................o...",
    "...o....................o...",
    "...o....................o...",
    "...o....................o...",
    "...o....................o...",
    "...os..................so...",
    "....o..................o....",
    ".....osssssssssssssssso.....",
    "......oooooooooooooooo......",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
    "............................",
]

CODEX_LEG_ROW = 21
CODEX_EYE_ROW, CODEX_EYE_COL, CODEX_EYE_GAP = 8, 6, 8
CODEX_BEAK = (12, 13, ["aa", "aa", ".a"])

CODEX_LEGS = {
    "stand": [
        "......oooooooooooooooo......",
        "..........aa....aa..........",
        "..........aa....aa..........",
        ".........aaa....aaa.........",
    ],
    "walk0": [
        "......oooooooooooooooo......",
        ".........aa......aa.........",
        ".........aa......aa.........",
        "........aaa.................",
    ],
    "walk1": [
        "......oooooooooooooooo......",
        "..........aa....aa..........",
        "..........aa....aa..........",
        ".........aaa....aaa.........",
    ],
    "walk2": [
        "......oooooooooooooooo......",
        "...........aa...aa..........",
        "...........aa...aa..........",
        "................aaa.........",
    ],
    "walk3": [
        "......oooooooooooooooo......",
        "..........aa....aa..........",
        "..........aa....aa..........",
        ".........aaa....aaa.........",
    ],
    "dangle": [
        "......oooooooooooooooo......",
        "..........aa....aa..........",
        "..........aa....aa..........",
        ".........aa......aa.........",
    ],
    "tuck": [
        "......oooooooooooooooo......",
        "..........aa....aa..........",
        ".........aa......aa.........",
        "............................",
    ],
}


# ── composition ────────────────────────────────────────────────────────────

BLANK_ROW = "." * GRID


def _fill_interior(grid):
    """Flood from the border through transparent pixels; whatever the flood
    cannot reach is inside the outline, and becomes base colour.

    A scanline fill between the first and last outline pixel of each row would
    be shorter and wrong: the owl's ear tufts leave a gap between them on the
    same row, and a scanline fill would paint the sky between the ears.
    """
    outside = [[False] * GRID for _ in range(GRID)]
    stack = [(0, i) for i in range(GRID)] + [(GRID - 1, i) for i in range(GRID)]
    stack += [(i, 0) for i in range(GRID)] + [(i, GRID - 1) for i in range(GRID)]
    while stack:
        r, c = stack.pop()
        if not (0 <= r < GRID and 0 <= c < GRID):
            continue
        if outside[r][c] or grid[r][c] != ".":
            continue
        outside[r][c] = True
        stack += [(r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)]
    for r in range(GRID):
        for c in range(GRID):
            if grid[r][c] == "." and not outside[r][c]:
                grid[r][c] = "b"
    return grid


def _paste(grid, top, left, band):
    for r, row in enumerate(band):
        for c, ch in enumerate(row):
            if ch == ".":
                continue
            rr, cc = top + r, left + c
            if 0 <= rr < GRID and 0 <= cc < GRID:
                grid[rr][cc] = ch


def _shift(rows, dy):
    """Integer vertical translation. Safe on a pixel grid — it maps pixel
    centres onto pixel centres — which is why the bob is this and not a float
    offset applied at paint time."""
    if dy == 0:
        return list(rows)
    if dy > 0:
        return [BLANK_ROW] * dy + list(rows[:-dy])
    return list(rows[-dy:]) + [BLANK_ROW] * (-dy)


def shear(rows, lean):
    """Lean a sprite by shifting each row sideways in proportion to its depth.

    This is how a pixel grid leans. Rotation resamples and there is no correct
    version of it below 90 degrees; a per-row integer shift moves whole pixels
    and leaves every edge as hard as it was. The top row does not move and the
    bottom moves by `lean`, so a hanging body pivots from where it is held.

    Used for the swing while the character is being dragged: the body trails
    the hand, which is the difference between something hanging and something
    glued to the cursor.
    """
    filled = [i for i, row in enumerate(rows) if set(row) != {"."}]
    if not filled or lean == 0:
        return list(rows)
    top, bottom = filled[0], filled[-1]
    span = max(1, bottom - top)
    out = []
    for i, row in enumerate(rows):
        if i < top:
            out.append(row)
            continue
        shift = int(round(lean * (i - top) / span))
        if shift > 0:
            out.append(("." * shift + row)[:GRID])
        elif shift < 0:
            out.append((row[-shift:] + "." * -shift)[:GRID])
        else:
            out.append(row)
    return out


def stretch_rows(rows, delta):
    """Squash or stretch a sprite by repeating or dropping whole rows.

    The other exact vertical operation on a pixel grid. Scaling by a fraction
    resamples; duplicating a row makes two identical rows and removing one
    leaves the rest untouched, so a body can wobble without a single soft edge
    appearing anywhere in it.

    Rows are taken from the middle of the body, never the head or the feet:
    stretching a face is uncanny and lifting the feet off the floor undoes what
    the ground row is for. The bottom stays put, so the shape grows upward.
    """
    filled = [i for i, row in enumerate(rows) if set(row) != {"."}]
    if not filled or delta == 0:
        return list(rows)
    top, bottom = filled[0], filled[-1]
    if bottom - top < 8:
        return list(rows)
    band = list(range(top + (bottom - top) // 3, top + 2 * (bottom - top) // 3))
    if not band:
        return list(rows)

    body = rows[top:bottom + 1]
    picks = [band[(i * len(band)) // max(1, abs(delta)) % len(band)] - top
             for i in range(abs(delta))]
    out = []
    for i, row in enumerate(body):
        if delta < 0 and i in picks:
            continue
        out.append(row)
        if delta > 0 and i in picks:
            out.append(row)

    blank = "." * GRID
    # Bottom stays where it was: pad or trim from the top.
    lead = bottom + 1 - len(out)
    if lead >= 0:
        result = [blank] * lead + out
    else:
        result = out[-lead:]
    return (result + [blank] * (GRID - len(result)))[:GRID]


def mirror(rows):
    """Horizontal flip on the grid rather than with a painter scale.
    Mirroring is the one exact transform on a pixel grid, and doing it here
    keeps it composable with the integer position snap."""
    return ["".join(reversed(row)) for row in rows]


def compose(brand, body, legs, eyes, body_dy=0, eye_dy=0):
    """One frame: body, legs, face, all shifted together by the bob.

    The legs move with the body rather than staying pinned to the floor. Pinned
    feet sound more correct and render worse: the band's first row is the
    body's ground outline, so when the body rises one row the outline is drawn
    twice, one row apart, and the character grows a two-pixel black bar across
    its base on every other frame. Letting the whole creature rise is also what
    a walk actually does — feet leave the ground.
    """
    grid = [list(row) for row in _shift(body, body_dy)]
    if brand == "codex":
        leg_row, er, ec, gap = CODEX_LEG_ROW, CODEX_EYE_ROW, CODEX_EYE_COL, CODEX_EYE_GAP
    else:
        leg_row, er, ec, gap = LEG_ROW, EYE_ROW, EYE_COL, EYE_GAP
    if legs is not None:
        _paste(grid, leg_row + body_dy, 0, legs)
    _fill_interior(grid)
    if brand == "codex":
        btop, bleft, band = CODEX_BEAK
        _paste(grid, btop + body_dy + eye_dy, bleft, band)
    if eyes is not None:
        width = len(eyes[0])
        _paste(grid, er + body_dy + eye_dy, ec, eyes)
        _paste(grid, er + body_dy + eye_dy, ec + width + gap, mirror(eyes))
    return ["".join(row) for row in grid]


# ── clips ──────────────────────────────────────────────────────────────────
# A clip is a list of (frame, milliseconds). Durations are per frame because a
# cycle at one rate reads mechanical: the walk holds on contact and hurries
# through the pass, which is what makes it look like weight transferring.
# `loop: False` clips play once and hand back to whatever asked for them.

CLIPS = {
    "idle":  {"loop": True,  "frames": [("stand_open", 1100), ("stand_open_up", 800)]},
    "blink": {"loop": False, "frames": [("stand_shut", 90), ("stand_open", 80),
                                        ("stand_shut", 90)]},
    "walk":  {"loop": True,  "frames": [("walk0", 120), ("walk1", 90),
                                        ("walk2", 120), ("walk3", 90)]},
    "talk":  {"loop": True,  "frames": [("stand_open", 380), ("stand_open_up", 220),
                                        ("stand_look", 340), ("stand_open", 260)]},
    "alert": {"loop": True,  "frames": [("stretch_wide", 110), ("stand_wide", 90),
                                        ("stretch_wide", 110), ("stand_wide", 520)]},
    "sleep": {"loop": True,  "frames": [("tuck_shut", 1500), ("tuck_half", 1100)]},
    # Held: it swings. Four positions rather than two, so the body reads as
    # trailing the hand instead of blinking between two poses — the limbs are
    # already hanging, and what sells weight on a string is that the swing has
    # a middle.
    "held":  {"loop": True,  "frames": [("dangle_wide", 150), ("dangle_look", 130),
                                        ("dangle_wide_up", 150), ("dangle_look", 130)]},
    # Dragged around for too long. Same pose, angrier face, and fast enough to
    # read as protest rather than as swinging.
    "annoyed": {"loop": True, "frames": [("dangle_angry", 110), ("dangle_angry_up", 90),
                                         ("dangle_angry", 110), ("dangle_shut", 90)]},
    # Running off with the pointer. Same gait, scowling.
    "furious": {"loop": True, "frames": [("walk0_angry", 90), ("walk1_angry", 70),
                                         ("walk2_angry", 90), ("walk3_angry", 70)]},
    "land":  {"loop": False, "frames": [("squash_shut", 70), ("squash_happy", 90),
                                        ("stand_happy", 110), ("stretch_happy", 90),
                                        ("stand_open", 130)]},
}

# <pose>_<eyes>[_up]: pose picks the body and the legs, eyes pick the face,
# _up raises the whole character by one row.
FRAME_SPECS = {
    "stand_open":     ("stand", "open", 0),
    "stand_open_up":  ("stand", "open", -1),
    "stand_look":     ("stand", "look", 0),
    "stand_shut":     ("stand", "shut", 0),
    "stand_wide":     ("stand", "wide", 0),
    "stand_happy":    ("stand", "happy", 0),
    "walk0":          ("walk0", "open", 0),
    "walk1":          ("walk1", "open", -1),
    "walk2":          ("walk2", "open", 0),
    "walk3":          ("walk3", "look", -1),
    "dangle_wide":    ("dangle", "wide", 0),
    "dangle_wide_up": ("dangle", "wide", -1),
    "dangle_look":    ("dangle", "look", 0),
    "dangle_shut":    ("dangle", "shut", 0),
    "dangle_angry":   ("dangle", "angry", 0),
    "dangle_angry_up": ("dangle", "angry", -1),
    "stand_angry":    ("stand", "angry", 0),
    "walk0_angry":    ("walk0", "angry", 0),
    "walk1_angry":    ("walk1", "angry", -1),
    "walk2_angry":    ("walk2", "angry", 0),
    "walk3_angry":    ("walk3", "angry", -1),
    "tuck_shut":      ("tuck", "shut", 0),
    "tuck_half":      ("tuck", "half", -1),
    "squash_shut":    ("squash", "shut", 0),
    "squash_happy":   ("squash", "happy", 0),
    "stretch_wide":   ("stretch", "wide", 0),
    "stretch_happy":  ("stretch", "happy", 0),
}

_BODIES = {
    "claude": {"squash": "CLAUDE_SQUASH", "stretch": "CLAUDE_STRETCH",
               "*": "CLAUDE_BODY"},
    "codex":  {"squash": "CODEX_SQUASH", "stretch": "CODEX_STRETCH",
               "*": "CODEX_BODY"},
}


def build_frames(brand):
    """Every frame as an ASCII grid, keyed by the names the clips use."""
    key = "codex" if brand == "codex" else "claude"
    table = _BODIES[key]
    legs = CODEX_LEGS if key == "codex" else CLAUDE_LEGS
    out = {}
    for name, (pose, eye, body_dy) in FRAME_SPECS.items():
        body = globals()[table.get(pose, table["*"])]
        leg_key = pose if pose in legs else "stand"
        eye_dy = POSE_EYE_DY[key].get(pose, 0)
        out[name] = compose(brand, body, legs[leg_key], EYES[eye],
                            body_dy=body_dy, eye_dy=eye_dy)

    # Swing poses are the dangle sheared, not redrawn: the shape is identical
    # and only its lean changes, so authoring them separately would be four
    # more grids to keep in step with the one that matters.
    base = out["dangle_wide"]
    for lean_step, lean in LEANS.items():
        leaned = shear(base, lean)
        for wob_step, wob in WOBBLES.items():
            out[wobble_frame(lean_step, wob_step)] = stretch_rows(leaned, wob)
    return out


# Held, the body both leans and wobbles. Lean is the shear, wobble is rows
# repeated or dropped. Five by five, generated from the one dangle pose — the
# alternative is twenty-five grids to keep in step with each other.
LEANS = {-3: -5, -2: -4, -1: -2, 0: 0, 1: 2, 2: 4, 3: 5}
WOBBLES = {-3: -3, -2: -2, -1: -1, 0: 0, 1: 2, 2: 4, 3: 5}


def wobble_frame(lean, wob):
    return f"wob{lean:+d}{wob:+d}"


def frame_names():
    """Every frame a clip can ask for. Used by the tests to prove no clip
    references a frame that was renamed out from under it."""
    return {f for clip in CLIPS.values() for f, _ in clip["frames"]}


# ── playback ───────────────────────────────────────────────────────────────

class Animator:
    """Plays clips. Pure Python and Qt-free, so the timing can be tested
    without a display.

    Two behaviours are the point of it existing:

    Non-looping clips (`land`, `blink`) play to the end and then hand control
    back to whatever was playing before, so a blink does not cancel a walk and
    a landing does not have to be manually un-set.

    Blinks arrive on their own schedule rather than on a beat. A blink every
    four seconds exactly is more obviously mechanical than never blinking at
    all, so the interval is drawn fresh each time from a range.
    """

    BLINK_MIN, BLINK_MAX = 2.6, 7.4

    def __init__(self, clip="idle", rng=None):
        import random as _random
        self._rng = rng or _random.Random()
        self.base = clip
        self.clip = clip
        self.index = 0
        self.elapsed = 0.0
        self._resume = None
        self.next_blink = self._rng.uniform(self.BLINK_MIN, self.BLINK_MAX)

    # -- state --

    def set_clip(self, clip):
        """Change the looping animation. A one-shot in flight is not
        interrupted; it resumes into the new clip when it ends."""
        if clip == self.base:
            return
        self.base = clip
        if self._resume is None:
            self.clip, self.index, self.elapsed = clip, 0, 0.0
        else:
            self._resume = clip

    def play_once(self, clip):
        """Interrupt with a one-shot; the current looping clip resumes after."""
        self._resume = self.base
        self.clip, self.index, self.elapsed = clip, 0, 0.0

    # -- time --

    def advance(self, dt):
        """Move time forward by dt seconds and return the current frame name."""
        frames = CLIPS[self.clip]["frames"]
        self.elapsed += dt * 1000.0
        guard = 0
        while self.elapsed >= frames[self.index][1] and guard < 64:
            guard += 1
            self.elapsed -= frames[self.index][1]
            self.index += 1
            if self.index >= len(frames):
                if CLIPS[self.clip]["loop"]:
                    self.index = 0
                else:
                    resume = self._resume if self._resume is not None else self.base
                    self._resume = None
                    self.clip, self.index = resume, 0
                    frames = CLIPS[self.clip]["frames"]
        return frames[self.index][0]

    def maybe_blink(self, dt, allowed=True):
        """Count down to the next blink. Returns True on the frame it fires."""
        self.next_blink -= dt
        if self.next_blink > 0:
            return False
        self.next_blink = self._rng.uniform(self.BLINK_MIN, self.BLINK_MAX)
        if not allowed or self._resume is not None:
            return False
        self.play_once("blink")
        return True


# ── Qt bridge ──────────────────────────────────────────────────────────────
# Imported lazily so the grids and the Animator can be exercised without a
# display, which is what the tests do.

def to_qimage(grid, palette, scale=SCALE):
    """One frame as a QImage at GRID*scale, drawn a source pixel at a time.

    Painting each pixel as a rectangle rather than building a small image and
    calling scaled() avoids the question of which transformation mode Qt picks
    — there is no resampling step to get wrong.
    """
    from PySide6.QtGui import QColor, QImage, QPainter
    # Sized from the grid it was handed, not from GRID. Hardcoding the
    # character's 28 meant anything drawn on a different canvas came out as a
    # 28-square corner of itself, silently — the image is the right *kind* of
    # thing, just cropped, so nothing raises and the only symptom is a
    # fragment on screen.
    rows = len(grid)
    cols = max((len(row) for row in grid), default=0)
    img = QImage(cols * scale, rows * scale, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    for r, row in enumerate(grid):
        for c, ch in enumerate(row):
            if ch == ".":
                continue
            p.fillRect(c * scale, r * scale, scale, scale, QColor(palette[ch]))
    p.end()
    return img


def build_sheet(brand, scale=SCALE):
    """Every frame of a brand as a QImage, plus its mirror.

    Both directions are baked rather than flipped at paint time: mirroring a
    grid is exact, but doing it once here means the paint path is a single
    drawImage with no transform on it at all.
    """
    pal = PALETTES["codex" if brand == "codex" else "claude"]
    frames = build_frames(brand)
    sheet = {}
    for name, grid in frames.items():
        sheet[name] = to_qimage(grid, pal, scale)
        sheet[name + ":flip"] = to_qimage(mirror(grid), pal, scale)
    return sheet

