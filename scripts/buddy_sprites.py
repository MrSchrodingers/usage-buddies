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
    # Waving without an arm, because Clawd has none. The gesture is the body
    # swinging over its feet; the leg is the accent on it, not the gesture.
    #
    # The first version reached a leg out sideways along the floor row. On a
    # creature whose legs are two-pixel stubs that is not a limb in the air, it
    # is a skid mark: a horizontal bar at ground level reads as something being
    # dragged. What says "off the ground" at this size is the gap underneath. So
    # the raised leg loses its lower two rows entirely and leaves them empty,
    # and it is drawn one column forward of where it stands, so the pair of
    # frames reads as one leg going up and coming down in the same place rather
    # than as two different legs.
    "wave0": [
        "......oooooooooooooooo......",
        "......ss..ss....ss...ss.....",
        "......ss..ss....ss..........",
        "......oo..oo....oo..........",
    ],
    "wave1": [
        "......oooooooooooooooo......",
        "......ss..ss....ss...ss.....",
        "......ss..ss....ss...ss.....",
        "......oo..oo....oo...oo.....",
    ],
    # Pointing. The whole animal aims: the body leans hard forward, the rearmost
    # leg curls up off the floor with the weight leaving it, and the front leg
    # goes out ahead with a bend in it and its foot a row clear of the ground.
    # Two legs stay planted under the middle, which is what stops a lunge from
    # reading as a fall.
    #
    # The foot being a row up is the whole difference. Drawn on the floor row
    # the same leg was a line coming out of the body — it pointed at nothing,
    # because a limb touching the ground is a limb standing on it.
    "point": [
        "......oooooooooooooooo......",
        "......ss..ss....ss..ss......",
        "..........ss....ss...ssoo...",
        "..........oo....oo..........",
    ],
    # Reading: hunched over the thing being read. The legs fold by a row and the
    # body comes down onto them, and the object itself is not in this band at
    # all — see POSE_PROP. It used to be drawn down here beside the feet, where
    # a four-pixel block detached from the body read as a dropped crumb.
    "read": [
        "......oooooooooooooooo......",
        "......ss..ss....ss..ss......",
        "......oo..oo....oo..oo......",
        "............................",
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
    # Sat down: the body drops a row onto two folded talons. Both of them, and
    # the same length. The first attempt ran the front one out into a six-pixel
    # bar to say "perched", and an orange bar along the floor beside a normal
    # foot reads as the bird having slipped, not as it having sat.
    "sit": [
        "......oooooooooooooooo......",
        "..........aa....aa..........",
        ".........aaa....aaa.........",
        "............................",
    ],
    # One talon up, one planted. Two legs mean the planted one keeps every pixel
    # it had — lifting both is a hop — and mean the raised one has to be
    # unmistakable, so it loses its lower two rows and stands one column forward
    # of where it lands in the other frame. The gap under it is the gesture.
    "wave0": [
        "......oooooooooooooooo......",
        "..........aa.....aa.........",
        "..........aa................",
        ".........aaa................",
    ],
    "wave1": [
        "......oooooooooooooooo......",
        "..........aa.....aa.........",
        "..........aa.....aa.........",
        ".........aaa....aaa.........",
    ],
    # Aiming. The rear talon stays down and keeps the whole bird up — there is
    # no third leg to spare — and the front one goes out ahead of it with its
    # foot a row clear of the floor.
    "point": [
        "......oooooooooooooooo......",
        "..........aa....aa..........",
        "..........aa.....aaaa.......",
        ".........aaa................",
    ],
    # Hunched over the page. The talons fold in under the body by a row and the
    # object has left this band entirely — see POSE_PROP.
    "read": [
        "......oooooooooooooooo......",
        "..........aa....aa..........",
        "..........aaa..aaa..........",
        "............................",
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


# ── the hoop ───────────────────────────────────────────────────────────────
# Hold the character long enough and a basket appears somewhere on the screen
# to throw it at. The art of the target is here. Where it appears and whether a
# throw went in are decided elsewhere, from HOOP_RIM below.
#
# Its own canvas and its own palette. 96 by 72 source pixels at the same
# integer SCALE as everything else, which is 192 by 144 on screen. Everything
# else in this file is 28 by 28 and the tests sweep for exactly that, so these
# grids are excluded there by name — sweeping them in asserts a 28-wide grid
# against a 96-wide one.
#
# The first version was 64 by 48 and it was wrong for a reason no test caught.
# Its opening came to 44 screen pixels; the character thrown at it is 56 wide.
# A basket narrower than the thing you throw into it reads as impossible, and
# it was not — the hit test scores a throw that passes within half a sprite of
# the middle, so it was easy and looked unmakeable. A drawing that promises
# less than the rule delivers is worse than one that promises too much: it
# teaches the player not to aim. The opening is now 76 screen pixels, which is
# the character plus a fifth of it either side.
#
# The legend is this palette's, not the body's. A letter means a colour in the
# palette it is drawn with:
#   .  transparent    o  outline
#   b  board          s  board shade     t  target rectangle
#   r  rim            h  rim highlight   k  rim, far side
#   n  net cord       u  net cord behind
#
# `d` and `m` are avoided on purpose: they are the shadow's two characters, and
# a letter meaning one thing in SHADOW and another here is the confusion that
# comment is about.

HOOP_W, HOOP_H = 96, 72

# The outline is dark and warm rather than black, for the reason given under
# PALETTES. The rim carries the only saturated hue in the drawing: without it
# the silhouette is a pale rectangle with a smaller rectangle inside it, which
# is a window, not a basket.
HOOP_PALETTE = {
    "o": "#43291B", "b": "#F0E3D2", "s": "#C9B49A", "t": "#C2521F",
    "k": "#B4531F", "r": "#EE7A31", "h": "#FFB067",
    "n": "#D6BC99", "u": "#8F7355",
}

# The board and the ring in one grid, because neither of them moves.
#
# The ring is drawn as a ring: an outlined ellipse with nothing inside it, so
# the wallpaper shows through the basket and the opening is a hole rather than
# a lighter patch of paint. That hole is what the player aims at and it is the
# one thing here that has to be unmistakable at 192 by 144 over someone else's
# desktop. Its far half is a step darker than its near half, which is what
# stops the ellipse from reading as a flat washer seen face on.
#
# The net's rows are left empty; it is a band, below.
HOOP_BOARD = [
    "................................................................................................",
    "...............oooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooo...............",
    "...............obbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbttttttttttttttttttttttbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbtbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbttttttttttttttttttttttbbbbbbbbbbbbbbbbbbbbso...............",
    "...............obbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbso...............",
    "...............osssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssso...............",
    "...............oooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooo...............",
    "...................................oooookkkkkkkkkkkkkkkkooooo...................................",
    "................................oookkkkkkkkkkkkkkkkkkkkkkkkkkooo................................",
    "..............................ookkkkkkkkooooooooooooooookkkkkkkkoo..............................",
    "............................ookkkkkooooo................oooookkkkkoo............................",
    "...........................okkkkoo............................ookkkko...........................",
    "..........................okkkoo................................ookkko..........................",
    ".........................ohhho....................................ohhho.........................",
    ".........................orro......................................orro.........................",
    ".........................orro......................................orro.........................",
    ".........................orrro....................................orrro.........................",
    "..........................orrhoo................................oohrro..........................",
    "...........................orrhhoo............................oohhrro...........................",
    "............................oorrhhhooooo................ooooohhhrroo............................",
    "..............................oorrrhhhhhoooooooooooooooohhhhhrrroo..............................",
    "................................ooorrrrrhhhhhhhhhhhhhhhhrrrrrooo................................",
    "...................................ooooorrrrrrrrrrrrrrrrooooo...................................",
    "........................................oooooooooooooooo........................................",
    "................................................................................................",
    "................................................................................................",
    "................................................................................................",
    "................................................................................................",
    "................................................................................................",
    "................................................................................................",
    "................................................................................................",
    "................................................................................................",
    "................................................................................................",
    "................................................................................................",
    "................................................................................................",
    "................................................................................................",
    "................................................................................................",
    "................................................................................................",
    "................................................................................................",
    "................................................................................................",
    "................................................................................................",
    "................................................................................................",
    "................................................................................................",
    "................................................................................................",
    "................................................................................................",
    "................................................................................................",
    "................................................................................................",
    "................................................................................................",
]

# ── the net ────────────────────────────────────────────────────────────────
# Cropped bands, for the same reason the legs are: the net is the only part of
# the basket that moves, and a twenty-seven-row diff is legible where a
# seventy-two-row one is not. Band row 0 falls inside the ring's own rows, so every cord
# starts at a pixel the ring is already covering and there is no seam to see.
#
# The band goes on *behind* the board grid: a cord is only drawn where the
# board left the pixel transparent. Drawn over, the cords notch the ring's
# outline everywhere the two overlap and a ring with holes in its edge stops
# reading as a ring.
#
# Three states, one drawing each:
#   hang    at rest, tapering to about half the rim's width
#   swish   a ball has just gone through: pulled down and bellied out in the
#           middle, which is the whole of what a made basket looks like
#   recoil  the snap back, swung to one side and shorter than it hangs
#
# The cords are in two tones and neither of them is white. A net in the
# lightest colour there is disappears against a pale wallpaper, which is the
# trap the legs avoid by being shade rather than outline. Two steps down from
# white, which is where these are, they hold against a near-white wallpaper
# and still read as cord rather than as shadow against a dark one. The first
# pass was one step down and it washed out on white at the size it is drawn.
# The two tones are the cords in front and the cords behind, which is what
# makes the mesh read as woven instead of as a printed pattern.
HOOP_NET_ROW = 44

HOOP_NETS = {
    "hang": [
        ".............................n....................................n.............................",
        "..............................n..n............................n..n..............................",
        "..............................n..un...n..................n...nu..n..............................",
        "...............................n.u.n..un...n........n...nu..n.u.n...............................",
        "................................un..nu..n.u.n..uu..n.u.n..un..nu................................",
        "................................u.n.nu..n.u.n..uu..n.u.n..un.n.u................................",
        "................................u.n..u...nu..nu..un..un...u..n.u................................",
        "................................n..nu.n..un...u..u...nu..n.un..n................................",
        ".................................n..n..nu.n..u.nn.u..n.un..n..n.................................",
        ".................................n..un..n..nnu.nn.unn..n..nu..n.................................",
        "..................................n.un..un..un....nu..nu..nu.n..................................",
        "...................................nu.n.unnu.n.uu.n.unnu.n.un...................................",
        "...................................un..u..nu..nuun..un..u..nu...................................",
        "...................................u.n.u...u..u..u..u...u.n.u...................................",
        "...................................u..u.n.u.n.unnu.n.u.n.u..u...................................",
        "...................................n..n..nu.nu.nn.un.un..n..n...................................",
        "....................................n.un..n..n....n..n..nu.n....................................",
        ".....................................nun.unnun....nunnu.nun.....................................",
        ".....................................nu.nu.nu.nuun.un.un.un.....................................",
        "......................................u.un.uu.uuuu.uu.nu.u......................................",
        ".....................................u.nun.un.unnu.nu.nun.u.....................................",
        ".....................................u.nu.nu.nu..un.un.un.u.....................................",
        ".....................................u..u.u..u....u..u.u..u.....................................",
        "................................................................................................",
        "................................................................................................",
        "................................................................................................",
        "................................................................................................",
    ],
    "swish": [
        ".............................n....................................n.............................",
        ".............................n...n............................n...n.............................",
        "..............................n..un...n..................n...nu..n..............................",
        "..............................n.u.n...un...n........n...nu...n.u.n..............................",
        "...............................nu..n.u.n..u.n..uu..n.u..n.u.n..un...............................",
        "...............................un...nu..n.u.n..uu..n.u.n..un...nu...............................",
        "...............................u.n..u...nu...nu..un...un...u..n.u...............................",
        "...............................u..n.un...u....u..u....u...nu.n..u...............................",
        "..............................n...nu..n.u.n..un..nu..n.u.n..un...n..............................",
        "...............................n...n..n.u.n..u.nn.u..n.u.n..n...n...............................",
        "................................n..n...n...nn..nn..nn...n...n..n................................",
        "................................n.u.n..un..un......nu..nu..n.u.n................................",
        ".................................nu..n.un..u.n.uu.n.u..nu.n..un.................................",
        "..................................u..nu..nu..n.uu.n..un..un..u..................................",
        "..................................un..u...u...u..u...u...u..nu..................................",
        "..................................u.n.un..un..u..u..nu..nu.n.u..................................",
        "..................................u.nu.n.u.n.u.nn.u.n.u.n.un.u..................................",
        ".................................n...n..nu..nu.nn.un..un..n...n.................................",
        "..................................n..un..n..n......n..n..nu..n..................................",
        "...................................nnun.unn.un....nu.nnu.nunn...................................",
        "....................................nu.nu.n.un.uu.nu.n.un.un....................................",
        ".....................................u..u..uu.nuun.uu..u..u.....................................",
        ".....................................un.u..un.unnu.nu..u.nu.....................................",
        ".....................................un.un.un.unnu.nu.nu.nu.....................................",
        ".....................................u.nu.nu.nu..un.un.un.u.....................................",
        ".....................................u..u.u..u....u..u.u..u.....................................",
        "................................................................................................",
    ],
    "recoil": [
        ".............................n....................................u.............................",
        "..............................n..n.............................n..u.............................",
        "...............................nnun...n...................n...un.u..............................",
        ".................................u.nn.un...n....n....n...un..u.nu...............................",
        ".................................uu..nu.n..un...un..u.n.u..n.u.u................................",
        "..................................un..u..nu..n.u..n.u.n.u..uu.u.u...............................",
        "..................................n.n.un..u...nu..nu...u..un..uu................................",
        "...................................n.nn.n.un..un..un..u.nu..nu.u................................",
        "....................................n.n..n..n.u.n.u.nu..n..un.u.................................",
        "....................................n.un.un..n...n...n..un.u.nu.................................",
        ".....................................nu.nu.n.un.un..un.u.nu..u..................................",
        "......................................u..u..nu.nu.n.u.nu..u.un..................................",
        "......................................un.un.u..nu..u..un.un.un..................................",
        "......................................n.nu.nun.un..u..unu.nu..u.................................",
        "......................................n..n..n.nu.nu.nu..n..n.u..................................",
        ".......................................n.n.un.un.un.un.un.un.u..................................",
        "........................................u.nu.nu.nu.nu.nu.nu.uu..................................",
        "........................................u..u..u..u.nu.u..uu.u...................................",
        "........................................un.un.u.un.un.un.unu.n..................................",
        "........................................u.u.nu.nu.nu.nunu.nu.n..................................",
        "........................................u.u..u..u.u..u..u..u..n.................................",
        "................................................................................................",
        "................................................................................................",
        "................................................................................................",
        "................................................................................................",
        "................................................................................................",
        "................................................................................................",
    ],
}

# The opening, in source pixels, as (left, top, width, height). The hole is an
# ellipse and this is the box around it, so the corners of the box are on the
# ring rather than through it.
#
# It lives with the art because the art is what knows where the hole is. The
# same four numbers written again beside whatever decides that a throw scored
# are two truths, and they diverge the first time the ring moves by a pixel.
# The other side is free to be more generous than this — a basket that only
# counts on a pixel-perfect line through the middle is an exam, not a joke —
# but it should be generous about a number that came from here.
HOOP_RIM = (29, 34, 38, 10)

# Same shape as CLIPS and a table of its own. CLIPS is the character's: it is
# what the Animator resolves names against and what the tests sweep for frames
# build_frames can produce, so a hoop frame listed there is a name that
# resolves to nothing on the character's sheet. Whoever animates the basket
# steps through this table itself.
#
# Non-uniform for the reason every clip in this file is: the snap back is
# quicker than the stretch that caused it, and the hold at the end is what says
# the ball has gone through and stopped mattering.
HOOP_CLIPS = {
    "score": {"loop": False, "frames": [("hoop_swish", 80), ("hoop_recoil", 120),
                                        ("hoop_swish", 90), ("hoop_hang", 240)]},
}


def build_hoop(net="hang"):
    """The board, the ring and one net band, as one HOOP_W by HOOP_H grid."""
    grid = [list(row) for row in HOOP_BOARD]
    for r, row in enumerate(HOOP_NETS[net]):
        rr = HOOP_NET_ROW + r
        if not 0 <= rr < HOOP_H:
            continue
        for c, ch in enumerate(row):
            # Behind the ring, never over it: see the note above the bands.
            if ch != "." and grid[rr][c] == ".":
                grid[rr][c] = ch
    return ["".join(row) for row in grid]


def build_hoop_frames():
    """Every hoop frame as an ASCII grid, keyed by the names HOOP_CLIPS uses.

    The `hoop_` prefix is not decoration. These frames end up in a dictionary
    beside the character's, and `swish` next to `stand_open` is two canvases
    and two palettes under names that look like they belong together.
    """
    return {"hoop_" + name: build_hoop(name) for name in HOOP_NETS}


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


def sway_shift(rows, lean, row):
    """How far sway moves one particular row.

    So that a rigid part of a drawing can be placed onto a leaned body instead
    of being leaned with it. A shear moves every row by a different amount, and
    anything small that straddles the row where the amount changes comes apart:
    Rex's three-pixel beak leaned into two pieces with a step between them, and
    a square eye leaned into two half-eyes. Bodies shear; faces do not.

    Matches sway exactly, which is why it is written from the same numbers
    rather than measured off the result.
    """
    filled = [i for i, r in enumerate(rows) if set(r) != {"."}]
    if not filled or lean == 0:
        return 0
    top, bottom = filled[0], filled[-1]
    return round(lean * (bottom - row) / max(1, bottom - top))


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


def add_prop(rows, prop):
    """Paste a rigid object onto a finished frame.

    After the flood fill, so it cannot change what the body's interior is, and
    after the lean, so that the thing being held keeps its own shape while the
    creature holding it bends.
    """
    top, left, band = prop
    grid = [list(row) for row in rows]
    _paste(grid, top, left, band)
    return ["".join(row) for row in grid]


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


def compose(brand, body, legs, eyes, body_dy=0, eye_dy=0, tilt=0):
    """One frame: body, legs, face, all shifted together by the bob.

    The legs move with the body rather than staying pinned to the floor. Pinned
    feet sound more correct and render worse: the band's first row is the
    body's ground outline, so when the body rises one row the outline is drawn
    twice, one row apart, and the character grows a two-pixel black bar across
    its base on every other frame. Letting the whole creature rise is also what
    a walk actually does — feet leave the ground.

    `tilt` leans the body and only the body. The legs go on straight, because a
    lean is weight travelling forward over feet that stay where they were, and
    the face goes on afterwards at the column the head moved to rather than
    being leaned with it: a shear moves every row by its own amount, and a beak
    or a square eye that straddles the row where the amount changes comes apart
    into two offset halves.

    The order below is the whole trick and it was arrived at by getting it
    wrong. Filling first and leaning the solid body is safe; leaning the drawing
    and filling afterwards is not. The `h` and `s` hints seal steps of two
    columns, and a shear changes the offset between one row and the next, so a
    step the hints were closing opens by a column somewhere along the body and
    the flood walks in. The result is a hollow outline of a leaning creature.
    Once the interior is filled there is nothing left to leak into.
    """
    filled = ["".join(row) for row
              in _fill_interior([list(row) for row in _shift(body, body_dy)])]
    leaned = sway(filled, tilt) if tilt else filled
    grid = [list(row) for row in leaned]
    if brand == "codex":
        leg_row, er, ec, gap = CODEX_LEG_ROW, CODEX_EYE_ROW, CODEX_EYE_COL, CODEX_EYE_GAP
    else:
        leg_row, er, ec, gap = LEG_ROW, EYE_ROW, EYE_COL, EYE_GAP
    if legs is not None:
        _paste(grid, leg_row + body_dy, 0, legs)
    if brand == "codex":
        btop, bleft, band = CODEX_BEAK
        beak_row = btop + body_dy + eye_dy
        _paste(grid, beak_row, bleft + sway_shift(filled, tilt, beak_row), band)
    if eyes is not None:
        left, right = _eye_bands(eyes)
        width = len(left[0])
        eye_row = er + body_dy + eye_dy
        dx = sway_shift(filled, tilt, eye_row)
        _paste(grid, eye_row, ec + dx, left)
        _paste(grid, eye_row, ec + width + gap + dx, right)
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
    # Reading is hunched: the body drops a row onto a leg band drawn a row
    # shorter, the same way sitting does, and leans out over the page. The three
    # frames differ by the eyes alone — the book is a rigid object pasted after
    # the lean, and a book that bobs with the reader is worse than a still one.
    "read_half":      ("read", "half", 1),
    "read_open":      ("read", "open", 1),
    "read_side":      ("read", "side", 1),
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

# The wave is the only place a tilt does the whole job. Its two frames lean
# opposite ways, five columns apart at the head, which is what makes them tell
# themselves apart across a room; two frames leaning the same way by one column
# were a creature standing still with a leg problem.
POSE_TILT = {"wave0": -3, "wave1": 2, "point": 3, "read": 3,
             "type0": 1, "type1": 2}
POSE_SQUEEZE = {"turn": 4}
POSE_CUT = {"peek": {"claude": 14, "codex": 15}}

# A prop is an object the character holds: its own small grid, pasted onto the
# finished frame. Three things it has to do, each of them learned by doing the
# opposite first.
#
#   It needs an outline of its own. Without one it is a coloured smudge, and at
#   four pixels across a smudge is not a thing, it is a mistake.
#
#   It is in the accent hue in both brands. Drawn in the body's own colours it
#   disappeared into Rex completely — the same shape, the same blue, no edge.
#
#   It touches the body. An object floating beside a character is not held by
#   it; on Clawd the first version read as a crumb dropped on the floor.
#
# It is pasted after the lean rather than before, which is the whole difference
# between something held and something painted on: the creature shears when it
# leans, and a rigid thing in front of it does not.

PROP_BOOK = [
    "ooooo",
    "oaaao",
    "oaaao",
    "ooooo",
]

# Held against the chest, under the face and over the front edge of the body,
# with its outline crossing the body's own. That crossing is what says "in
# front of"; placed clear of the body it was a gold square floating beside the
# hip, and placed down by the feet it was something the creature had dropped.
POSE_PROP = {"read": {"claude": (15, 23, PROP_BOOK),
                      "codex": (14, 23, PROP_BOOK)}}

# The leg each pose lifts, as the columns it stands on when it is down. Legs
# this short cannot gesture by reaching: a two-pixel stub stretched out along
# the floor row reads as a skid, not as a limb in the air. What reads is the
# gap underneath, so a raised leg has to leave the floor row empty across its
# whole width — which is a thing a test can check, and does.
#
# Poses that lift everything at once are not here; they are in
# OFF_GROUND_POSES, because nothing is left standing to compare them against.
RAISED_LEGS = {
    "claude": {"wave0": [(21, 22)], "point": [(6, 7), (20, 24)]},
    "codex":  {"wave0": [(17, 18)], "point": [(16, 20)]},
}

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
                       body_dy=body_dy, eye_dy=eye_dy,
                       tilt=POSE_TILT.get(pose, 0))
        # Held objects go on after the lean, and the foreshortening of a turn
        # goes on after everything: dropping columns out of a finished frame
        # cannot leak, because the flood fill has already run on a closed shape.
        if pose in POSE_PROP:
            grid = add_prop(grid, POSE_PROP[pose][key])
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


def build_hoop_sheet(scale=SCALE):
    """The hoop's frames as QImages, keyed as build_hoop_frames names them.

    Its own sheet rather than more keys in build_sheet. build_sheet takes a
    brand and the hoop has none; every image it hands back is the character's
    canvas and this one is not; and it paints with the brand palette, in which
    `t`, `k`, `n` and `u` do not exist while `b`, `s` and `h` exist and mean
    body colours. The first two go wrong in silence and the third raises.

    No `:flip` keys. A basket has no direction to face, so a mirrored one is
    one more image that can be asked for and drawn by mistake — the same
    argument as the shadow's.

    `scale` is here rather than fixed because the basket has to be worth
    aiming at: nothing in the grid assumes 2, and drawing it at 3 gives a
    target half again as wide without a second drawing of it. Any integer is
    safe; a fraction is not, for the reason at the top of this file.

    Whatever is passed here is also what HOOP_RIM has to be converted with by
    whoever judges a throw. Drawn at one scale and judged at another, the
    basket is one size to look at and another size to hit, and the only
    symptom is that it feels wrong.
    """
    return {name: to_qimage(grid, HOOP_PALETTE, scale)
            for name, grid in build_hoop_frames().items()}
