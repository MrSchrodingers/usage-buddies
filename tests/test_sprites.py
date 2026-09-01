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
@pytest.mark.parametrize("name", [n for n in dir(sprites)
                                  if n.isupper() and not n.startswith("CAR_")
                                  and not n.startswith("SHADOW")
                                  and isinstance(getattr(sprites, n), list)
                                  and getattr(sprites, n)
                                  and isinstance(getattr(sprites, n)[0], str)])
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
