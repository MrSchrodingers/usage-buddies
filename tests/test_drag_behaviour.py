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
def test_the_tug_is_bounded_and_gradual():
    """It closes a fraction of the gap per frame, so real movement beats it."""
    mod, c = _companion()
    from PySide6.QtGui import QCursor
    from PySide6.QtCore import QPoint

    c.move(400, 400)
    QCursor.setPos(900, 900)
    before = QCursor.pos()
    c.tug_until = time.monotonic() + 5
    c.dragging = False
    c._tug(time.monotonic())
    after = QCursor.pos()

    moved = abs(after.x() - before.x()) + abs(after.y() - before.y())
    gap = abs(before.x() - 400) + abs(before.y() - 400)
    assert 0 < moved, "the tug did nothing"
    assert moved < gap * 0.5, f"moved {moved} of {gap} in one frame — that is a jump"
    QCursor.setPos(QPoint(before.x(), before.y()))


@needs_qt
def test_no_tug_outside_its_window():
    mod, c = _companion()
    from PySide6.QtGui import QCursor
    QCursor.setPos(900, 900)
    before = QCursor.pos()
    c.tug_until = 0.0
    c._tug(time.monotonic())
    assert QCursor.pos() == before, "moved the pointer with no tug running"


@needs_qt
def test_no_tug_while_being_dragged():
    """Fighting the hand that is holding it would just feel broken."""
    mod, c = _companion()
    from PySide6.QtGui import QCursor
    QCursor.setPos(900, 900)
    before = QCursor.pos()
    c.tug_until = time.monotonic() + 5
    c.dragging = True
    c._tug(time.monotonic())
    assert QCursor.pos() == before


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
    """Read from the constants: a tug that could run indefinitely, or repeat
    immediately, is not a joke any more."""
    source = COMPANION.read_text()
    scope = {}
    for line in source.splitlines():
        if line.startswith(("TUG_", "DRAG_")):
            exec(line.split("#")[0], {}, scope)
    assert scope["TUG_SECONDS"] <= 10, "pulls for too long"
    assert scope["TUG_COOLDOWN"] >= 300, "can repeat too soon"
    assert 0 < scope["TUG_STRENGTH"] <= 0.15, "not a tug, a teleport"
