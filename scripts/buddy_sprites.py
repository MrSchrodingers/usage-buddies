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

The same reasoning admits a small family of others, and every one of them moves
whole pixels: shifting rows, shearing by a per-row integer offset, duplicating
or dropping whole rows, and dropping whole columns. The leans, the swing, the
squash, the sit and the edge-on frames of a turn are all made of those, which
is why there is one drawing of each body here instead of one per pose. A second
drawing of a body is a second thing to keep in step with the first.

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

  Contact with the ground. Every pose ends on the same floor row unless it says
  otherwise, and there is a shadow to put under it. A character with neither is
  a sticker on a wallpaper; it is the cheapest of all of these and it does the
  most.
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
    # Sat down. Two rows of leg instead of three, used with the body dropped by
    # one, so the creature is shorter by a row and still on the same floor. The
    # front foot lies forward out of the crouch: the first attempt drew the
    # whole thing one row deep and the legs merged with the body's own ground
    # outline into a single dark bar, which read as a blob on a plank.
    "sit": [
        "......oooooooooooooooo......",
        "......ss..ss....ss..ss......",
        "......oo..oo....oo..oooo....",
        "............................",
    ],
    # Waving without an arm, because Clawd has none. A front leg leaves the
    # floor and reaches up and forward while the body leans back — the lean is
    # the half of it that reads at this size, since a lifted leg on its own is
    # a limp. The raised foot is drawn on the band's first row, level with the
    # body's base and clear of its edge, so it ends up higher than every other
    # foot; drawn a row lower it was a twig sticking out of the side.
    #
    # The three legs still down do not move at all. That is what keeps the
    # gesture attached to a body instead of floating in front of one.
    "wave0": [
        "......oooooooooooooooo..oo..",
        "......ss..ss....ss..ssss....",
        "......ss..ss....ss..........",
        "......oo..oo....oo..........",
    ],
    "wave1": [
        "......oooooooooooooooo......",
        "......ss..ss....ss..ssss....",
        "......ss..ss....ss......oo..",
        "......oo..oo....oo..........",
    ],
    # Pointing. Same trick as the wave and a different word: the leg goes out
    # straight and low rather than up, and it is held there instead of beating.
    # It comes down on its foot at the far end, so the pose has weight on it —
    # a limb held in the air with nothing under it reads as a stick.
    "point": [
        "......oooooooooooooooo......",
        "......ss..ss....ss..ss......",
        "......ss..ss....ss..ssssss..",
        "......oo..oo....oo......oo..",
    ],
    # Reading. The thing being read is drawn into the leg band rather than
    # given a grid of its own: it stands on the same floor row and it only ever
    # appears with this pose, so a separate image would be one more thing to
    # keep aligned with the feet. It is filled with accent rather than left
    # hollow, because the flood fill would otherwise pour base colour into it
    # and a book in body colour is not visible.
    "read": [
        "......oooooooooooooooo......",
        "......ss..ss....ss..ss.oooo.",
        "......ss..ss....ss..ss.oaao.",
        "......oo..oo....oo..oo.oaao.",
    ],
    # Braced. The outer legs splay away from the body and the inner pair stays
    # under it, so the stance widens without the legs crossing — at four
    # columns apart, two legs leaning toward each other merge into one block.
    "panic": [
        "......oooooooooooooooo......",
        "......ss..ss....ss..ss......",
        ".....ss...ss....ss...ss.....",
        "....oo....oo....oo....oo....",
    ],
    # Off the ground. Everything is pulled up under the body and the band's
    # lower rows are empty, which is what makes the pose airborne — see
    # OFF_GROUND_POSES.
    "celebrate": [
        "......oooooooooooooooo......",
        ".......oo..oo..oo..oo.......",
        "............................",
        "............................",
    ],
    # Typing: the two front feet tap in alternation and nothing else moves.
    # The whole gesture is one row of two pixels changing, which is the point —
    # a part moving on its own schedule reads better than a body redrawn.
    "type0": [
        "......oooooooooooooooo......",
        "......ss..ss....ss..ss......",
        "......ss..ss....ss..ss......",
        "......oo..oo....oo..........",
    ],
    "type1": [
        "......oooooooooooooooo......",
        "......ss..ss....ss..ss......",
        "......ss..ss....ss..ss......",
        "......oo..oo........oo......",
    ],
    # Mid-turn, seen edge-on. The legs are bunched toward the centre line and
    # deliberately clear of columns 11-12 and 15-16, which is what `squeeze`
    # takes out of the middle: legs drawn across those columns come back a
    # single pixel wide.
    "turn": [
        "......oooooooooooooooo......",
        ".........ss......ss.........",
        ".........ss......ss.........",
        ".........oo......oo.........",
    ],
    # Peeking has no legs at all: the body is cut off above them. None rather
    # than an empty band, so that a missing drawing is a decision in the table
    # and not four rows of dots that look like an accident.
    "peek": None,
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
    # Rolled up. The pupil is pinned against the top of the box, which is as
    # far up as an eight-pixel eye can look before it leaves it.
    "roll":  ["wppw", "wppw", "wwww", "wwww"],
    # Reeling. Drawn straight onto the body colour like `shut` and `happy`
    # rather than onto a white eye: a cross needs the whole box, and the white
    # left around it at this size reads as a smudge instead of an eye.
    "dizzy": ["o..o", ".oo.", ".oo.", "o..o"],
    # One white pixel inside the pupil, and nothing else differs from `open`.
    # A flat pupil is a hole; a pupil with a catchlight in it is wet, and that
    # single pixel is the whole difference between the two.
    "sparkle": ["wwww", "wpww", "wppw", "wwww"],
    # One step past `half` and one step short of `shut`: the lid is down over
    # three rows and what is left is a sliver with the pupil still in it. The
    # yawn needs a rung between awake and asleep or the two cut together.
    "sleepy": ["....", "....", "oooo", "wppw"],
    # A glance. Both pupils sit on the same side of the face, which is the one
    # thing mirroring cannot draw: mirrored, a pupil against the left edge of
    # the left eye becomes a pupil against the right edge of the right one, and
    # the result is `look` — a stare past both sides of whatever is in front.
    # So this is authored as (left eye, right eye) and pasted as given.
    "side":  (["wwww", "ppww", "ppww", "wwww"],
              ["wwww", "ppww", "ppww", "wwww"]),
}

POSE_EYE_DY = {
    # `panic` borrows the stretch body, so it borrows the stretch offset with
    # it; a face left at the standing row floats inside a taller head.
    "claude": {"squash": 4, "stretch": -2, "panic": -2, "tuck": 1},
    "codex":  {"squash": 5, "stretch": -2, "panic": -2, "tuck": 1},
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
    # Sat down: the body drops a row and the front foot goes out in front of
    # it. Asymmetric, because the front foot of a perched bird is the one you
    # see; a symmetric pair of talons is a bird standing, not sitting.
    "sit": [
        "......oooooooooooooooo......",
        "..........aa....aa..........",
        ".........aaa....aaaaaa......",
        "............................",
    ],
    # One talon up and reaching, the other planted with its toe still down.
    # With two legs there is no spare weight to shift, so the planted one keeps
    # every pixel it had — moving both is how a wave turns into a hop.
    "wave0": [
        "......oooooooooooooooo..aa..",
        "..........aa....aaaaaa......",
        "..........aa................",
        ".........aaa................",
    ],
    "wave1": [
        "......oooooooooooooooo......",
        "..........aa....aaaaaa......",
        "..........aa..........aa....",
        ".........aaa................",
    ],
    "point": [
        "......oooooooooooooooo......",
        "..........aa....aa..........",
        "..........aa....aaaaaa......",
        ".........aaa..........aa....",
    ],
    "read": [
        "......oooooooooooooooo......",
        "..........aa....aa.....oooo.",
        "..........aa....aa.....oaao.",
        ".........aaa....aaa....oaao.",
    ],
    # Braced: both talons step outward and the toes spread. An owl that panics
    # widens its stance; it has no fifth leg to put down.
    "panic": [
        "......oooooooooooooooo......",
        ".........aa......aa.........",
        "........aa........aa........",
        ".......aaa........aaa.......",
    ],
    "celebrate": [
        "......oooooooooooooooo......",
        "..........aa....aa..........",
        "............................",
        "............................",
    ],
    "type0": [
        "......oooooooooooooooo......",
        "..........aa....aa..........",
        "..........aa....aa..........",
        ".........aaa................",
    ],
    "type1": [
        "......oooooooooooooooo......",
        "..........aa....aa..........",
        "..........aa....aa..........",
        "................aaa.........",
    ],
    # Clear of columns 11-12 and 15-16 for the same reason as Clawd's: those
    # are the ones `squeeze` drops.
    "turn": [
        "......oooooooooooooooo......",
        ".........aa......aa.........",
        ".........aa......aa.........",
        "........aaa......aaa........",
    ],
    "peek": None,
}


# ── contact shadow ─────────────────────────────────────────────────────────
# A flattened ellipse to put under the feet. Without one, a sprite on a
# photograph of a beach is a sticker on a photograph of a beach; with one, it
# is standing on the beach. It is the cheapest thing on this page and it does
# more for the illusion than any single frame.
#
# It is its own image rather than rows added to the body grids, for two reasons
# that are both about what must *not* happen to it. It must not shear when the
# body is dragged and must not stretch when the body squashes — a shadow that
# leans with the thing casting it reads as a second object glued to its feet —
# and it must not be drawn at all while the character is off the ground. Both
# are decisions for whoever paints, and neither is available if the shadow is
# baked into the same grid as the creature.
#
# It has its own two characters and its own palette so that it stays out of the
# body's alphabet: `d` or `m` in a body grid would have to mean a body colour
# there and a shadow colour here. Its colours carry alpha (#AARRGGBB), which no
# body colour does — a shadow is the wallpaper, darkened, not a grey shape laid
# on top of it.

SHADOW = [
    "........mmmmmmmmmmmm........",
    "......mmddddddddddddmm......",
    "........mmmmmmmmmmmm........",
]

SHADOW_PALETTE = {"d": "#59000000", "m": "#2E000000"}


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


def sway(rows, lean):
    """Lean about the feet instead of about the hand.

    `shear` pivots on its top row because it was written for a body hanging
    from a cursor. A creature standing on a floor pivots at the other end: the
    feet stay where they were and the head travels. Reversing the rows,
    shearing and reversing back is the same per-row integer shift with the
    pivot moved, so it is exactly as safe on the grid as shear is — and it is
    why a lean does not need a second drawing of the body.

    Two things fall out of pivoting at the floor and both are wanted. The
    ground row does not move, so the leg band's seam stays covered. And the
    shift is proportional to the distance from the pivot, so the legs — which
    sit on it — barely move while the head moves by the full lean.
    """
    return list(reversed(shear(list(reversed(rows)), lean)))


def cut_off(rows, at):
    """Everything from row `at` down removed, and the opening sealed.

    For peeking around an edge, where the half of the body behind the edge is
    not drawn at all. The seal is not a finishing touch: the interior is found
    by flooding in from the border, so an open-bottomed dome is not a closed
    shape, the flood walks in underneath it, and the body renders hollow with
    nothing raised anywhere. The seal spans the row that was cut, so it lands
    on the outline it replaces rather than guessing a width.
    """
    kept = list(rows[:at])
    edge = [c for c, ch in enumerate(rows[at]) if ch != "."]
    if edge:
        kept.append("." * edge[0] + "o" * (edge[-1] - edge[0] + 1)
                    + "." * (GRID - edge[-1] - 1))
    return (kept + [BLANK_ROW] * GRID)[:GRID]


# The two columns a squeeze may never take: the owl's beak sits on them, and a
# narrowing that removes the beak removes the one feature that makes the
# silhouette a bird rather than an egg.
SQUEEZE_KEEP = (GRID // 2 - 1, GRID // 2)


def squeeze(rows, cols):
    """Narrow a sprite by dropping whole columns out of it.

    The horizontal twin of stretch_rows, and the only exact way to foreshorten
    a pixel grid: scaling a body to 70% resamples every edge in it, dropping a
    column leaves every remaining edge as hard as it was. Used for the middle
    of a turn, where the creature is edge-on and there is less of it to see.

    The columns come out in two runs either side of the centre line rather than
    across it, so the beak survives, and the halves are re-padded evenly so the
    sprite keeps the same centre. `cols` must be even for that to hold.
    """
    if cols <= 0:
        return list(rows)
    half = cols // 2
    left, right = SQUEEZE_KEEP[0] - half, SQUEEZE_KEEP[1] + 1
    out = []
    for row in rows:
        kept = row[:left] + row[left + half:right] + row[right + half:]
        out.append("." * half + kept + "." * (GRID - half - len(kept)))
    return out


def mirror(rows):
    """Horizontal flip on the grid rather than with a painter scale.
    Mirroring is the one exact transform on a pixel grid, and doing it here
    keeps it composable with the integer position snap."""
    return ["".join(reversed(row)) for row in rows]


def _eye_bands(eyes):
    """The left eye and the right eye, out of either one band or a pair.

    A single band is mirrored, and that stays the default: the two halves of a
    face drifting apart is the commonest way an eight-pixel eye goes wrong, and
    one band means a change to one eye is a change to both.

    But mirroring can only produce symmetric expressions, and some of them are
    not. A glance has both pupils on the same side of the face; mirrored, a
    pupil against the left edge of the left eye becomes a pupil against the
    right edge of the right one, which is a stare past both sides of whatever
    is in front. Those are authored as (left, right) and pasted as given.
    """
    if isinstance(eyes, tuple):
        return eyes
    return eyes, mirror(eyes)


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
        left, right = _eye_bands(eyes)
        width = len(left[0])
        _paste(grid, er + body_dy + eye_dy, ec, left)
        _paste(grid, er + body_dy + eye_dy, ec + width + gap, right)
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
    # Sat down where it stopped. It looks around from there rather than holding
    # one pose: something that has not moved for four seconds is a statue, and
    # it is a statue in whichever pose you left it in.
    "sit":   {"loop": True,  "frames": [("sit_open", 1300), ("sit_half", 760),
                                        ("sit_side", 1100), ("sit_open", 620)]},
    # The way into sleep. It used to cut from standing to curled up in one
    # frame; the stretch, the eyes going and the fold are what make the sleep
    # afterwards read as having been arrived at rather than switched on.
    "yawn":  {"loop": False, "frames": [("stand_half", 220), ("stretch_shut", 300),
                                        ("stretch_sleepy", 240), ("stand_sleepy", 360),
                                        ("tuck_sleepy", 480), ("tuck_shut", 700)]},
    # Waving. Quick on the beats and long on the hold afterwards — a wave with
    # every frame the same length is a windmill, and the pause is what says the
    # gesture was aimed at someone.
    "wave":  {"loop": True,  "frames": [("wave0_happy", 150), ("wave1_happy", 110),
                                        ("wave0_happy", 150), ("wave1_open", 130),
                                        ("stand_happy", 720)]},
    # Pointing: fast into the pose, then held. The length of the hold is the
    # difference between pointing at something and gesturing at the room.
    "point": {"loop": True,  "frames": [("point_open", 170), ("point_wide", 880),
                                        ("point_open", 240), ("point_wide", 620)]},
    "nod":   {"loop": False, "frames": [("stand_open", 100), ("nod_down", 140),
                                        ("stand_open_up", 90), ("nod_down", 160),
                                        ("stand_open", 130)]},
    "shake": {"loop": False, "frames": [("shake_left", 100), ("shake_right", 80),
                                        ("shake_left", 100), ("shake_right", 80),
                                        ("stand_open", 140)]},
    "read":  {"loop": True,  "frames": [("read_half", 900), ("read_open", 420),
                                        ("read_half", 1200), ("read_side", 520)]},
    # Nothing holds still: the longest frame here is a tenth of a second, which
    # is the only timing that reads as alarm rather than as a fast idle.
    "panic": {"loop": True,  "frames": [("panic_wide", 80), ("panic_dizzy", 70),
                                        ("panic_wide", 100), ("stand_wide", 60)]},
    # A hop with its weight in the right places: quick out of the crouch, slow
    # at the top where a jump hangs, quick back down.
    "celebrate": {"loop": True,
                  "frames": [("squash_happy", 110), ("celebrate_happy", 170),
                             ("celebrate_sparkle", 230), ("celebrate_happy", 130),
                             ("stand_happy", 150)]},
    "peek":  {"loop": True,  "frames": [("peek_side", 950), ("peek_wide", 600),
                                        ("peek_side", 1400), ("peek_shut", 120)]},
    # Turning around. The facing used to invert between one frame and the next,
    # which is a creature being replaced by its own mirror image. Two edge-on
    # frames in the middle give the movement somewhere to happen, and the eyes
    # shut on the fastest of them: a blink through the impossible part of a
    # turn is the oldest trick there is for this.
    "turn":  {"loop": False, "frames": [("stand_look", 130), ("turn_open", 80),
                                        ("turn_shut", 60), ("turn_open", 90),
                                        ("stand_open", 150)]},
    "type":  {"loop": True,  "frames": [("type0_open", 120), ("type1_open", 90),
                                        ("type0_half", 140), ("type1_open", 100)]},
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
    # Sitting: the body drops a row onto a leg band drawn a row shorter, so the
    # creature loses a row of height and keeps the same floor under it.
    "sit_open":       ("sit", "open", 1),
    "sit_half":       ("sit", "half", 1),
    "sit_side":       ("sit", "side", 1),
    "stand_half":     ("stand", "half", 0),
    "stand_sleepy":   ("stand", "sleepy", 0),
    # No clip names stand_roll: the two shake frames are made from it below.
    # It is in the table anyway so that it goes through the same checks every
    # other frame does, rather than being composed off to the side.
    "stand_roll":     ("stand", "roll", 0),
    "stretch_shut":   ("stretch", "shut", 0),
    "stretch_sleepy": ("stretch", "sleepy", 0),
    "tuck_sleepy":    ("tuck", "sleepy", 0),
    "wave0_happy":    ("wave0", "happy", 0),
    "wave1_happy":    ("wave1", "happy", 0),
    "wave1_open":     ("wave1", "open", 0),
    "point_open":     ("point", "open", 0),
    "point_wide":     ("point", "wide", 0),
    # The reading frames differ by the eyes alone. A one-row bob would lift the
    # book with them — it is drawn into the leg band, and the band travels with
    # the body — and a book that breathes is worse than a still one.
    "read_half":      ("read", "half", 0),
    "read_open":      ("read", "open", 0),
    "read_side":      ("read", "side", 0),
    "panic_wide":     ("panic", "wide", 0),
    "panic_dizzy":    ("panic", "dizzy", 0),
    # Two rows is the whole headroom there is. Rex's ear tufts start on row 2
    # and the stretch body starts on row 0, so a lift of three takes the tips
    # off the top of the grid and leaves the tufts as two floating marks — it
    # is a shift, so nothing is out of range and nothing raises. The height in
    # this hop comes from the legs being tucked, which is four more rows.
    "celebrate_happy":   ("celebrate", "happy", -1),
    "celebrate_sparkle": ("celebrate", "sparkle", -2),
    "peek_side":      ("peek", "side", 0),
    "peek_wide":      ("peek", "wide", 0),
    "peek_shut":      ("peek", "shut", 0),
    "turn_open":      ("turn", "open", 0),
    "turn_shut":      ("turn", "shut", 0),
    "type0_open":     ("type0", "open", 0),
    "type1_open":     ("type1", "open", 0),
    "type0_half":     ("type0", "half", 0),
}

_BODIES = {
    "claude": {"squash": "CLAUDE_SQUASH", "stretch": "CLAUDE_STRETCH",
               "panic": "CLAUDE_STRETCH", "*": "CLAUDE_BODY"},
    "codex":  {"squash": "CODEX_SQUASH", "stretch": "CODEX_STRETCH",
               "panic": "CODEX_STRETCH", "*": "CODEX_BODY"},
}

# Poses that are the standing body put through an exact transform instead of a
# second drawing of it. A leaning copy of the body would be one more grid to
# keep in step with the one that matters, and the transforms here move whole
# pixels: nothing in them can soften an edge.
#
#   POSE_TILT     columns the head travels, pivoting at the feet. Negative
#                 leans back, away from the direction it faces.
#   POSE_SQUEEZE  columns taken out of the middle, for the edge-on frames of a
#                 turn. Even, and never the two the beak sits on.
#   POSE_CUT      the row the body is cut off and sealed at, for peeking around
#                 an edge with only the dome and the eyes showing. Per brand:
#                 Rex's beak runs to row 14, so his cut has to fall below it or
#                 the peek is an owl with the front of its face missing.

POSE_TILT = {"wave0": -2, "wave1": -1, "point": 3, "read": 3,
             "type0": 1, "type1": 2}
POSE_SQUEEZE = {"turn": 4}
POSE_CUT = {"peek": {"claude": 14, "codex": 15}}

# Poses whose silhouette does not reach the floor, and why. Everything else is
# expected to stand on it — a pose that floats without saying so here reads as
# the creature shrinking rather than as it moving, and the only symptom is that
# something looks slightly wrong.
OFF_GROUND_POSES = {
    "tuck": "asleep with its feet pulled up under it; the band's last row is "
            "empty, so the curl clears the floor by a row",
    "peek": "cut off above the legs; there are no feet in the frame at all",
    "celebrate": "in the air, which is the entire pose",
}


def pose_body(brand, pose):
    """The body grid a pose is drawn on, before anything is shifted.

    Its own function because the tests need the same answer build_frames does:
    a copy of this lookup in a test drifts from the one that renders, and then
    the test is checking a body nothing draws.
    """
    key = "codex" if brand == "codex" else "claude"
    table = _BODIES[key]
    body = globals()[table.get(pose, table["*"])]
    if pose in POSE_CUT:
        body = cut_off(body, POSE_CUT[pose][key])
    return body


def build_frames(brand):
    """Every frame as an ASCII grid, keyed by the names the clips use."""
    key = "codex" if brand == "codex" else "claude"
    legs = CODEX_LEGS if key == "codex" else CLAUDE_LEGS
    out = {}
    for name, (pose, eye, body_dy) in FRAME_SPECS.items():
        body = pose_body(brand, pose)
        # Squash and stretch borrow the standing legs on purpose: the body
        # changes and the stance does not. Every other pose has a band of its
        # own, so falling through to `stand` is a mistake rather than a default
        # — a pose silently wearing the wrong legs still renders.
        leg_key = pose if pose in legs else "stand"
        eye_dy = POSE_EYE_DY[key].get(pose, 0)
        grid = compose(brand, body, legs[leg_key], EYES[eye],
                       body_dy=body_dy, eye_dy=eye_dy)
        # Lean and foreshortening are applied to the finished frame rather than
        # to the body. The flood fill has already run on a closed shape by
        # then, so neither can leak, and pivoting the lean at the feet leaves
        # the legs where they were planted while the head travels.
        grid = sway(grid, POSE_TILT.get(pose, 0))
        out[name] = squeeze(grid, POSE_SQUEEZE.get(pose, 0))

    # Swing poses are the dangle sheared, not redrawn: the shape is identical
    # and only its lean changes, so authoring them separately would be four
    # more grids to keep in step with the one that matters.
    base = out["dangle_wide"]
    for lean_step, lean in LEANS.items():
        leaned = shear(base, lean)
        for wob_step, wob in WOBBLES.items():
            out[wobble_frame(lean_step, wob_step)] = stretch_rows(leaned, wob)

    # A nod and a head shake, made from the standing frames rather than from
    # two more drawings of them. There is no neck here, so the whole creature
    # is the head: the nod is a one-row drop and the shake is the drag's own
    # lean with the pivot moved to the feet.
    #
    # The dip goes one row below where it stands, and stays there. Nothing is
    # drawn under the character, so what reads is the weight going down, and
    # the recovery through the existing raised frame gives the movement its
    # return. The shake borrows the rolled eyes, because a head shake and a
    # pair of eyes going up are the same sentence.
    out["nod_down"] = _shift(out["stand_open"], 1)
    out["shake_left"] = sway(out["stand_roll"], -2)
    out["shake_right"] = sway(out["stand_roll"], 2)
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
    # The shadow is not a frame. No mirror is baked for it — an ellipse is its
    # own mirror, and a `shadow:flip` key would only be one more thing that can
    # be asked for and drawn instead. Nothing animates it either: it is one
    # image, handed over for the painter to put under the feet on the frames
    # where there are feet on the floor.
    sheet["shadow"] = to_qimage(SHADOW, SHADOW_PALETTE, scale)
    return sheet

