"""Raising the window is only half the job when the sessions are tabs.

Measured on the machine this was written for: five live Claude sessions, three
of them tabs of a single konsole process. Their ancestor chains converge on one
pid, so no amount of window matching can tell them apart — the focus helper
could raise the right window and leave the wrong tab showing.

Konsole publishes org.kde.konsole-<pid>, and every tab answers
foregroundProcessId(), which is the Claude pid itself. That is an exact map.
The tests drive the helper against a stub qdbus-qt6 rather than a live desktop.
"""
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "focus-session.sh"

STUB = r"""#!/bin/bash
# A konsole with three tabs. Tab 2 is running the wanted pid; the current tab
# starts at 1, so reaching it takes real cycling.
state="$STUB_STATE"
[ -f "$state" ] || echo 1 > "$state"
case "$*" in
    "org.kde.konsole-4242")
        echo " /Sessions/1"; echo " /Sessions/2"; echo " /Sessions/3"
        echo " /Windows/1" ;;
    "org.kde.konsole-4242 /Windows/1 org.kde.konsole.Window.sessionCount") echo 3 ;;
    "org.kde.konsole-4242 /Windows/1 org.kde.konsole.Window.currentSession") cat "$state" ;;
    "org.kde.konsole-4242 /Windows/1 org.kde.konsole.Window.nextSession")
        cur=$(cat "$state"); echo $(( cur % 3 + 1 )) > "$state" ;;
    "org.kde.konsole-4242 /Sessions/1 org.kde.konsole.Session.foregroundProcessId") echo 111 ;;
    "org.kde.konsole-4242 /Sessions/2 org.kde.konsole.Session.foregroundProcessId") echo 777 ;;
    "org.kde.konsole-4242 /Sessions/3 org.kde.konsole.Session.foregroundProcessId") echo 333 ;;
    *) exit 1 ;;
esac
"""


def _run(tmp_path, target):
    """Call select_konsole_tab against the stub, and report the tab it left on."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "qdbus-qt6"
    stub.write_text(STUB)
    stub.chmod(0o755)
    state = tmp_path / "state"

    body = SCRIPT.read_text()
    start = body.index("select_konsole_tab()")
    end = body.index("\n}\n", start) + 3
    program = body[start:end] + (
        f'\nselect_konsole_tab {target} org.kde.konsole-4242\n'
        'echo "rc=$?"\n'
        'echo "tab=$(cat "$STUB_STATE")"\n')

    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", STUB_STATE=str(state))
    done = subprocess.run(["bash", "-c", program], capture_output=True, text=True,
                          env=env, timeout=20)
    return done.stdout


def test_it_lands_on_the_tab_running_that_session(tmp_path):
    out = _run(tmp_path, 777)
    assert "rc=0" in out, out
    assert "tab=2" in out, f"stopped on the wrong tab: {out}"


def test_an_unknown_pid_leaves_the_tabs_alone(tmp_path):
    """A session in a different terminal must not make konsole cycle through
    every tab it has."""
    out = _run(tmp_path, 999)
    assert "rc=1" in out, out
    assert "tab=1" in out, f"cycled the tabs for a pid it does not own: {out}"


def test_the_tab_is_chosen_before_the_window_is_raised():
    """Raising first and switching after makes the wrong tab visible for as
    long as the round trip takes."""
    body = SCRIPT.read_text()
    assert body.index("select_konsole_tab \"$PID\"") < body.index("loadScript"), \
        "the window is raised before the tab is selected"


def test_the_ancestor_walk_stops_before_init(tmp_path):
    """Every session on a machine shares pid 1, and most share the user's
    systemd. An ancestor list that reaches them matches windows belonging to
    other sessions."""
    body = SCRIPT.read_text()
    assert '"$cur" != "1"' in body, "the walk does not stop at init"
