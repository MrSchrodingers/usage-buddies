"""Being dragged around, and the one place this is allowed to touch the mouse.

A short drag is how you put the character somewhere. A long one is someone
playing with it, and it may notice. Repeated ones earn a brief tug back —
bounded, gradual, and on a long cooldown, because taking the pointer away from
someone working is the difference between a joke and a hijacked desktop.
"""
import importlib.util
import os
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
COMPANION = REPO / "scripts" / "usage-buddy-companion.py"

needs_qt = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None or not os.environ.get("DISPLAY"),
    reason="PySide6 or X display missing")


def _companion():
    os.environ["QT_QPA_PLATFORM"] = "xcb"
    spec = importlib.util.spec_from_file_location("drag_companion", COMPANION)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["drag_companion"] = mod
    spec.loader.exec_module(mod)
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    c = mod.Companion()
    c.poll_timer.stop()
    c.frame_timer.stop()
    c._poll = lambda: None
    return mod, c


@needs_qt
def test_a_short_drag_draws_no_comment(monkeypatch):
    """Putting it in a corner is an instruction, not provocation."""
    mod, c = _companion()
    said = []
    # monkeypatch, not a bare assignment: patching the class outright leaked
    # into every other module's companion and broke a test three files away.
    monkeypatch.setattr(type(c), "_say", lambda self, text: said.append(text))
    now = time.monotonic()
    c.dragging = True
    c.drag_started = now
    c._animate(0.02, now + 1.0, moving=False)
    assert c.anim.base == "held"
    assert not said, f"complained after one second: {said}"


@needs_qt
def test_a_long_drag_complains_once(monkeypatch):
    mod, c = _companion()
    said = []
    monkeypatch.setattr(type(c), "_say", lambda self, text: said.append(text))
    now = time.monotonic()
    c.dragging = True
    c.drag_started = now
    late = now + mod.DRAG_PATIENCE + 1
    c._animate(0.02, late, moving=False)
    assert c.anim.base == "annoyed", f"still {c.anim.base}"
    assert len(said) == 1, said
    c._animate(0.02, late + 5, moving=False)
    assert len(said) == 1, f"said it again: {said}"


@needs_qt
def test_one_drag_never_earns_a_tug(monkeypatch):
    mod, c = _companion()
    monkeypatch.setattr(type(c), "_say", lambda self, text: None)
    c.tug_until = 0.0
    c.tugged_at = 0.0
    c.recent_drags = []
    for _ in range(mod.DRAG_TUG_AFTER - 1):
        c.dragging = True
        c._release_for_test() if hasattr(c, "_release_for_test") else None
        c.dragging = False
        c.recent_drags.append(time.monotonic())
    assert len(c.recent_drags) < mod.DRAG_TUG_AFTER
    assert c.tug_until == 0.0, "tugged before it had been dragged enough"


def test_the_tug_has_a_hard_ceiling_and_a_long_cooldown():
    """Read from the constants. Taking the pointer away from someone working
    is only acceptable because all four of these hold at once: it ends, it
    cannot repeat soon, it never jumps the pointer in one frame, and it can
    be broken by pulling away."""
    source = COMPANION.read_text()
    scope = {}
    for line in source.splitlines():
        if line.startswith(("TUG_", "DRAG_")):
            exec(line.split("#")[0], {}, scope)
    assert scope["TUG_SECONDS"] <= 10, "holds on for too long"
    assert scope["TUG_COOLDOWN"] >= 300, "can repeat too soon"
    assert 0 < scope["TUG_STEP"] <= 20, "sends the pointer in jumps big enough to fling it"


# ── the swing ──────────────────────────────────────────────────────────────

@needs_qt
def test_the_body_lags_behind_the_hand():
    """A window moved to the pointer every frame has no weight — it is the
    pointer wearing a costume. The body accelerates toward the hand, so during
    a fast pull it is always somewhere behind it."""
    mod, c = _companion()
    c.pos_x, c.pos_y = 500.0, 500.0
    c.vel_x = c.vel_y = 0.0
    c.dragging = True
    c.hand = (900.0, 500.0)

    gaps = []
    for _ in range(6):
        c._swing(0.033)
        gaps.append(c.hand[0] - c.pos_x)

    assert gaps[0] > 0, "arrived instantly"
    assert all(g > 0 for g in gaps), f"never trailed: {gaps}"
    assert gaps[-1] < gaps[0], f"never caught up at all: {gaps}"


@needs_qt
def test_it_overshoots_and_settles():
    """The overshoot is the point: a spring that only ever approaches reads as
    easing, not as weight on a string."""
    mod, c = _companion()
    c.pos_x, c.pos_y = 500.0, 500.0
    c.vel_x = c.vel_y = 0.0
    c.dragging = True
    c.hand = (700.0, 500.0)

    passed_it = False
    for _ in range(120):
        c._swing(0.033)
        if c.pos_x > c.hand[0] + 1:
            passed_it = True
    assert passed_it, "approached without ever passing the hand"
    assert abs(c.pos_x - c.hand[0]) < 6, f"never settled: {c.pos_x}"


@needs_qt
def test_the_lean_trails_the_direction_of_travel():
    """Pulled right, the bottom of the body is still back on the left."""
    mod, c = _companion()
    c.vel_x = 0.0
    c.wobble = 0.0

    import buddy_sprites as sprites
    c.wobble = 0.0
    c.vel_x = mod.SWING_MAX_LEAN
    right = c.swing_frame()
    c.vel_x = -mod.SWING_MAX_LEAN
    left = c.swing_frame()
    assert right != left
    assert right == sprites.wobble_frame(-3, 0), f"moving right leaned right: {right}"
    assert left == sprites.wobble_frame(3, 0), f"moving left leaned left: {left}"


@needs_qt
def test_every_lean_is_a_frame_that_exists():
    mod, c = _companion()
    for velocity in (-900, -200, -40, 0, 40, 200, 900):
        c.vel_x = velocity
        frame = c.swing_frame()
        if frame is not None:
            assert frame in c.sheet, f"{frame} is not in the sheet"


@needs_qt
def test_one_long_pull_earns_the_tug_on_its_own(monkeypatch):
    """Holding it and dragging for ten seconds is the same message as
    picking it up three times."""
    mod, c = _companion()
    monkeypatch.setattr(type(c), "_say", lambda self, text: None)
    monkeypatch.setattr(type(c), "_snap", lambda self: None)
    c.recent_drags = []
    c.tugged_at = 0.0
    c.tug_until = 0.0
    c.dragging = True
    c.drag_started = time.monotonic() - (mod.DRAG_TUG_SECONDS + 1)

    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    release = QMouseEvent(QMouseEvent.MouseButtonRelease, QPointF(0, 0),
                          Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    c.mouseReleaseEvent(release)
    assert c.tug_until > time.monotonic(), "a ten-second drag earned nothing"


@needs_qt
def test_the_spring_is_reached_through_the_frame_tick():
    """Calling _swing directly proves the maths and nothing else. If the tick
    stops routing through it, the drag goes back to welding the sprite to the
    pointer and every test above still passes."""
    mod, c = _companion()
    c.pos_x, c.pos_y = 500.0, 500.0
    c.vel_x = c.vel_y = 0.0
    c.dragging = True
    c.hand = (900.0, 500.0)
    c.bubble = ""
    c._tick()
    assert c.pos_x != 500.0, "the tick did not move it at all"
    assert c.pos_x < 900.0, "the tick teleported it onto the hand"


@needs_qt
def test_what_is_painted_changes_with_the_swing():
    """The lean has to reach the screen. Picking a frame nobody draws is the
    same as not having one."""
    mod, c = _companion()
    import buddy_sprites as sprites
    c.dragging = True
    c.frame = "dangle_wide"
    c.facing = 1
    c.resize(sprites.SIZE, sprites.SIZE)

    c.vel_x = 0.0
    still = c.grab().toImage()
    c.vel_x = -mod.SWING_MAX_LEAN
    leaning = c.grab().toImage()

    assert still != leaning, "the sprite looks identical whether it is swinging or not"


# ── the wobble, which is the part that is in the sprite ────────────────────

@needs_qt
def test_the_body_keeps_moving_after_the_hand_stops():
    """This is the difference between inertia in the window and inertia in the
    drawing. The window can trail the cursor perfectly and the sprite still be
    a rigid picture being slid around; what makes it read as soft is the shape
    still changing once nothing is pulling on it."""
    mod, c = _companion()
    c.dragging = True
    c.pos_x, c.pos_y = 500.0, 500.0
    c.vel_x = c.vel_y = 0.0
    c.wobble = c.wobble_v = 0.0

    c.hand = (500.0, 200.0)                 # yanked upward
    for _ in range(8):
        c._swing(0.033)
    assert abs(c.wobble) > 0.05, f"a hard pull did not deform it: {c.wobble}"

    c.hand = (c.pos_x, c.pos_y)             # hand stops dead
    shapes = []
    for _ in range(30):
        c._swing(0.033)
        shapes.append(round(c.wobble, 3))
    assert len(set(shapes)) > 5, f"the shape froze the moment the hand did: {shapes}"


@needs_qt
def test_the_wobble_settles_instead_of_ringing_forever():
    """A spring with no damping is a sprite having a seizure."""
    mod, c = _companion()
    c.dragging = True
    c.pos_x = c.pos_y = 500.0
    c.vel_x = c.vel_y = 0.0
    c.wobble, c.wobble_v = 1.0, 0.0
    c.hand = (500.0, 500.0)
    for _ in range(200):
        c._swing(0.033)
    assert abs(c.wobble) < 0.08, f"still ringing after six seconds: {c.wobble}"


@needs_qt
def test_stretch_and_squash_are_different_drawings():
    """The frames have to actually differ, or the oscillator is driving
    nothing."""
    mod, c = _companion()
    import buddy_sprites as sprites
    c.vel_x = 0.0
    seen = set()
    for w in (-1.0, 0.0, 1.0):
        c.wobble = w
        seen.add(c.swing_frame())
    assert len(seen) == 3, f"squash, rest and stretch are not distinct: {seen}"
    for name in seen:
        assert name in c.sheet, f"{name} is not a frame that exists"


def test_squashing_keeps_the_feet_on_the_ground():
    """A body that shrinks off the floor reads as getting smaller, not as
    being compressed."""
    import sys as _sys
    _sys.path.insert(0, str(REPO / "scripts"))
    import buddy_sprites as sprites
    frames = sprites.build_frames("claude")
    grounds = set()
    for wob in (-2, -1, 0, 1, 2):
        grid = frames[sprites.wobble_frame(0, wob)]
        grounds.add(max(i for i, row in enumerate(grid) if set(row) != {"."}))
    assert len(grounds) == 1, f"the ground row moves with the squash: {grounds}"


def test_stretching_changes_the_height():
    import sys as _sys
    _sys.path.insert(0, str(REPO / "scripts"))
    import buddy_sprites as sprites
    frames = sprites.build_frames("claude")

    def height(wob):
        grid = frames[sprites.wobble_frame(0, wob)]
        rows = [i for i, row in enumerate(grid) if set(row) != {"."}]
        return rows[-1] - rows[0]

    assert height(-2) < height(0) < height(2), \
        f"heights do not order: {height(-2)}, {height(0)}, {height(2)}"


@needs_qt
def test_the_shape_has_its_own_spring_not_a_readout_of_speed():
    """Distinguishing a spring from a formula.

    "The shape changes while being dragged" is not enough: setting the
    deformation equal to the current speed also changes it, and passes every
    other test here, because the body is overshooting the hand and the speed
    is oscillating anyway. What only a spring does is carry a displacement
    through zero on its own — released from a stretch with nothing moving, it
    has to squash before it comes to rest.
    """
    mod, c = _companion()
    c.dragging = True
    c.pos_x = c.pos_y = 500.0
    c.hand = (500.0, 500.0)          # hand exactly on the body: nothing pulling
    c.vel_x = c.vel_y = 0.0
    c.wobble, c.wobble_v = 1.0, 0.0  # let go of it stretched

    crossings, previous = 0, c.wobble
    for _ in range(90):
        c._swing(0.033)
        assert abs(c.vel_y) < 1.0, "the position spring moved; the case is not clean"
        if previous > 0 >= c.wobble or previous < 0 <= c.wobble:
            crossings += 1
        previous = c.wobble
    assert crossings >= 2, (
        f"the shape never passed through its resting state ({crossings} crossings) — "
        "it is following the speed, not springing back")


@needs_qt
def test_it_runs_somewhere_worth_watching():
    """A kidnapping that ends four pixels away is a shrug."""
    mod, c = _companion(); import random
    said = []
    type(c)._say_backup = type(c)._say
    try:
        type(c)._say = lambda self, text: said.append(text)
        type(c)._snap_backup = type(c)._snap
        type(c)._snap = lambda self: None
        c.pos_x, c.pos_y = float(c.min_x + 20), float(c.max_y - 20)
        c.recent_drags = []
        c.tugged_at = 0.0
        c.tug_until = 0.0
        c.dragging = True
        c.drag_started = time.monotonic() - (mod.DRAG_TUG_SECONDS + 1)

        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        c.mouseReleaseEvent(QMouseEvent(QMouseEvent.MouseButtonRelease, QPointF(0, 0),
                                        Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
        assert c.tug_until > time.monotonic()
        travel = abs(c.target[0] - c.pos_x) + abs(c.target[1] - c.pos_y)
        span = (c.max_x - c.min_x) + (c.max_y - c.min_y)
        assert travel > span * 0.2, f"ran {travel:.0f}px across a {span:.0f}px desktop"
    finally:
        type(c)._say = type(c)._say_backup
        type(c)._snap = type(c)._snap_backup


# ── carrying the pointer ───────────────────────────────────────────────────
#
# QCursor.setPos does not move the pointer here and looks like it does: it
# warps XWayland's shadow, the compositor corrects the real one back, and on
# screen the cursor flickers and stays where it was. Verified against KWin's
# own workspace.cursorPos, which a uinput device does move — 853,559 to
# 1450,891 — and which QCursor.pos() reported as unchanged throughout.
#
# So the pointer is moved by *relative* deltas from a virtual input device,
# and never read: there is no reliable way to ask where it is.

class _FakePointer:
    def __init__(self):
        self.moved = []
        self.alive = True

    def move(self, dx, dy):
        self.moved.append((dx, dy))
        return self.alive


@needs_qt
def test_it_carries_the_pointer_by_its_own_movement():
    """Moved by the distance the character moved, not toward where it is
    standing. There is no absolute position to aim at."""
    mod, c = _companion()
    fake = _FakePointer()
    c.pointer = fake
    c.dragging = False
    c.tug_until = time.monotonic() + 5
    c.tug_from = None

    c.pos_x, c.pos_y = 400.0, 400.0
    c._tug(time.monotonic())            # first frame only records where it was
    assert not fake.moved, "moved the pointer before it had a delta"

    c.pos_x, c.pos_y = 460.0, 430.0
    c._tug(time.monotonic())
    assert fake.moved, "did not carry the pointer at all"
    total_x = sum(dx for dx, _ in fake.moved)
    total_y = sum(dy for _, dy in fake.moved)
    assert abs(total_x - 60) < 1.5, f"carried {total_x} horizontally, moved 60"
    assert abs(total_y - 30) < 1.5, f"carried {total_y} vertically, moved 30"


@needs_qt
def test_the_pointer_is_carried_in_small_steps():
    """libinput accelerates. One big delta travels much further than the same
    distance sent gradually, and the pointer ends up somewhere else."""
    mod, c = _companion()
    fake = _FakePointer()
    c.pointer = fake
    c.dragging = False
    c.tug_until = time.monotonic() + 5
    c.pos_x = c.pos_y = 400.0
    c.tug_from = (400.0, 400.0)
    c.pos_x = 700.0
    c._tug(time.monotonic())
    assert len(fake.moved) > 1, "sent a 300px jump in one event"
    assert all(abs(dx) <= mod.TUG_STEP + 1 for dx, _ in fake.moved), \
        f"steps too large: {fake.moved[:4]}"


@needs_qt
def test_it_does_not_touch_the_pointer_outside_the_grab():
    mod, c = _companion()
    fake = _FakePointer()
    c.pointer = fake

    c.tug_until = 0.0
    c.dragging = False
    c.pos_x = 400.0
    c._tug(time.monotonic())
    assert not fake.moved, "moved the pointer with no grab running"

    c.tug_until = time.monotonic() + 5
    c.dragging = True                    # being held: it is not carrying anything
    c.tug_from = (100.0, 100.0)
    c._tug(time.monotonic())
    assert not fake.moved, "carried the pointer while it was being dragged"


@needs_qt
def test_a_dead_device_stops_it_rather_than_raising():
    """The device can vanish — the user's session can revoke it. A desktop toy
    must not throw in a paint tick."""
    mod, c = _companion()
    fake = _FakePointer()
    fake.alive = False
    c.pointer = fake
    c.dragging = False
    c.tug_until = time.monotonic() + 5
    c.tug_from = (400.0, 400.0)
    c.pos_x = 500.0
    c._tug(time.monotonic())
    assert c.pointer is False, "kept a device that reported itself gone"


def test_the_virtual_pointer_degrades_to_nothing():
    """Where /dev/uinput is not writable this has to return None, not raise:
    the whole feature is a joke and must never be the reason the companion
    does not start."""
    import sys as _sys
    _sys.path.insert(0, str(REPO / "scripts"))
    import virtual_pointer
    original = virtual_pointer.UINPUT
    try:
        virtual_pointer.UINPUT = "/definitely/not/here"
        assert virtual_pointer.VirtualPointer().open() is None
        assert virtual_pointer.available() is False
    finally:
        virtual_pointer.UINPUT = original


def test_the_pointer_device_turns_its_own_acceleration_off():
    """libinput accelerates by default, and the cursor arrives ahead of the
    character — measured, 900 pixels of movement carried the pointer 1220.
    With the device's profile set flat it is 800 for 800.

    Also pins the D-Bus call shape: reading a property as
    `org.kde.KWin.InputDevice.name` answers UnknownInterface, which reads as
    the interface being absent rather than the call being wrong.
    """
    import sys as _sys
    _sys.path.insert(0, str(REPO / "scripts"))
    import virtual_pointer
    source = (REPO / "scripts" / "virtual_pointer.py").read_text()
    assert "pointerAccelerationProfileFlat" in source
    assert "org.freedesktop.DBus.Properties.Get" in source, \
        "reads properties by dotted name, which does not work"
    assert "org.freedesktop.DBus.Properties.Set" in source


def test_movement_keeps_its_fractional_remainder():
    """The protocol carries whole pixels. Dropping the fraction on every call
    loses a few percent of every movement, which across a run is the pointer
    ending up somewhere the character is not."""
    import sys as _sys
    _sys.path.insert(0, str(REPO / "scripts"))
    import virtual_pointer

    sent = []
    device = virtual_pointer.VirtualPointer()
    device.fd = -1
    device._flatten = lambda: None
    original = virtual_pointer.os.write
    try:
        virtual_pointer.os.write = lambda fd, payload: sent.append(payload) or len(payload)
        for _ in range(10):
            device.move(0.6, 0.0)
    finally:
        virtual_pointer.os.write = original
        device.fd = None

    total = 0
    for payload in sent:
        for i in range(0, len(payload), virtual_pointer._EVENT.size):
            _, _, kind, code, value = virtual_pointer._EVENT.unpack(
                payload[i:i + virtual_pointer._EVENT.size])
            if kind == virtual_pointer.EV_REL and code == virtual_pointer.REL_X:
                total += value
    assert total == 6, f"ten moves of 0.6px carried {total}px, not 6"
