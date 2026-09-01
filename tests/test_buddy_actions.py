"""The four ways this engine hurts someone if it is wrong.

It throws the character off the screen — a whip estimated from two events a
millisecond apart extrapolates to thousands of pixels a second, and one frame
later there is no companion. It never stops — a bounce with restitution and no
floor rule keeps the body vibrating on the bottom edge for ever, and the
companion never walks again. It runs a subprocess somewhere nobody asked for —
what comes out of a drop becomes a working directory and the body of a prompt,
so `http://`, `..`, a plain file and a selection of four hundred folders all
have to be refused, out loud. And it takes the mouse away and drops it on
another monitor, where the compositor clamps the intermediate positions and
the pointer is simply lost.

Nothing here sleeps: dt and the sample timestamps are arguments.
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import buddy_actions as actions


# The desktop this was written on, measured twice over: kscreen-doctor and
# KWin's own getWindowInfo agree with Qt on the xcb platform that HDMI-A-1 is
# (0, 0, 2194, 1234) and eDP-1 is (2195, 0, 1920, 1200). The two are different
# heights, which is the whole reason delivery refuses to cross between them.
SCREENS = [(0, 0, 2194, 1234), (2195, 0, 1920, 1200)]
SPRITE = 56                     # buddy_sprites.GRID 28 at SCALE 2
# What Companion computes from the union of those screens: the range of legal
# top-left corners, inset by 8 px and by one sprite.
BOUNDS = (8, 8, 4115 - SPRITE - 8, 1234 - SPRITE - 8)


def _drag(points, start=1000.0):
    """(t, x, y) samples from (dt, x, y) steps, oldest first."""
    now, rows = start, []
    for step, x, y in points:
        now += step
        rows.append((now, float(x), float(y)))
    return rows


# ── the throw ──

def test_a_release_with_nothing_to_go_on_is_a_zero_and_not_a_crash():
    """Letting go without having moved is an ordinary thing to do. Raising on
    it takes the companion down inside a mouse event handler; answering None
    makes every caller invent a fallback for a case that is not ambiguous."""
    assert actions.throw_velocity([]) == (0.0, 0.0)
    assert actions.throw_velocity(None) == (0.0, 0.0)
    assert actions.throw_velocity([(1000.0, 10.0, 10.0)]) == (0.0, 0.0)
    # Two readings at the same instant: no time base, so no division.
    assert actions.throw_velocity([(1000.0, 0.0, 0.0),
                                   (1000.0, 40.0, 0.0)]) == (0.0, 0.0)
    # Junk in the buffer is skipped rather than thrown.
    assert actions.throw_velocity([("x", None, None), (1000.0, 0.0, 0.0)]) == (0.0, 0.0)


def test_the_flick_at_the_end_beats_the_average_of_the_whole_drag():
    """Someone who drags slowly across the desk and whips at the last moment
    is throwing. Fit the whole drag and the slow part cancels the fast one, so
    the character leaves the hand at walking pace and the gesture is lost."""
    slow = [(1 / 60.0, 100 + i * 1.0, 500.0) for i in range(120)]   # 60 px/s
    whip = [(1 / 60.0, 220 + i * 30.0, 500.0) for i in range(6)]    # 1800 px/s
    vx, vy = actions.throw_velocity(_drag(slow + whip))
    assert 1500 < vx < 2000, f"the whip was averaged away: {vx}"
    assert abs(vy) < 1.0
    # The whole-drag average is what this must not be.
    rows = _drag(slow + whip)
    average = (rows[-1][1] - rows[0][1]) / (rows[-1][0] - rows[0][0])
    assert vx > average * 4, f"{vx} is the average {average}, not the flick"


def test_an_impossible_flick_is_capped_instead_of_believed():
    """Three pixels in one millisecond reads as 3000 px/s, which at the active
    frame rate is 99 px a frame — the character is off the far edge of the
    desktop before anyone sees it leave."""
    vx, vy = actions.throw_velocity([(1000.000, 0.0, 0.0),
                                     (1000.001, 3.0, 4.0)])
    speed = (vx * vx + vy * vy) ** 0.5
    assert speed <= actions.THROW_MAX_SPEED + 1e-9, f"{speed} px/s left the cap"
    # Capped by scaling, so a diagonal throw stays diagonal: 3 and 4 across,
    # so the same 3:4 out.
    assert abs(vx / vy - 0.75) < 1e-9, f"the cap bent the direction: {vx}, {vy}"


def test_a_release_slower_than_the_character_walks_is_a_placement():
    """A hand moving at 40 px/s was putting the thing down. Launching from
    there looks like the sprite slipping out of your fingers, and it fights
    the drop-to-dock the companion already does."""
    creep = [(1 / 60.0, 100 + i * 0.7, 400.0) for i in range(30)]   # 42 px/s
    assert actions.throw_velocity(_drag(creep)) == (0.0, 0.0)


def test_the_body_settles_in_finite_time_instead_of_bouncing_for_ever():
    """Restitution under 1 shrinks a bounce and never ends it. Without a floor
    rule the character hums against the bottom edge for the rest of the
    session, the frame timer never goes back to idle, and it never walks."""
    x, y, vx, vy = 2000.0, 8.0, 900.0, 0.0
    for step in range(600):                       # 20 s at 30 fps
        state = actions.integrate((x, y), (vx, vy), 1 / 30.0, BOUNDS)
        x, y, vx, vy = state.x, state.y, state.vx, state.vy
        if state.resting:
            break
    else:
        raise AssertionError("still moving after twenty seconds")
    assert step < 300, f"took {step / 30.0:.1f}s to settle"
    assert (vx, vy) == (0.0, 0.0)
    assert y == BOUNDS[3], "settled somewhere other than the floor"
    # And it stays settled: another second of steps moves it nowhere.
    landed = (x, y)
    for _ in range(30):
        state = actions.integrate((x, y), (vx, vy), 1 / 30.0, BOUNDS)
        x, y, vx, vy = state.x, state.y, state.vx, state.vy
    assert (x, y) == landed, "a body at rest crept"


def test_a_throw_at_a_wall_bounces_off_it_rather_than_through_it():
    """The companion clamps its own position, so a body that should have
    bounced instead slides along the edge with its velocity still pointing
    outward — it looks stuck, and it never comes back."""
    x, y, vx, vy = float(BOUNDS[2]) - 200.0, 400.0, 1800.0, -100.0
    bounced = False
    for _ in range(200):
        state = actions.integrate((x, y), (vx, vy), 1 / 60.0, BOUNDS)
        assert BOUNDS[0] <= state.x <= BOUNDS[2], f"left the screen at {state.x}"
        assert BOUNDS[1] <= state.y <= BOUNDS[3], f"left the screen at {state.y}"
        if state.bounced and vx > 0:
            assert state.vx < 0, "hit the right wall and kept going right"
            bounced = True
        x, y, vx, vy = state.x, state.y, state.vx, state.vy
    assert bounced, "never hit the wall it was thrown at"


def test_a_stalled_frame_does_not_teleport_the_body_through_a_wall():
    """The idle frame timer is 200 ms and a wedged process hands in worse. At
    the speed ceiling a two-second step is 4800 px of travel resolved in one
    go, which passes clean through the screen and comes out clamped in a
    corner with the throw's whole energy still in it."""
    state = actions.integrate((2000.0, 600.0), (2400.0, 0.0), 2.0, BOUNDS)
    assert state.x <= 2000.0 + actions.THROW_MAX_SPEED * actions.MAX_STEP + 1
    assert BOUNDS[0] <= state.x <= BOUNDS[2]
    assert BOUNDS[1] <= state.y <= BOUNDS[3]


def test_the_same_throw_twice_lands_in_the_same_place():
    """A trajectory with any randomness in it cannot be asserted, only
    described, and the first regression that matters is the one a description
    is too loose to catch."""
    def flight():
        x, y, vx, vy = 100.0, 300.0, 1400.0, -300.0
        for _ in range(120):
            state = actions.integrate((x, y), (vx, vy), 1 / 60.0, BOUNDS)
            x, y, vx, vy = state.x, state.y, state.vx, state.vy
        return round(x, 6), round(y, 6)
    assert flight() == flight()


# ── the drop ──

def _repo(root, name=".git"):
    """A directory that passes for a repository."""
    root.mkdir(parents=True, exist_ok=True)
    (root / name).mkdir()
    return root


def test_a_url_that_is_not_a_local_file_is_refused_and_says_why():
    """What comes out of here becomes a working directory. A scheme that is
    not file:// is either a network fetch or a path this never validated, and
    dropping it silently makes the mascot look broken instead of careful."""
    dropped = actions.dropped_repositories([
        "http://example.com/repo",
        "data:text/plain;base64,AAAA",
        "relative/path",
        "file://elsewhere/home/ti/repo",
    ])
    assert dropped.accepted == []
    assert [reason for _uri, reason in dropped.rejected] == [
        actions.REASON_NOT_LOCAL,            # http
        actions.REASON_NOT_LOCAL,            # data
        actions.REASON_NOT_LOCAL,            # no scheme at all
        actions.REASON_NOT_LOCAL,            # file:// on another host
    ]
    assert dropped.rejected[0][0] == "http://example.com/repo", \
        "the reason has to name the thing it rejected"


def test_a_parent_segment_never_reaches_the_filesystem(tmp_path):
    """`file:///home/ti/projects/../../../etc` normalises to /etc. No file
    manager emits one, so a URI carrying `..` was assembled by something else,
    and a path whose meaning depends on when it is resolved is not one to hand
    to a subprocess."""
    repo = _repo(tmp_path / "hub")
    sneaky = f"file://{tmp_path}/hub/../hub"
    dropped = actions.dropped_repositories([sneaky])
    assert dropped.accepted == []
    assert dropped.rejected == [(sneaky, actions.REASON_UNSAFE)]
    # The same directory, named plainly, is fine — so the rejection is about
    # the `..` and not about the folder.
    assert actions.dropped_repositories([repo.as_uri()]).accepted == \
        [os.path.realpath(repo)]


def test_a_symlink_is_followed_and_what_comes_back_is_the_real_folder(tmp_path):
    """Keeping repositories behind links is normal, so refusing them refuses
    real work. But the caller must be handed the directory that was actually
    checked: return the link and the name can be repointed between the check
    and the `claude -p` that uses it."""
    repo = _repo(tmp_path / "real")
    link = tmp_path / "link"
    link.symlink_to(repo, target_is_directory=True)
    dropped = actions.dropped_repositories([link.as_uri()])
    assert dropped.accepted == [os.path.realpath(repo)]
    assert str(link) not in dropped.accepted

    dangling = tmp_path / "dangling"
    dangling.symlink_to(tmp_path / "gone", target_is_directory=True)
    broken = actions.dropped_repositories([dangling.as_uri()])
    assert broken.accepted == []
    assert broken.rejected == [(dangling.as_uri(), actions.REASON_MISSING)]


def test_a_file_and_a_folder_that_is_not_a_repository_both_fail(tmp_path):
    """`claude -p` in a downloads folder is a paid call about nothing, and in
    `/` it is a paid call about everything. The `.git` is what makes the
    difference sayable: "that is not a repository"."""
    plain = tmp_path / "notes.md"
    plain.write_text("hello", encoding="utf-8")
    folder = tmp_path / "downloads"
    folder.mkdir()
    missing = tmp_path / "gone"

    dropped = actions.dropped_repositories(
        [plain.as_uri(), folder.as_uri(), missing.as_uri()])
    assert dropped.accepted == []
    assert [reason for _uri, reason in dropped.rejected] == [
        actions.REASON_NOT_A_FOLDER,
        actions.REASON_NOT_A_REPOSITORY,
        actions.REASON_MISSING,
    ]
    # A worktree or submodule has a .git file rather than a directory.
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    assert actions.dropped_repositories([worktree.as_uri()]).accepted == \
        [os.path.realpath(worktree)]


def test_a_selection_of_four_hundred_folders_becomes_eight(tmp_path):
    """One accepted folder is one `claude -p`, billed. Dropping a home
    directory's worth of them must not be four hundred subscription calls, and
    must not be four hundred stat calls either."""
    repos = [_repo(tmp_path / f"r{i:03d}") for i in range(12)]
    # Everything past the limit points at nothing at all. If the answer for
    # those is `tooMany` rather than `missing`, the filesystem was never asked.
    phantom = [f"file://{tmp_path}/never-created-{i}" for i in range(388)]
    dropped = actions.dropped_repositories([r.as_uri() for r in repos] + phantom)

    assert len(dropped.accepted) == actions.DROP_LIMIT
    assert dropped.accepted == [os.path.realpath(r) for r in repos[:actions.DROP_LIMIT]]
    over = [reason for _uri, reason in dropped.rejected]
    assert set(over) == {actions.REASON_TOO_MANY}
    assert len(over) == 4 + 388, "every rejection has to be reported, not just some"


def test_a_uri_list_blob_is_split_and_its_comments_ignored(tmp_path):
    """QMimeData hands drops over as a CRLF-separated text/uri-list as often
    as a list. Treated as one string it becomes a single path with newlines in
    it, and that path goes into a prompt."""
    repo = _repo(tmp_path / "hub")
    blob = f"# comment\r\n{repo.as_uri()}\r\nhttp://nope/\r\n"
    dropped = actions.dropped_repositories(blob)
    assert dropped.accepted == [os.path.realpath(repo)]
    assert dropped.rejected == [("http://nope/", actions.REASON_NOT_LOCAL)]
    # And a single list entry that smuggled a second URI inside itself is
    # split the same way rather than being treated as one exotic path.
    smuggled = actions.dropped_repositories([f"{repo.as_uri()}\nhttp://nope/"])
    assert smuggled.accepted == [os.path.realpath(repo)]
    assert smuggled.rejected == [("http://nope/", actions.REASON_NOT_LOCAL)]


def test_a_newline_in_the_path_is_refused_however_it_was_encoded(tmp_path):
    """Percent-decoding happens here, so %0A arrives as a real newline after
    the split that would have caught it. Downstream every line-oriented thing
    — and the prompt — reads it as two."""
    dropped = actions.dropped_repositories([f"file://{tmp_path}/hub%0Aetc"])
    assert dropped.accepted == []
    assert [reason for _uri, reason in dropped.rejected] == [actions.REASON_UNSAFE]


def test_percent_encoding_is_decoded_and_nothing_else_is(tmp_path):
    """A folder called `~` is a folder called `~`. Expanding it, or `$HOME`,
    lets the contents of a dropped string choose a directory it never named —
    and the one it chooses is the user's home."""
    spaced = _repo(tmp_path / "my repo")
    tilde = _repo(tmp_path / "~")
    variable = _repo(tmp_path / "$HOME")

    dropped = actions.dropped_repositories(
        [spaced.as_uri(), tilde.as_uri(), variable.as_uri()])
    assert dropped.accepted == [os.path.realpath(spaced),
                                os.path.realpath(tilde),
                                os.path.realpath(variable)]
    assert os.path.realpath(Path.home()) not in dropped.accepted


# ── the perch ──

def test_a_window_narrower_than_the_sprite_is_still_sat_on():
    """Pushed inside a 40 px window the sprite would sit off the end of the
    bar. Centred, it overhangs both sides evenly, which is what sitting on
    something small looks like."""
    window = {"x": 1000.0, "y": 300.0, "width": 40.0, "height": 220.0}
    x, y = actions.perch_position(window, SPRITE, BOUNDS)
    assert x == 1000.0 + 20.0 - SPRITE / 2.0, "not centred on the narrow window"
    assert x < 1000.0 and x + SPRITE > 1040.0, "stopped overhanging"
    assert y == 300.0 - SPRITE + actions.PERCH_SINK


def test_a_window_off_the_screen_has_nowhere_to_perch():
    """A window on a disconnected monitor, or one that KWin still lists after
    it moved away, gives coordinates outside every screen. Perching there
    parks the character where nobody can see it, and the companion looks like
    it crashed."""
    for rect in ((-4000.0, 300.0, 800.0, 600.0),      # left of everything
                 (9000.0, 300.0, 800.0, 600.0),       # right of everything
                 (1000.0, -2000.0, 800.0, 600.0),     # above
                 (1000.0, 5000.0, 800.0, 600.0)):     # below
        window = dict(zip(("x", "y", "width", "height"), rect))
        assert actions.perch_position(window, SPRITE, BOUNDS) is None, rect
    assert actions.perch_position(None, SPRITE, BOUNDS) is None
    assert actions.perch_position({"x": 0, "y": 0, "width": 0, "height": 0},
                                  SPRITE, BOUNDS) is None


def test_a_maximised_window_is_sat_in_its_bar_rather_than_above_the_screen():
    """Measured here: a maximised konsole is at y=0. Its title bar has nothing
    above it, so the honest perch overlaps the bar; the alternative is a
    position off the top of the screen, which is no companion at all."""
    window = {"x": 0.0, "y": 0.0, "width": 2194.3, "height": 1233.8}
    x, y = actions.perch_position(window, SPRITE, BOUNDS)
    assert y == BOUNDS[1], f"perched above the screen at {y}"
    assert BOUNDS[0] <= x <= BOUNDS[2]


def test_a_half_off_screen_window_is_perched_over_the_half_that_shows():
    """Centring on the whole window sends the character off toward a corner
    that is not on any monitor, to sit above a title bar nobody can see."""
    window = {"x": -600.0, "y": 400.0, "width": 1000.0, "height": 500.0}
    x, _y = actions.perch_position(window, SPRITE, BOUNDS)
    # The visible strip runs from the left edge of the walkable area to x=400,
    # so the middle of what can be seen is 204 and the sprite is centred there.
    middle = (BOUNDS[0] + 400.0) / 2.0
    assert x == middle - SPRITE / 2.0, f"perched over the invisible half: {x}"
    # Centring on the whole window and clamping afterwards would both put it
    # hard against the left edge instead.
    assert x != BOUNDS[0]


def test_a_minimised_window_is_not_perched_on():
    """KWin keeps reporting the geometry of a minimised window. Sitting on it
    puts the character in the middle of the desktop, apparently at random."""
    window = {"x": 300.0, "y": 400.0, "width": 900.0, "height": 600.0,
              "minimized": True}
    assert actions.perch_position(window, SPRITE, BOUNDS) is None
    window["minimized"] = False
    assert actions.perch_position(window, SPRITE, BOUNDS) is not None


# ── the geometry that comes from KWin ──

# Captured on this machine, verbatim:
#   busctl --user call org.kde.KWin /WindowsRunner org.kde.krunner1 \
#          Match s "konsole" --json=short
MATCH_REPLY = (
    '{"type":"a(sssida{sv})","data":[[["0_{d99ef423-a543-42a0-805c-1c12755e7b37}",'
    '"adb_tools : claude — Konsole","utilities-terminal",30,'
    '6.999999999999999555911e-01,{"subtext":{"type":"s","data":"Activate running '
    'window on Terminais"}}],["0_{46171fa6-b6a4-4e5e-8c5c-f35204fe8ade}",'
    '"~ : claude — Konsole","utilities-terminal",30,6.999999999999999555911e-01,'
    '{"subtext":{"type":"s","data":"Activate running window on Terminais"}}],'
    '["0_{fc9ffc42-8b69-454b-aff8-1a1bb221cdc6}","~ : claude — Konsole",'
    '"utilities-terminal",30,6.999999999999999555911e-01,{"subtext":{"type":"s",'
    '"data":"Activate running window on hubspoke"}}]]]}')

#   busctl --user call org.kde.KWin /KWin org.kde.KWin \
#          getWindowInfo s "{d99ef423-a543-42a0-805c-1c12755e7b37}" --json=short
INFO_REPLY = (
    '{"type":"a{sv}","data":[{"activities":{"type":"as","data":'
    '["9e7f61a6-5d4b-4599-b1af-3e95ccc97d44"]},"caption":{"type":"s","data":'
    '"adb_tools : claude — Konsole"},"clientMachine":{"type":"s","data":""},'
    '"desktopFile":{"type":"s","data":"org.kde.konsole"},"desktops":{"type":"as",'
    '"data":["81c096be-930d-4f8b-818b-24982a6739e5"]},"excludeFromCapture":'
    '{"type":"b","data":false},"fullscreen":{"type":"b","data":false},'
    '"hasTransientParent":{"type":"b","data":false},"height":{"type":"d","data":'
    '1.233771428571428714349e+03},"keepAbove":{"type":"b","data":false},'
    '"keepBelow":{"type":"b","data":false},"layer":{"type":"i","data":2},'
    '"localhost":{"type":"b","data":true},"maximizeHorizontal":{"type":"i","data":2},'
    '"maximizeVertical":{"type":"i","data":1},"minimized":{"type":"b","data":false},'
    '"noBorder":{"type":"b","data":false},"pid":{"type":"i","data":11240},'
    '"resourceClass":{"type":"s","data":"org.kde.konsole"},"resourceName":'
    '{"type":"s","data":"konsole"},"role":{"type":"s","data":""},"skipPager":'
    '{"type":"b","data":false},"skipSwitcher":{"type":"b","data":false},'
    '"skipTaskbar":{"type":"b","data":false},"type":{"type":"i","data":0},"uuid":'
    '{"type":"s","data":"{d99ef423-a543-42a0-805c-1c12755e7b37}"},"width":'
    '{"type":"d","data":2.194285714285714220750e+03},"x":{"type":"d","data":'
    '0.000000000000000000000e+00},"y":{"type":"d","data":'
    '0.000000000000000000000e+00}}]}')

# The reply for a match id that turns out to be a virtual desktop, not a
# window. The runner answers an empty query with both.
EMPTY_REPLY = '{"type":"a{sv}","data":[{}]}'

# The same enumeration as it arrives from an empty query, which is what the
# lookup actually sends: measured at 18 rows for 10 distinct windows, each one
# repeated with a different relevance. Built by putting the first row of the
# capture above back at the head of the list with the relevance the empty
# query gives it.
_REPEATED_ROW = (
    '["0_{d99ef423-a543-42a0-805c-1c12755e7b37}","adb_tools : claude — Konsole",'
    '"utilities-terminal",100,8.000000000000000444089e-01,{"subtext":{"type":"s",'
    '"data":"Activate running window on Terminais"}}],')
MATCH_WITH_REPEATS = MATCH_REPLY.replace('"data":[[', '"data":[[' + _REPEATED_ROW, 1)


def test_the_window_ids_come_out_of_the_runner_reply_without_repeats():
    """An empty query enumerates every window and returns each one more than
    once — 18 rows for 10 windows here. One getWindowInfo per row is twice the
    compositor round trips for the same answer."""
    ids = ["{d99ef423-a543-42a0-805c-1c12755e7b37}",
           "{46171fa6-b6a4-4e5e-8c5c-f35204fe8ade}",
           "{fc9ffc42-8b69-454b-aff8-1a1bb221cdc6}"]
    assert actions.parse_match(MATCH_REPLY) == ids
    assert actions.parse_match(MATCH_WITH_REPEATS) == ids, "asked KWin twice"
    assert actions.parse_match(MATCH_REPLY + MATCH_REPLY[:5]) == []
    assert actions.parse_match("") == []
    assert actions.parse_match(None) == []


def test_the_geometry_parses_out_of_the_captured_reply():
    """The numbers arrive as GVariant doubles in exponent form and the
    maximise state arrives as the enum bits it matched, 2 and 1, not as
    booleans. Read as truthiness alone, a restored window reads maximised."""
    info = actions.parse_window_info(INFO_REPLY)
    assert info["pid"] == 11240
    assert (info["x"], info["y"]) == (0.0, 0.0)
    assert round(info["width"], 4) == 2194.2857
    assert round(info["height"], 4) == 1233.7714
    assert info["minimized"] is False
    assert info["skipTaskbar"] is False
    assert info["maximized"] is True
    assert info["uuid"] == "{d99ef423-a543-42a0-805c-1c12755e7b37}"


def test_a_desktop_is_not_a_window_and_a_broken_reply_is_not_either():
    """The runner answers an empty query with virtual desktops as well as
    windows, and getWindowInfo returns an empty map for those. Treated as a
    window it becomes a geometry of zeros at the origin, which passes every
    bounds check and puts the character in the top-left corner."""
    assert actions.parse_window_info(EMPTY_REPLY) is None
    assert actions.parse_window_info('{"type":"a{sv}","data":[]}') is None
    assert actions.parse_window_info("not json at all") is None
    assert actions.parse_window_info(None) is None


def test_the_window_is_matched_through_the_process_tree_not_by_pid():
    """The chain is claude -> shell -> terminal and only the last owns a
    window, so matching the session pid against window pids matches nothing,
    ever, and the perch silently never happens."""
    calls = []
    captured_pid = '"pid":{"type":"i","data":11240}'

    def _with_pid(pid):
        return INFO_REPLY.replace(captured_pid,
                                  '"pid":{"type":"i","data":' + str(pid) + "}")

    def runner(path, _iface, method, *args):
        calls.append((path, method) + args)
        if method == "Match":
            return MATCH_REPLY
        # The window belongs to this process's parent, which is an ancestor
        # and not the pid asked about — so the lookup has to have climbed.
        return _with_pid(os.getppid())

    found = actions.window_geometry(os.getpid(), runner=runner)
    assert found is not None, "walked the tree and matched nothing"
    assert found["pid"] == os.getppid()
    assert calls[0][1] == "Match"

    # A menu or a tooltip carries the pid of the application that opened it,
    # so the first thing in the list with a matching pid may be a popup that
    # exists for half a second. Perching on one is perching on nothing.
    popup = _with_pid(os.getppid()).replace(
        '"skipTaskbar":{"type":"b","data":false}',
        '"skipTaskbar":{"type":"b","data":true}')
    replies = [MATCH_REPLY, popup, _with_pid(os.getppid())]

    def with_popup(_path, _iface, _method, *_args):
        return replies.pop(0)
    solid = actions.window_geometry(os.getpid(), runner=with_popup)
    assert solid is not None and solid["skipTaskbar"] is False

    # A pid whose tree contains none of the windows gets nothing rather than
    # the first window on the desktop. 2**30 is above every pid_max in use.
    def stranger(_path, _iface, method, *_args):
        return MATCH_REPLY if method == "Match" else _with_pid(2 ** 30)
    assert actions.window_geometry(os.getpid(), runner=stranger) is None


def test_a_compositor_that_does_not_answer_produces_none():
    """Every failure here — no busctl, no KWin, a terminal that has closed —
    has to look the same to the caller, because the caller's answer to all of
    them is the same: carry on walking."""
    assert actions.window_geometry(os.getpid(),
                                   runner=lambda *_a, **_k: None) is None
    assert actions.window_geometry(0, runner=lambda *_a, **_k: MATCH_REPLY) is None
    assert actions.window_geometry(None, runner=lambda *_a, **_k: MATCH_REPLY) is None


def test_the_process_tree_is_walked_upward_and_stops_at_init():
    """A walk that does not stop climbing reaches pid 1 and matches whatever
    window systemd is imagined to own; one that does not climb at all never
    reaches the terminal."""
    chain = actions.session_ancestors(os.getpid())
    assert chain[0] == os.getpid()
    assert chain[1] == os.getppid()
    assert 1 not in chain, "climbed all the way to init"
    assert len(chain) <= actions.ANCESTOR_DEPTH
    assert actions.session_ancestors("not a pid") == []


# ── handing over the pointer ──

def test_a_window_on_the_other_monitor_does_not_get_the_pointer():
    """Measured: the two screens here are 1234 and 1200 pixels tall. A run
    between them passes through rows that exist on one and not the other, the
    compositor clamps the pointer to a valid position, the clamped part of
    every delta is gone, and the pointer arrives somewhere else — with the
    user's hand still on it."""
    here = (400.0, 900.0)                       # on HDMI-A-1
    far = {"x": 2400.0, "y": 300.0, "width": 900.0, "height": 600.0}
    assert actions.delivery_target(far, SPRITE, BOUNDS, here, SCREENS) is None
    # The same window, approached from its own screen, is fine.
    assert actions.delivery_target(far, SPRITE, BOUNDS, (2500.0, 500.0),
                                   SCREENS) is not None


def test_the_pointer_is_delivered_to_the_middle_of_the_window():
    """The right end of a title bar is the close button. A pointer parked
    there invites the click that kills the session it was sent to rescue."""
    window = {"x": 300.0, "y": 200.0, "width": 800.0, "height": 600.0}
    x, y = actions.delivery_target(window, SPRITE, BOUNDS, (100.0, 900.0), SCREENS)
    # The sprite's centre lands on the window's centre, so the pointer it is
    # carrying ends up inside the window rather than on its frame.
    assert (x + SPRITE / 2.0, y + SPRITE / 2.0) == (700.0, 500.0)


def test_an_unknown_layout_is_a_refusal_rather_than_a_guess():
    """This is the rung that takes the mouse out of someone's hand, and it
    cannot be undone by ignoring it. With no origin or no screen list the
    cross-monitor question has no answer, and an unanswered question about a
    destructive act is a no."""
    window = {"x": 300.0, "y": 200.0, "width": 800.0, "height": 600.0}
    assert actions.delivery_target(window, SPRITE, BOUNDS, None, SCREENS) is None
    assert actions.delivery_target(window, SPRITE, BOUNDS, (100.0, 900.0), []) is None
    assert actions.delivery_target(window, SPRITE, BOUNDS, (100.0, 900.0),
                                   None) is None


def test_a_window_nobody_can_see_does_not_get_the_pointer_either():
    """Minimised, closed since the geometry was read, or off every screen: in
    all three the pointer would be dropped on empty desktop and the person
    would have to go and find it."""
    assert actions.delivery_target(None, SPRITE, BOUNDS, (100.0, 900.0),
                                   SCREENS) is None
    minimised = {"x": 300.0, "y": 200.0, "width": 800.0, "height": 600.0,
                 "minimized": True}
    assert actions.delivery_target(minimised, SPRITE, BOUNDS, (100.0, 900.0),
                                   SCREENS) is None
    gone = {"x": -9000.0, "y": 200.0, "width": 800.0, "height": 600.0}
    assert actions.delivery_target(gone, SPRITE, BOUNDS, (100.0, 900.0),
                                   SCREENS) is None
