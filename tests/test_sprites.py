"""The sprite system: the grids, the playback clock, and the paint contract.

Pixel art has a small number of ways to go wrong, and every one of them was hit
while building this. The tests below are each pinned to one of them, so a
regression names itself instead of just looking slightly off.
"""
import importlib.util
import os
import random
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import buddy_sprites as sprites

BRANDS = ("claude", "codex")
LEGAL = set(".osbhwpa")


def _bounds(grid):
    rows = [i for i, r in enumerate(grid) if set(r) != {"."}]
    return (rows[0], rows[-1]) if rows else (0, 0)


def _ink(grid):
    return sum(1 for row in grid for ch in row if ch != ".")


# ── the grids ──────────────────────────────────────────────────────────────

# CAR_* excluded: the car has its own canvas and its own palette, and is
# checked by tests/test_drag_behaviour.py. Sweeping it in here asserted a
# 28-wide grid against a 128-wide one.
#
# SHADOW excluded for the same reason and not as a favour: it is three rows
# rather than twenty-eight and its two characters are deliberately outside the
# body alphabet, because a character cannot mean a body colour in one grid and
# a shadow colour in another. It has its own test below.
#
# PROP_* excluded because a prop is a small band like the eye and leg bands,
# not a body: it is four rows square and it is pasted at an offset. The bands
# inside the dictionaries are not swept here either, for the same reason.
#
# HOOP_* excluded on the car's precedent, which is exactly what it is: 96 by 72
# on a canvas of its own, in a palette of its own where `b`, `s` and `h` name
# board colours rather than body ones. Swept in here it asserts a 28-wide grid
# against a 96-wide one and it fails on the first row. It has its own tests
# below, and the exclusion has its own test too — one that fails if it grew
# wide enough to stop the sweep watching the bodies.
def _swept_grid_names():
    """The module-level grids the 28-square sweep covers.

    A function rather than a comprehension inside the decorator so that the
    test which checks *what* is excluded reads the same list the sweep runs on.
    Two copies of this filter is how an exclusion widens on one side only.
    """
    return [n for n in dir(sprites)
            if n.isupper() and not n.startswith("CAR_")
            and not n.startswith("HOOP_")
            and not n.startswith("SHADOW")
            and not n.startswith("PROP_")
            and isinstance(getattr(sprites, n), list)
            and getattr(sprites, n)
            and isinstance(getattr(sprites, n)[0], str)]


@pytest.mark.parametrize("name", _swept_grid_names())
def test_every_body_is_a_square_grid_of_known_colours(name):
    """A row one character short shifts every pixel after it by one."""
    grid = getattr(sprites, name)
    assert len(grid) == sprites.GRID, f"{name}: {len(grid)} rows"
    for i, row in enumerate(grid):
        assert len(row) == sprites.GRID, f"{name} row {i}: {len(row)} columns"
        assert set(row) <= LEGAL, f"{name} row {i}: {set(row) - LEGAL}"


def _hollow_at(grid):
    """Rows through the widest part of the body that have transparent pixels
    inside the silhouette. That is what a leaked flood fill looks like."""
    top, bottom = _bounds(grid)
    found = []
    for row in range(top + (bottom - top) // 3, top + (bottom - top) // 2 + 1):
        cols = [c for c, ch in enumerate(grid[row]) if ch != "."]
        if len(cols) < 2:
            continue
        gap = [c for c in range(cols[0], cols[-1] + 1) if grid[row][c] == "."]
        if gap:
            found.append((row, gap))
    return found


@pytest.mark.parametrize("brand", BRANDS)
def test_no_pose_renders_hollow(brand):
    """The flood fill finds the interior by what it cannot reach from outside.

    A row that widens by three columns over the one above leaves a gap the
    flood pours through, and the whole body comes out empty with an outline
    around it. It looks like a deflated balloon and it is entirely silent —
    nothing raises, nothing warns.
    """
    for name, grid in sprites.build_frames(brand).items():
        assert not _hollow_at(grid), f"{brand}/{name}: hollow at {_hollow_at(grid)}"


def test_the_hollow_check_can_still_see_a_hollow_body():
    """The check above is a sweep over whatever build_frames produced, so it
    passes just as happily if it has stopped looking at anything. This hands it
    a body with a three-column step in it — the exact edit that leaks — and
    fails if it comes back clean."""
    leaky = [row for row in sprites.CLAUDE_BODY]
    leaky[10] = "o.......................o..."   # three columns wider, unshaded
    grid = sprites.compose("claude", leaky, sprites.CLAUDE_LEGS["stand"],
                           sprites.EYES["open"])
    assert _hollow_at(grid), "the flood leaked and the probe did not notice"


@pytest.mark.parametrize("brand", BRANDS)
def test_the_hollow_check_sees_every_pose_and_not_just_the_old_ones(brand):
    """A pose is only checked if a frame in the table draws it. A new pose
    added with no frame naming it is a drawing nothing renders and nothing
    tests, and it stays that way until someone puts it in a clip and it comes
    out hollow on a desktop."""
    swept = {pose for pose, _eye, _dy in sprites.FRAME_SPECS.values()}
    legs = sprites.CODEX_LEGS if brand == "codex" else sprites.CLAUDE_LEGS
    unused = set(legs) - swept
    assert not unused, f"{brand}: leg bands no frame uses: {sorted(unused)}"


@pytest.mark.parametrize("brand", BRANDS)
def test_every_pose_stands_on_the_same_ground(brand):
    """Squash has to compress against the floor.

    A squash that is shorter *and* floats reads as the creature shrinking. The
    ground row is the contract that makes squash mean weight.
    """
    grounds = {}
    for pose, attr in sprites._BODIES[brand].items():
        body = getattr(sprites, attr)
        grounds[pose] = _bounds(body)[1]
    assert len(set(grounds.values())) == 1, f"poses end on different rows: {grounds}"


@pytest.mark.parametrize("brand", BRANDS)
def test_only_the_declared_poses_leave_the_floor(brand):
    """A pose that floats reads as the creature shrinking rather than moving.

    Two things are allowed to lift it. The bob a walk is built on, which raises
    the whole creature — feet included — by exactly the row it shifted, and the
    poses named in OFF_GROUND_POSES: peeking has no feet in the frame at all,
    and a celebration is a jump.

    "By exactly the row it shifted" is the load-bearing half. Letting any
    negative offset excuse any height made this test blind: the celebration
    lifts four rows through its leg band and one through its offset, and a
    version of this that only looked at the sign of the offset let it go
    undeclared. The assertion also runs the other way, so a pose declared
    airborne that in fact stands on the floor fails too — a list that may be
    wrong in one direction is not a list of anything.
    """
    frames = sprites.build_frames(brand)
    ground = _bounds(frames["stand_open"])[1]
    for name, (pose, _eye, body_dy) in sprites.FRAME_SPECS.items():
        bottom = _bounds(frames[name])[1]
        if pose in sprites.OFF_GROUND_POSES:
            assert bottom < ground, \
                f"{brand}/{name} is declared off the floor and stands on it"
        else:
            bobbed = body_dy < 0 and bottom == ground + body_dy
            assert bottom == ground or bobbed, \
                (f"{brand}/{name} ends on row {bottom}; the floor is row {ground} "
                 f"and the frame is offset by {body_dy}")


@pytest.mark.parametrize("brand", BRANDS)
def test_no_frame_lifts_the_body_off_the_top_of_the_grid(brand):
    """Rex's ear tufts start two rows down. A frame that lifts the body by
    three takes their tips off the edge of the canvas and the tufts come back
    as two floating marks over an earless owl. The shift is in range, nothing
    raises, and the symptom is one frame of one clip looking wrong."""
    for name, (pose, _eye, body_dy) in sprites.FRAME_SPECS.items():
        body = sprites.pose_body(brand, pose)
        lost = _ink(body) - _ink(sprites._shift(body, body_dy))
        assert lost == 0, f"{brand}/{name}: {lost} pixels shifted off the grid"


@pytest.mark.parametrize("brand", BRANDS)
def test_a_lean_does_not_shave_the_far_side_off_the_body(brand):
    """The horizontal twin of the clipping test above.

    A shear pads one side and truncates the other at the edge of the grid, so a
    tilt one column too large does not raise or warn: it takes a strip off the
    far side of the creature. Rex is two columns from the edge and leans by
    three, which is as much as fits, and the amount that fits is not something
    to keep in anyone's head.

    Composed twice, once flat and once leaning, and the pixels are counted.
    """
    legs = sprites.CODEX_LEGS if brand == "codex" else sprites.CLAUDE_LEGS
    for name, (pose, eye, body_dy) in sprites.FRAME_SPECS.items():
        tilt = sprites.POSE_TILT.get(pose, 0)
        if not tilt:
            continue
        body = sprites.pose_body(brand, pose)
        band = legs[pose] if pose in legs else legs["stand"]
        eye_dy = sprites.POSE_EYE_DY[brand].get(pose, 0)
        flat = sprites.compose(brand, body, band, sprites.EYES[eye],
                               body_dy, eye_dy, 0)
        leaning = sprites.compose(brand, body, band, sprites.EYES[eye],
                                  body_dy, eye_dy, tilt)
        lost = _ink(flat) - _ink(leaning)
        assert lost == 0, \
            f"{brand}/{name}: leaning by {tilt} pushed {lost} pixels off the grid"


@pytest.mark.parametrize("brand", BRANDS)
def test_a_raised_leg_never_touches_the_floor(brand):
    """A creature with two-pixel legs cannot gesture by reaching.

    The wave, the point and the read were all drawn first as a leg stretched
    out sideways along the floor row, four or five pixels of it, and all three
    read the same way: as a skid mark. A limb touching the ground is a limb
    standing on the ground, however long it is. What says "in the air" at this
    size is the gap underneath it, and nothing else does.

    So the poses that lift a leg declare which columns it stands on, and the
    floor row has to be empty across all of them. Both halves are checked: the
    leg also has to be drawn somewhere above the floor, or the declaration is
    describing a leg that is not there and the real assertion is vacuous.

    Poses that lift everything at once are not here — they are in
    OFF_GROUND_POSES, checked by the floor test above, because there is nothing
    left standing to compare them against.
    """
    legs = sprites.CODEX_LEGS if brand == "codex" else sprites.CLAUDE_LEGS
    for pose, spans in sprites.RAISED_LEGS[brand].items():
        band = legs[pose]
        drawn = [i for i, row in enumerate(band) if set(row) != {"."}]
        seam, floor = drawn[0], drawn[-1]
        assert floor - seam >= 2, f"{brand}/{pose}: this band has no legs in it"
        for lo, hi in spans:
            above = [band[i][lo:hi + 1] for i in range(seam + 1, floor)]
            assert any(set(part) != {"."} for part in above), \
                f"{brand}/{pose}: nothing drawn in columns {lo}-{hi} to be raised"
            assert set(band[floor][lo:hi + 1]) == {"."}, \
                (f"{brand}/{pose}: the leg declared raised is standing on the "
                 f"floor row at columns {lo}-{hi}")


@pytest.mark.parametrize("brand", BRANDS)
def test_only_squash_and_stretch_wear_another_pose_s_legs(brand):
    """build_frames falls back to the standing band for a pose that has none.

    That fallback renders something plausible and wrong — a sit wearing
    standing legs is a creature standing — and it renders it silently. Two
    poses use it on purpose: squash and stretch change the body and not the
    stance. A third name appearing here is a leg band nobody drew.
    """
    legs = sprites.CODEX_LEGS if brand == "codex" else sprites.CLAUDE_LEGS
    borrowed = {pose for pose, _eye, _dy in sprites.FRAME_SPECS.values()
                if pose not in legs}
    assert borrowed == {"squash", "stretch"}, f"{brand}: falls back for {borrowed}"


def test_the_shading_hints_are_load_bearing():
    """`h` and `s` close two-column steps; without them the flood leaks in.

    This is not a style assertion. Replacing the hints with transparency is
    exactly the edit that looks harmless and empties the body.
    """
    stripped = [row.replace("h", ".").replace("s", ".") for row in sprites.CLAUDE_BODY]
    grid = sprites.compose("claude", stripped, sprites.CLAUDE_LEGS["stand"],
                           sprites.EYES["open"])
    filled = sum(row.count("b") for row in grid)
    intact = sum(row.count("b") for row in sprites.build_frames("claude")["stand_open"])
    assert filled < intact, "removing the hints should have leaked; the test is blind"


# ── mirroring ──────────────────────────────────────────────────────────────

def _pupils(brand, grid):
    """Where the pupils sit inside each eye box, left box then right box.

    Read off the frame rather than off the EYES table, because the question is
    what compose pasted, not what was authored.
    """
    if brand == "codex":
        er, ec, gap = (sprites.CODEX_EYE_ROW, sprites.CODEX_EYE_COL,
                       sprites.CODEX_EYE_GAP)
    else:
        er, ec, gap = sprites.EYE_ROW, sprites.EYE_COL, sprites.EYE_GAP
    width = 4
    return [{(r - er, c - left) for r in range(er, er + width)
             for c in range(left, left + width) if grid[r][c] == "p"}
            for left in (ec, ec + width + gap)]


def test_a_paired_eye_is_used_as_drawn_and_a_single_one_is_still_mirrored():
    """Both halves of the rule carry weight.

    A single band has to keep being mirrored or every symmetric face starts
    drifting apart, one eye at a time. A pair has to be pasted as given or the
    glance it exists for comes out as `look`.
    """
    band = ["wwww", "ppww", "ppww", "wwww"]
    left, right = sprites._eye_bands(band)
    assert (left, right) == (band, sprites.mirror(band)), \
        "a single band stopped being mirrored"

    pair = (["wwww", "ppww", "ppww", "wwww"], ["wwww", "ppww", "ppww", "wwww"])
    assert sprites._eye_bands(pair) == pair, "a pair was not used as drawn"
    assert pair[1] != sprites.mirror(pair[0]), \
        "the pair is its own mirror; it would prove nothing"


@pytest.mark.parametrize("brand", BRANDS)
def test_a_glance_reaches_the_frame_without_being_mirrored(brand):
    """The right eye used to be built by mirroring whatever went on the left,
    so an asymmetric expression was not expressible at all: both pupils against
    the left edge came out as one pupil left and one right, which is a stare
    past either side of whatever is in front. This checks the pixels compose
    actually pasted, in both directions — the symmetric eyes have to stay
    symmetric too."""
    frames = sprites.build_frames(brand)
    left, right = _pupils(brand, frames["peek_side"])
    assert left and right, "no pupils found; this probe is reading the wrong rows"
    assert left == right, "the glance was mirrored: the pupils went to opposite edges"

    left, right = _pupils(brand, frames["stand_look"])
    assert left and right, "no pupils found in the mirrored face either"
    assert left != right, "a mirrored eye quietly stopped being mirrored"


@pytest.mark.parametrize("brand", BRANDS)
def test_mirroring_is_exact_and_reversible(brand):
    """The one transform allowed on a pixel grid, because it maps pixel
    centres onto pixel centres. Everything else resamples."""
    for name, grid in sprites.build_frames(brand).items():
        once = sprites.mirror(grid)
        assert sprites.mirror(once) == grid, f"{name}: flip is not an involution"
        for a, b in zip(grid, once):
            assert sorted(a) == sorted(b), f"{name}: flip changed the pixels"


# ── clips ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("brand", BRANDS)
def test_every_clip_names_a_frame_that_exists(brand):
    built = set(sprites.build_frames(brand))
    missing = sprites.frame_names() - built
    assert not missing, f"{brand}: clips reference {missing}"


def test_frames_do_not_all_run_at_one_rate():
    """A cycle at a constant rate reads mechanical. The walk is supposed to
    hold on contact and hurry through the pass, and every other clip has the
    same obligation: a wave with four equal frames is a windmill, a nod with
    four equal frames is a machine part. Uniform timing is the default a clip
    arrives with, so it is the thing worth failing on."""
    walk = [ms for _, ms in sprites.CLIPS["walk"]["frames"]]
    assert len(set(walk)) > 1, f"walk is a metronome: {walk}"

    for name, clip in sprites.CLIPS.items():
        timings = [ms for _, ms in clip["frames"]]
        assert len(timings) > 1, f"{name} is a single frame, not a clip"
        assert len(set(timings)) > 1, f"{name} is a metronome: {timings}"


# ── the contact shadow ─────────────────────────────────────────────────────

def test_the_contact_shadow_is_translucent_and_keeps_out_of_the_body_alphabet():
    """A shadow is the wallpaper darkened, not a grey shape laid on top of it.

    Opaque, it is a puddle the character is standing in, and on a dark
    wallpaper it is a bright one. And its characters have to stay out of
    ".osbhwpa": a character cannot mean a body colour in one grid and a shadow
    colour in another, and the body grids are swept for that alphabet.
    """
    assert sprites.SHADOW and sprites.SHADOW_PALETTE, "there is no shadow"
    for ch, value in sprites.SHADOW_PALETTE.items():
        assert len(value) == 9, f"{ch}: {value} carries no alpha channel"
        alpha = int(value[1:3], 16)
        assert 0 < alpha < 255, f"{ch}: alpha {alpha} is not a shadow"

    used = set("".join(sprites.SHADOW)) - {"."}
    assert used <= set(sprites.SHADOW_PALETTE), f"undrawable characters: {used}"
    assert not used & LEGAL, "the shadow is using the body's alphabet"


def test_the_shadow_is_wider_than_it_is_tall():
    """It is a contact shadow, seen from the front. Anything approaching round
    is a hole in the desktop, and anything as tall as the character is a second
    character lying under it."""
    rows = len(sprites.SHADOW)
    cols = max(len([c for c in row if c != "."]) for row in sprites.SHADOW)
    assert cols > rows * 2, f"{cols} wide by {rows} tall is not flat"


# ── the hoop ───────────────────────────────────────────────────────────────
# A second canvas in the same file, which is the situation the car was in when
# it was here. Everything below is about the two ways that goes wrong: the
# 28-square checks reaching a 96-wide grid, and the 96-wide grid escaping every
# check there is because it was excluded from all of them.

HOOP_LEGAL = set(".obstkrhnu")
HOOP_RING = set("rhko")
HOOP_BOARD_PAINT = set("bst")


def test_the_hoop_grids_are_rectangles_of_their_own_colours():
    """A row one character short shifts every pixel after it by one, and on a
    96-wide grid that is a whole ring sliding off its board.

    The alphabet is checked against HOOP_PALETTE and not against the body's:
    `b` is the board here and the creature there, and a character with no entry
    in the palette it is painted with raises at paint time, on a machine with a
    display, which is not where the tests run.
    """
    assert set(sprites.HOOP_PALETTE) <= HOOP_LEGAL, "the palette grew a letter"
    grids = {"HOOP_BOARD": sprites.HOOP_BOARD}
    grids.update({f"HOOP_NETS[{k!r}]": v for k, v in sprites.HOOP_NETS.items()})
    grids.update(sprites.build_hoop_frames())
    for name, grid in grids.items():
        assert grid, f"{name} is empty"
        for i, row in enumerate(grid):
            assert len(row) == sprites.HOOP_W, \
                f"{name} row {i}: {len(row)} columns, not {sprites.HOOP_W}"
            assert set(row) <= HOOP_LEGAL, f"{name} row {i}: {set(row) - HOOP_LEGAL}"
            assert set(row) - {"."} <= set(sprites.HOOP_PALETTE), \
                f"{name} row {i}: undrawable in HOOP_PALETTE"
    assert len(sprites.HOOP_BOARD) == sprites.HOOP_H
    for name, grid in sprites.build_hoop_frames().items():
        assert len(grid) == sprites.HOOP_H, f"{name}: {len(grid)} rows"


def test_every_hoop_colour_is_drawn_and_every_drawn_colour_has_a_colour():
    """A palette entry nothing uses is a colour someone chose and then lost;
    a character no palette has is a KeyError the moment it is painted."""
    used = {ch for grid in sprites.build_hoop_frames().values()
            for row in grid for ch in row} - {"."}
    assert used == set(sprites.HOOP_PALETTE), \
        f"drawn but unpainted: {used - set(sprites.HOOP_PALETTE)}; " \
        f"painted but undrawn: {set(sprites.HOOP_PALETTE) - used}"


def test_the_hoop_is_out_of_the_28_square_sweep_and_the_bodies_are_still_in_it():
    """Both halves, because the cheap way to pass the first is to break the
    second.

    The sweep asserts GRID rows of GRID columns. HOOP_BOARD is 72 of 96 and has
    to be excluded or it fails on its first row. But an exclusion is a hole in
    the net, and one written a little too wide — matching on `HOO`, or on any
    name with an underscore in it — stops the sweep watching the creatures it
    was written for, and nothing says so.
    """
    swept = _swept_grid_names()
    assert "HOOP_BOARD" not in swept, "the 96-wide grid is in the 28-square sweep"
    for name in ("CLAUDE_BODY", "CLAUDE_SQUASH", "CLAUDE_STRETCH",
                 "CODEX_BODY", "CODEX_SQUASH", "CODEX_STRETCH"):
        assert name in swept, f"the sweep has stopped looking at {name}"


def test_the_score_clip_names_frames_that_exist_and_does_not_run_at_one_rate():
    """A clip is names and durations, and both go wrong quietly.

    A renamed frame is a KeyError on the one occasion the animation plays,
    which is the moment someone finally landed the throw. And a made basket at
    a constant frame rate is a slideshow: the snap back has to be quicker than
    the stretch that caused it, or the net reads as sliding rather than
    springing.
    """
    built = set(sprites.build_hoop_frames())
    for name, clip in sprites.HOOP_CLIPS.items():
        named = {f for f, _ in clip["frames"]}
        assert named <= built, f"{name} references {named - built}"
        timings = [ms for _, ms in clip["frames"]]
        assert len(timings) > 1, f"{name} is a single frame, not a clip"
        assert len(set(timings)) > 1, f"{name} is a metronome: {timings}"


def test_the_declared_opening_is_the_hole_and_not_the_middle_of_the_board():
    """HOOP_RIM is where a throw has to arrive, and it is four numbers.

    Four numbers are wrong silently: a box on the backboard is still a box on
    the drawing, and the only symptom is that hitting the target does nothing
    while hitting the board scores. So it is checked against the pixels — the
    box has to sit below the board, hold no board paint, and be open along its
    middle row with ring either side of it.
    """
    left, top, width, height = sprites.HOOP_RIM
    assert 0 <= left and left + width <= sprites.HOOP_W, "the box leaves the grid"
    assert 0 <= top and top + height <= sprites.HOOP_H, "the box leaves the grid"

    grid = sprites.build_hoop("hang")
    inside = {grid[r][c] for r in range(top, top + height)
              for c in range(left, left + width)}
    assert not inside & HOOP_BOARD_PAINT, \
        f"the opening is drawn on the backboard: {inside & HOOP_BOARD_PAINT}"
    assert "." in inside, "nothing in the declared opening is open"

    middle = top + height // 2
    span = grid[middle][left:left + width]
    assert set(span) == {"."}, f"row {middle} of the opening is not open: {span}"
    assert grid[middle][left - 1] in HOOP_RING, "nothing to the left of the hole"
    assert grid[middle][left + width] in HOOP_RING, "nothing to its right"

    centre = left + width // 2
    above = [grid[r][centre] for r in range(top)]
    below = [grid[r][centre] for r in range(top + height, sprites.HOOP_H)]
    assert set(above) & HOOP_RING, "no ring above the opening"
    assert set(below) & HOOP_RING, "no ring below it; this is not a hole"


def test_the_opening_is_wider_than_the_thing_thrown_through_it():
    """The one property a basket in a throwing game has to have, and the first
    drawing of this one did not.

    Its opening came to 44 screen pixels against a character 56 wide: narrower
    than the thing being thrown into it. Nothing failed. The 28-square sweep
    does not reach this canvas, the opening was still the hole and not the
    board, the clip still named frames that existed — and the basket read as
    one nobody could make while buddy_hoop was already scoring any throw that
    passed within half a sprite of the middle. Easy to hit and impossible to
    believe is the worst of the four combinations: it teaches the player not to
    aim, and then rewards them anyway.

    The margin is a fifth of the character on each side rather than a bare fit,
    because a hole exactly as wide as the sprite is a hole the sprite plugs.
    """
    opening = sprites.HOOP_RIM[2] * sprites.SCALE
    assert opening >= sprites.SIZE * 1.25, \
        (f"the opening is {opening}px across and the character thrown at it is "
         f"{sprites.SIZE}px wide")


def test_the_net_hangs_behind_the_ring():
    """The board is drawn once and the net goes on behind it.

    Pasted over, the cords cut notches out of the ring's outline everywhere the
    two overlap, and a ring with holes in its edge stops reading as a ring. The
    overlap is not hypothetical — the second assertion is there because a net
    that has stopped reaching the ring at all would pass the first.
    """
    board = sprites.HOOP_BOARD
    for name, grid in sprites.build_hoop_frames().items():
        for r, row in enumerate(board):
            for c, ch in enumerate(row):
                if ch != ".":
                    assert grid[r][c] == ch, \
                        f"{name}: the net painted over the board at ({c},{r})"

    overlaps = sum(1 for r, row in enumerate(sprites.HOOP_NETS["hang"])
                   for c, ch in enumerate(row)
                   if ch != "." and board[sprites.HOOP_NET_ROW + r][c] != ".")
    assert overlaps, "the net band no longer reaches the ring; the check is idle"


def test_the_score_frames_move_the_net_and_leave_the_board_alone():
    """Three frames of one drawing, not three drawings.

    Every row above the net band has to be identical in all of them — a board
    redrawn per frame is a second thing to keep in step with the first, and it
    shows up on screen as the basket flinching when the net does. And the
    frames have to actually differ below that row, or the clip is a still
    image played three times.
    """
    frames = sprites.build_hoop_frames()
    for name, grid in frames.items():
        assert grid[:sprites.HOOP_NET_ROW] == sprites.HOOP_BOARD[:sprites.HOOP_NET_ROW], \
            f"{name} redraws the board above the net"
    nets = {name: tuple(grid[sprites.HOOP_NET_ROW:]) for name, grid in frames.items()}
    assert len(set(nets.values())) == len(nets), \
        f"two hoop frames are the same drawing: {sorted(nets)}"


# The character's frames, as they were before the hoop existed: 108 per brand,
# and a digest over every row of every one of them. The hoop is a second canvas
# in the same module and the thing to prove about a second canvas is that the
# first one did not move — grid by grid, not by counting files.
#
# To change the character on purpose: run the two lines in the test body over
# the new grids and paste the digests. Being made to do that is the point.
CHARACTER_FRAMES = {
    "claude": (108, "35d5fefadcba858d89aeba375cf5a47907bba06d99a627d52c508daabef27e28"),
    "codex":  (108, "bd57db8ff40c236c2f553f68594342525da087be3ec42b186316a00cdda90233"),
}


@pytest.mark.parametrize("brand", BRANDS)
def test_the_character_frames_did_not_move_when_the_hoop_arrived(brand):
    """One pixel of one frame changes the digest, which is the whole idea."""
    import hashlib

    frames = sprites.build_frames(brand)
    count, digest = CHARACTER_FRAMES[brand]
    h = hashlib.sha256()
    for name in sorted(frames):
        h.update(name.encode() + b"\n")
        for row in frames[name]:
            h.update(row.encode() + b"\n")
    assert len(frames) == count, f"{brand}: {len(frames)} frames, not {count}"
    assert h.hexdigest() == digest, f"{brand}: the character's art changed"


# ── playback ───────────────────────────────────────────────────────────────

def test_a_one_shot_hands_control_back():
    """Landing must not leave the character stuck in a squash."""
    a = sprites.Animator("walk", rng=random.Random(1))
    a.play_once("land")
    total = sum(ms for _, ms in sprites.CLIPS["land"]["frames"]) / 1000.0
    for _ in range(int(total / 0.02) + 4):
        a.advance(0.02)
    assert a.clip == "walk", f"stuck in {a.clip}"


def test_a_clip_change_during_a_one_shot_is_not_lost():
    """It starts walking mid-landing: the landing finishes, then it walks."""
    a = sprites.Animator("idle", rng=random.Random(2))
    a.play_once("land")
    a.advance(0.02)
    a.set_clip("walk")
    assert a.clip == "land", "the landing was cut short"
    for _ in range(60):
        a.advance(0.02)
    assert a.clip == "walk", f"never reached the new clip: {a.clip}"


def test_a_looping_clip_loops():
    a = sprites.Animator("walk", rng=random.Random(3))
    seen = {a.advance(0.03) for _ in range(200)}
    assert seen == {f for f, _ in sprites.CLIPS["walk"]["frames"]}


def test_blinks_are_not_on_a_beat():
    """A blink every four seconds exactly is more mechanical than no blink."""
    a = sprites.Animator("idle", rng=random.Random(4))
    gaps, elapsed = [], 0.0
    for _ in range(4000):
        elapsed += 0.02
        if a.maybe_blink(0.02):
            gaps.append(round(elapsed, 2))
            elapsed = 0.0
        a.advance(0.02)
    assert len(gaps) > 5, f"barely blinked: {gaps}"
    assert len(set(gaps)) > len(gaps) // 2, f"blinks on a beat: {gaps}"


def test_it_does_not_blink_while_asleep():
    a = sprites.Animator("sleep", rng=random.Random(5))
    fired = [a.maybe_blink(0.02, allowed=False) for _ in range(2000)]
    assert not any(fired)


# ── the paint contract ─────────────────────────────────────────────────────

needs_qt = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None or not os.environ.get("DISPLAY"),
    reason="PySide6 or X display missing")


@needs_qt
@pytest.mark.parametrize("brand", BRANDS)
def test_a_source_pixel_is_a_solid_block_on_screen(brand):
    """The whole style lives on hard edges.

    Any smoothing — antialiasing, a non-integer scale, SmoothPixmapTransform —
    turns the boundary between two source pixels into a gradient. If every
    SCALE by SCALE block is one flat colour, none of that happened.
    """
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    scale = sprites.SCALE
    grid = sprites.build_frames(brand)["stand_open"]
    img = sprites.to_qimage(grid, sprites.PALETTES[brand], scale)
    for r in range(sprites.GRID):
        for c in range(sprites.GRID):
            block = {img.pixel(c * scale + dx, r * scale + dy)
                     for dy in range(scale) for dx in range(scale)}
            assert len(block) == 1, f"{brand} source pixel ({c},{r}) is not flat"


@needs_qt
@pytest.mark.parametrize("brand", BRANDS)
def test_the_sheet_hands_over_one_shadow_and_no_mirror_of_it(brand):
    """The shadow reaches the painter as its own image, so that it can be left
    out on the frames where the character is in the air and left unsheared
    while the body is being dragged. Neither is possible if it is drawn into
    the body grids, and both are the reason it exists separately.

    No `:flip`: an ellipse is its own mirror, and a second key is one more
    thing that can be asked for and drawn by mistake.
    """
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    sheet = sprites.build_sheet(brand)
    assert "shadow" in sheet, "the sheet carries no shadow"
    assert "shadow:flip" not in sheet, "a symmetric ellipse was given a mirror"

    img = sheet["shadow"]
    alphas = {(img.pixel(x, y) >> 24) & 0xFF
              for y in range(img.height()) for x in range(img.width())}
    assert any(0 < a < 255 for a in alphas), f"nothing translucent in it: {alphas}"
    assert 255 not in alphas, "part of the shadow is opaque"


@needs_qt
def test_the_hoop_reaches_qt_at_its_own_size_and_stays_out_of_the_body_sheet():
    """The hoop is 96 by 72 and the character is 28 by 28.

    to_qimage used to size its image from GRID, so anything on another canvas
    came out as a 28-square corner of itself: the right kind of image, cropped,
    nothing raised. That is the bug this pins, on the only grid in the file
    that can still hit it.

    The keys are the second half. The hoop is a separate sheet because
    build_sheet is per brand, paints with the brand palette — in which `t`,
    `k`, `n` and `u` do not exist and `b`, `s` and `h` mean body colours — and
    hands back images that everything downstream assumes are the character's
    size. And no `:flip`: a basket has no direction to face.
    """
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    sheet = sprites.build_hoop_sheet()
    assert set(sheet) == set(sprites.build_hoop_frames()), \
        "the sheet and the frames disagree about what a hoop frame is called"
    assert not [k for k in sheet if k.endswith(":flip")], \
        "a symmetric object with no facing was given a mirror"
    for name, img in sheet.items():
        assert img.width() == sprites.HOOP_W * sprites.SCALE, \
            f"{name} is {img.width()} wide, not {sprites.HOOP_W * sprites.SCALE}"
        assert img.height() == sprites.HOOP_H * sprites.SCALE, \
            f"{name} is {img.height()} tall, not {sprites.HOOP_H * sprites.SCALE}"

    character = sprites.build_sheet("claude")
    assert not set(sheet) & set(character), \
        "hoop frames are in the character's sheet, on the character's palette"


@needs_qt
def test_the_window_only_ever_sits_on_the_sprite_grid(monkeypatch):
    """A 2x sprite on an odd screen pixel has every source pixel straddling
    the screen grid by half. Nothing is blurred; it crawls."""
    sys.path.insert(0, str(REPO / "tests"))
    from test_companion import _companion
    _mod, _app, c = _companion(monkeypatch)
    for x in (100.0, 100.4, 101.0, 101.7, 102.9, 317.5):
        c.pos_x, c.pos_y = x, 400.3
        c._place()
        assert c.x() % sprites.SCALE == 0, f"{x} landed on {c.x()}"
        assert c.y() % sprites.SCALE == 0


@needs_qt
def test_facing_left_uses_a_baked_frame_rather_than_a_transform(monkeypatch):
    """Rotation and mirroring by painter transform were both in the previous
    version; the mirror is exact, the rotation was not. Both are gone, and the
    sheet carries the flipped frames so the paint path has no transform at
    all to get wrong."""
    sys.path.insert(0, str(REPO / "tests"))
    from test_companion import _companion
    _mod, _app, c = _companion(monkeypatch)
    assert c.sheet, "no frames built"
    for key in list(c.sheet):
        if key.endswith(":flip"):
            break
    else:
        pytest.fail("the sheet has no mirrored frames")
    left = c.sheet["stand_open:flip"]
    right = c.sheet["stand_open"]
    assert left.size() == right.size()
    assert left != right, "the mirror is a no-op"


# ── installation ───────────────────────────────────────────────────────────

def test_everything_the_companion_imports_is_installed_beside_it():
    """The companion imports from its own directory, which is ~/.local/bin on
    an installed system. A module left behind in the repository fails at
    import time, and the only symptom is a character that never appears."""
    import ast

    companion = REPO / "scripts" / "usage-buddy-companion.py"
    tree = ast.parse(companion.read_text())
    local = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if (REPO / "scripts" / f"{alias.name}.py").exists():
                    local.add(f"{alias.name}.py")
        elif isinstance(node, ast.ImportFrom) and node.module:
            if (REPO / "scripts" / f"{node.module}.py").exists():
                local.add(f"{node.module}.py")

    assert local, "no local imports found; this test has stopped watching anything"

    # Looking for the name anywhere in install.sh is not enough: the comment
    # explaining why the file is copied contains the name too, so deleting the
    # copy leaves the assertion happy. It has to be a copy instruction, on a
    # line that is not a comment.
    copies = [line for line in (REPO / "install.sh").read_text().splitlines()
              if "cp " in line and not line.lstrip().startswith("#")]
    for name in sorted(local):
        assert any(name in line for line in copies), \
            f"{name} is imported but install.sh never copies it"


def test_the_header_mascots_have_not_drifted_from_the_sprites():
    """The header and the companion draw the same creature.

    They used to be two separate drawings — a flat silhouette in the widget
    and a shaded character on the desktop — which is how they ended up looking
    like different animals. The committed SVGs are generated from the grids;
    this fails when a grid changes and render-mascots.py was not re-run.
    """
    spec = importlib.util.spec_from_file_location(
        "render_mascots", REPO / "scripts" / "render-mascots.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    for name, brand in mod.MASCOTS.items():
        committed = (REPO / "plasmoid" / "contents" / "icons" / name).read_text()
        assert committed == mod.to_svg(brand), \
            f"{name} is stale; run scripts/render-mascots.py"


# ── the state machine ──────────────────────────────────────────────────────

@needs_qt
@pytest.mark.parametrize("setup,expected", [
    (lambda c, now: setattr(c, "dragging", True), "held"),
    (lambda c, now: setattr(c, "alert_until", now + 5), "alert"),
    (lambda c, now: setattr(c, "bubble", "something"), "talk"),
    (lambda c, now: (setattr(c, "docked", True),
                     setattr(c, "settled_at", now - 3600)), "sleep"),
    (lambda c, now: None, "idle"),
])
def test_the_clip_follows_what_is_actually_happening(monkeypatch, setup, expected):
    """Each state has to reach the screen, or the animation is decoration."""
    import time
    sys.path.insert(0, str(REPO / "tests"))
    from test_companion import _companion
    _mod, _app, c = _companion(monkeypatch)
    now = time.monotonic()
    c.dragging = False
    c.docked = False
    c.bubble = ""
    c.alert_until = 0.0
    c.settled_at = now
    setup(c, now)
    c._animate(0.02, now, moving=False)
    assert c.anim.base == expected, f"got {c.anim.base}"


@needs_qt
def test_walking_shows_the_walk(monkeypatch):
    sys.path.insert(0, str(REPO / "tests"))
    from test_companion import _companion
    import time
    _mod, _app, c = _companion(monkeypatch)
    c.dragging = c.docked = False
    c.bubble = ""
    c.alert_until = 0.0
    c._animate(0.02, time.monotonic(), moving=True)
    assert c.anim.base == "walk"


@needs_qt
def test_being_held_beats_everything_else(monkeypatch):
    """Picked up mid-sentence it should hang from the cursor, not keep
    gesturing as though nothing happened."""
    import time
    sys.path.insert(0, str(REPO / "tests"))
    from test_companion import _companion
    _mod, _app, c = _companion(monkeypatch)
    now = time.monotonic()
    c.dragging = True
    c.bubble = "still talking"
    c.alert_until = now + 5
    c.docked = True
    c.settled_at = now - 3600
    c._animate(0.02, now, moving=True)
    assert c.anim.base == "held"


@needs_qt
def test_the_double_take_comes_before_the_sentence(monkeypatch):
    """A line and an alert arrive on the same poll, always: the alert is set
    from the same brain state that produced the line. So the two are never
    apart, and testing them apart tests nothing — the ordering between them is
    the whole behaviour. Seen first, read second."""
    import time
    sys.path.insert(0, str(REPO / "tests"))
    from test_companion import _companion
    _mod, _app, c = _companion(monkeypatch)
    now = time.monotonic()
    c.dragging = c.docked = False
    c.bubble = "ti finished"
    c.alert_until = now + 1.0
    c._animate(0.02, now, moving=False)
    assert c.anim.base == "alert", f"the jump was swallowed by the bubble: {c.anim.base}"

    # and once the jump is spent, it settles into talking
    c._animate(0.02, now + 2.0, moving=False)
    assert c.anim.base == "talk"


@needs_qt
def test_a_session_needing_a_human_triggers_the_jump(monkeypatch):
    """Closes the loop from data to animation. Everything above tests the
    animator given a state; this tests that a real session reaches it."""
    import time
    sys.path.insert(0, str(REPO / "tests"))
    from test_companion import _companion
    mod, _app, c = _companion(monkeypatch)

    session = {"name": "widget", "pid": 1, "state": "asking", "idleSeconds": 5}
    c.brain.refresh = lambda: None
    c.brain.sessions = {"sessions": [session], "attention": session}
    c.alert_until = 0.0
    c.said = ""
    mod.Companion._poll(c)
    assert c.bubble, "said nothing about a session that is asking"
    assert c.alert_until > time.monotonic(), "no double-take for a session that is asking"

    # An ambient remark with nothing needing a human must not jump: a jump that
    # fires for everything stops meaning anything.
    c.brain.sessions = {"sessions": [], "attention": None}
    c.alert_until = 0.0
    c.said = ""
    mod.Companion._poll(c)
    assert c.alert_until == 0.0, "jumped for an ambient line"
