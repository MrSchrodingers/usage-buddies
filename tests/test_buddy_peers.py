"""Two companions noticing each other, and the six ways that goes wrong.

It freezes — a presence file caught mid-write, or a coordinate that parses as
NaN, raising inside the frame timer, which is not a logged traceback but a
mascot standing still for the rest of the session. It chases a ghost — a pid
reused by something that is not a companion, or a file left by a process that
was killed, and the character walks to a window nobody can see. They chase each
other — both processes decide to be the one that approaches, with no message
between them to settle it. They loop — two mascots parked side by side satisfy
the meeting condition on every single read and greet each other forever. It
goes catatonic — the peer stops publishing mid-encounter and the state machine
never lets go. And it costs — a directory scan on every frame, permanently, for
a joke.

Time is an argument throughout, so none of this sleeps.
"""
import json
import math
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import buddy_peers as peers

# Measured on this machine: the command line of a companion started by
# companion-ctl.sh. argv[0] is the interpreter, which is the trap the ctl
# script documents paying for.
COMPANION_ARGV = ["/usr/bin/python3",
                  "/home/ti/.local/bin/usage-buddy-companion.py", "--codex"]

# Also measured: the zsh that ran the window-tree measurements for this
# feature. The script name is in its command line, inside a -c argument.
NOISY_SHELL_ARGV = [
    "/usr/bin/zsh", "-c",
    ("eval 'setsid python3 /tmp/scratch/scripts/usage-buddy-companion.py "
     "--codex --alerts-only > /tmp/scratch/companion3.log 2>&1 < /dev/null'")]


def _payload(pid=101, brand="claude", x=0.0, y=0.0, at=0.0, **extra):
    row = {"pid": pid, "brand": brand, "x": x, "y": y, "at": at}
    row.update(extra)
    return json.dumps(row).encode("utf-8")


def _peer(pid=101, brand="claude", x=0.0, y=0.0, at=0.0):
    return peers.Peer(pid, brand, float(x), float(y), float(at))


def _nearby_pids(me, candidates, radius=peers.NOTICE_RADIUS):
    return [p.pid for p in peers.nearby(me, candidates, radius)]


def _fake_proc(root, pid, argv=None):
    """A /proc/<pid>/cmdline that says what we want it to say."""
    entry = Path(root) / str(pid)
    entry.mkdir(parents=True, exist_ok=True)
    (entry / "cmdline").write_bytes(
        b"\0".join(part.encode("utf-8") for part in (argv or COMPANION_ARGV)) + b"\0")
    return str(root)


# ── reading a file somebody else is writing ────────────────────────────────

def test_a_presence_file_caught_mid_write_does_not_raise():
    """This is decoded inside the frame timer. An exception here does not print
    a stack and carry on, it stops the frame that was drawing the character —
    so the mascot freezes because another process was killed mid-write."""
    for raw in (b"", b"{", b"[", b'{"pid": 101, "brand": "cla',
                b"\xff\xfe\x00", b"[" * 2000, b"null", b"12", b'"claude"'):
        assert peers.decode(101, raw, 0.0) is None, raw


def test_a_presence_file_of_the_wrong_shape_does_not_raise():
    """Nothing about the file is guaranteed: it is JSON from another process
    that may be a version behind, or truncated, or somebody's editor swap file
    with a numeric name. Every field is checked before it is believed."""
    hostile = [
        None, 12, [], {},
        _payload(brand=None), _payload(brand=7), _payload(brand=""),
        _payload(brand="b" * (peers.BRAND_MAX + 1)),
        _payload(x="12"), _payload(y={"a": 1}), _payload(at=None),
        _payload(x=True),          # JSON true is an int in Python, not a place
        b'{"brand": "claude", "x": 1, "y": 2}',       # no timestamp at all
        b'{"pid": 101, "x": 1, "y": 2, "at": 0}',     # no brand
    ]
    for raw in hostile:
        assert peers.decode(101, raw, 0.0) is None, raw
    # The instrument finds the positive case: a whole file still decodes.
    assert peers.decode(101, _payload(x=3, y=4), 0.0) == _peer(x=3, y=4)


def test_a_coordinate_that_is_not_a_number_is_refused():
    """NaN and Infinity are valid JSON to this parser — measured,
    `json.loads(b"NaN")` returns nan and `b"1e999"` returns inf. A NaN
    coordinate makes every distance comparison false, so the feature reads as
    silently not implemented; an infinite one sends the character off-screen."""
    for raw in (b'{"pid":101,"brand":"claude","x":NaN,"y":0,"at":0}',
                b'{"pid":101,"brand":"claude","x":0,"y":Infinity,"at":0}',
                b'{"pid":101,"brand":"claude","x":1e999,"y":0,"at":0}',
                b'{"pid":101,"brand":"claude","x":0,"y":0,"at":NaN}'):
        assert peers.decode(101, raw, 0.0) is None, raw


def test_a_file_that_names_a_different_pid_is_not_believed():
    """A presence file copied rather than written describes a process that is
    not the one the filename claims, and its position belongs to nobody."""
    assert peers.decode(101, _payload(pid=999), 0.0) is None
    assert peers.decode("101", _payload(pid=101), 0.0) == _peer()
    assert peers.decode("not-a-pid", _payload(), 0.0) is None


def test_a_presence_file_older_than_the_expiry_is_ignored():
    """A companion killed with SIGKILL never removes its file. Without the age
    check the survivor keeps standing next to a mascot that closed hours ago."""
    assert peers.decode(101, _payload(at=0.0), peers.STALE_SECONDS - 0.1) is not None
    assert peers.decode(101, _payload(at=0.0), peers.STALE_SECONDS + 0.1) is None


def test_a_timestamp_from_before_the_last_reboot_is_refused():
    """The timestamps are monotonic, which restarts at zero on boot. A file
    left over from a long uptime therefore reads as newer than anything written
    now, and an age check alone would treat it as the freshest peer there is."""
    assert peers.decode(101, _payload(at=90_000.0), 30.0) is None


# ── is that pid still one of us ────────────────────────────────────────────

def test_the_liveness_check_finds_a_companion_whose_argv0_is_the_interpreter(tmp_path):
    """The positive case the instrument has to find, or every other check here
    is measuring nothing. A shebang script is exec'd as `/usr/bin/python3
    /path/script.py`: matching argv[0] alone finds no companion, ever."""
    root = _fake_proc(tmp_path / "proc", 101)
    assert peers.is_companion(101, root)
    assert peers.is_companion("101", root)


def test_a_pid_reused_by_a_shell_that_merely_mentions_the_script_is_rejected(tmp_path):
    """Pids get reused. A plain substring search over the command line accepts
    any shell that happens to name the script — the one that ran the window
    measurements for this feature was one, and companion-ctl.sh kills itself
    for the same reason. A reused pid accepted here puts the character in a
    staring contest with a window that does not exist."""
    root = _fake_proc(tmp_path / "proc", 101, NOISY_SHELL_ARGV)
    assert not peers.is_companion(101, root)


def test_a_pid_that_is_gone_is_not_alive(tmp_path):
    """The ordinary case: the process exited and /proc has nothing to say."""
    root = str(tmp_path / "proc")
    (tmp_path / "proc").mkdir()
    assert not peers.is_companion(404, root)
    (tmp_path / "proc" / "505").mkdir()          # a pid with no readable cmdline
    assert not peers.is_companion(505, root)
    assert not peers.is_companion(None, root)
    assert not peers.is_companion("junk", root)


def test_a_file_left_by_a_dead_process_is_ignored_and_marked_for_removal():
    """Nobody else clears these. Left alone the directory accumulates one file
    per pid that has ever run a companion, and the scan pays for all of them
    every second for the life of the desktop."""
    reading = peers.collect([(101, _payload())], 0.0, alive=lambda pid: False)
    assert reading.peers == []
    assert reading.dead == [101]


def test_an_expired_file_belonging_to_a_live_companion_is_not_deleted():
    """Old is not dead. A companion busy starting a subprocess can miss a
    publish; deleting its file makes it vanish from every other companion's
    view and stay gone until it writes again."""
    reading = peers.collect([(101, _payload(at=0.0))], 3600.0, alive=lambda pid: True)
    assert reading.peers == []
    assert reading.dead == [], "deleted a live companion's file"


# ── the directory ──────────────────────────────────────────────────────────

def test_a_presence_file_survives_the_round_trip(tmp_path):
    """The end-to-end positive control. Every other test in this section
    asserts that something is refused, and a module that refused everything
    would pass all of them."""
    root = _fake_proc(tmp_path / "proc", 101)
    yard = tmp_path / "peers"
    writer = peers.PeerDirectory(yard, pid=101, proc=root)
    me = writer.publish("codex", 12.5, 34.5, 5.0)
    assert me == _peer(101, "codex", 12.5, 34.5, 5.0)

    reader = peers.PeerDirectory(yard, pid=99, proc=root)
    assert reader.peers(5.0) == [_peer(101, "codex", 12.5, 34.5, 5.0)]


def test_a_read_inside_the_cadence_touches_the_disk_not_at_all(tmp_path):
    """The cost of the joke. This runs in a timer that ticks every 33 ms while
    the character walks, and the round trip measured 0.257 ms — 7.7 ms per
    second of walking if it is done every frame. The proof that it is not is
    that the directory can be deleted and the answer stays the same."""
    root = _fake_proc(tmp_path / "proc", 101)
    yard = tmp_path / "peers"
    yard.mkdir()
    (yard / "101.json").write_bytes(_payload(at=0.0))
    directory = peers.PeerDirectory(yard, pid=99, proc=root)
    assert [p.pid for p in directory.peers(0.0)] == [101]

    shutil.rmtree(yard)
    assert [p.pid for p in directory.peers(peers.READ_SECONDS - 0.1)] == [101], \
        "went back to the disk inside the cadence"
    assert directory.peers(peers.READ_SECONDS) == []


def test_a_publish_inside_the_cadence_touches_the_disk_not_at_all(tmp_path):
    """Same argument on the writing side: a file rewritten thirty times a
    second is thirty renames a second for a position that is read once."""
    yard = tmp_path / "peers"
    directory = peers.PeerDirectory(yard, pid=99, proc=str(tmp_path / "proc"))
    directory.publish("claude", 10, 20, 0.0)
    assert (yard / "99.json").exists()

    shutil.rmtree(yard)
    directory.publish("claude", 30, 40, peers.PUBLISH_SECONDS - 0.1)
    assert not yard.exists(), "wrote inside the cadence"
    directory.publish("claude", 30, 40, peers.PUBLISH_SECONDS)
    assert (yard / "99.json").exists()


def test_the_presence_file_is_swapped_in_rather_than_written_over(tmp_path, monkeypatch):
    """A file written in place is half-written for as long as the write takes,
    and the other companion reads it several times a minute. Rename is atomic
    only within one filesystem, so the temporary has to be a sibling of the
    real name rather than somewhere in /tmp."""
    swaps = []
    real = peers.os.replace
    monkeypatch.setattr(peers.os, "replace",
                        lambda src, dst: (swaps.append((src, dst)), real(src, dst))[1])
    yard = tmp_path / "peers"
    peers.PeerDirectory(yard, pid=99, proc=str(tmp_path / "proc")).publish(
        "claude", 1.0, 2.0, 0.0)

    assert len(swaps) == 1, "wrote the file in place"
    source, destination = (Path(p) for p in swaps[0])
    assert source.parent == destination.parent, "renamed across filesystems"
    assert destination.name == "99.json"
    assert [p.name for p in yard.iterdir()] == ["99.json"], "left a temporary behind"


def test_our_own_presence_file_is_not_read_back_as_a_peer(tmp_path):
    """A character that notices itself stops dead and stares at nothing, and
    the encounter never ends because the peer never walks away."""
    root = _fake_proc(tmp_path / "proc", 99)
    yard = tmp_path / "peers"
    directory = peers.PeerDirectory(yard, pid=99, proc=root)
    directory.publish("claude", 1.0, 2.0, 0.0)
    assert directory.peers(0.0) == []


def test_a_missing_cache_directory_is_an_empty_desktop_not_a_crash(tmp_path):
    """First run, or a cache someone cleaned out while the companion was up."""
    directory = peers.PeerDirectory(tmp_path / "nothing" / "here", pid=99,
                                    proc=str(tmp_path / "proc"))
    assert directory.peers(0.0) == []


def test_a_directory_full_of_junk_yields_the_peer_that_is_real(tmp_path):
    """Anything can end up in a cache directory: editor leftovers, a partial
    write, a name that is not a pid, even a directory. None of it may raise,
    and none of it may hide the one companion that is actually there."""
    root = tmp_path / "proc"
    for pid in (101, 202, 303):
        _fake_proc(root, pid)
    yard = tmp_path / "peers"
    yard.mkdir()
    (yard / "101.json").write_bytes(_payload(pid=101, x=5, y=6))
    (yard / "202.json").write_bytes(b'{"pid": 202, "bra')      # caught mid-write
    (yard / "notapid.json").write_bytes(_payload())
    (yard / "readme.txt").write_bytes(b"not json at all")
    (yard / ".99.tmp").write_bytes(b"someone's half-written file")
    (yard / "303.json").mkdir()          # opening this raises IsADirectoryError

    directory = peers.PeerDirectory(yard, pid=99, proc=str(root))
    assert directory.peers(0.0) == [_peer(101, "claude", 5, 6, 0.0)]


def test_a_dead_companions_file_is_swept_instead_of_scanned_forever(tmp_path):
    """The sweep is bounded to files whose pid failed the liveness check, so it
    cannot delete a live companion's file out from under it."""
    root = _fake_proc(tmp_path / "proc", 101)
    yard = tmp_path / "peers"
    yard.mkdir()
    (yard / "101.json").write_bytes(_payload(pid=101))
    (yard / "202.json").write_bytes(_payload(pid=202))     # no /proc entry
    directory = peers.PeerDirectory(yard, pid=99, proc=root)

    assert [p.pid for p in directory.peers(0.0)] == [101]
    assert not (yard / "202.json").exists()
    assert (yard / "101.json").exists(), "swept a companion that is alive"


# ── who is near, and who walks ─────────────────────────────────────────────

def test_a_companion_on_the_other_side_of_the_desktop_is_not_noticed():
    """The desktop measured here is two monitors wide. Without a radius the
    two mascots would be permanently in each other's business."""
    me = _peer(100, "claude", 0, 0)
    assert _nearby_pids(me, [_peer(200, "codex", peers.NOTICE_RADIUS, 0)]) == [200]
    assert _nearby_pids(me, [_peer(200, "codex", peers.NOTICE_RADIUS + 1, 0)]) == []
    assert _nearby_pids(me, [_peer(200, "codex", 2000, 900)]) == []


def test_the_nearest_of_several_is_the_one_noticed():
    me = _peer(100, "claude", 0, 0)
    crowd = [_peer(300, "codex", 200, 0), _peer(200, "claude", 40, 0),
             _peer(400, "codex", 120, 0)]
    assert _nearby_pids(me, crowd) == [200, 400, 300]


def test_a_companion_does_not_notice_itself():
    """Its own file is skipped when the directory is read, and again here: two
    layers, because a character staring at itself never stops."""
    me = _peer(100, "claude", 0, 0)
    assert _nearby_pids(me, [_peer(100, "claude", 0, 0)]) == []


def test_a_peer_that_cannot_be_measured_is_never_the_nearest():
    """distance() is public and takes whatever it is handed. Answering 0 for
    something unmeasurable would make junk the closest thing on the screen, and
    a NaN coordinate that survived a hand-built Peer would sit at every radius
    at once."""
    me = _peer(100, "claude", 0, 0)
    assert peers.distance(me, _peer(200, "codex", 3, 4)) == 5.0
    assert peers.distance(me, object()) == math.inf
    assert peers.distance(me, _peer(200, "codex", float("nan"), 0)) == math.inf
    assert _nearby_pids(me, [_peer(200, "codex", float("nan"), 0)]) == []


def test_both_processes_pick_the_same_one_to_walk_over():
    """There is no message between the two processes. If both decide to
    approach they chase each other across the desktop; if both decide to wait
    they stand there. The tie is broken by the same rule on both sides."""
    for mine, theirs in ((100, 200), (200, 100), (7, 7000), (99999, 2)):
        assert peers.approaches(mine, theirs) != peers.approaches(theirs, mine)
        assert peers.approaches(min(mine, theirs), max(mine, theirs))
    assert not peers.approaches(None, 100)


def test_the_two_sides_stay_in_step_all_the_way_through_a_meeting():
    """The whole encounter, run from both processes at once over the same
    world. They have to agree on the phase at every step and disagree on the
    role at every step, with nothing passing between them but position."""
    mover, waiter = peers.Encounter(), peers.Encounter()
    ax, bx = 0.0, 300.0
    phases, roles = [], []
    for step in range(30):
        now = float(step)
        me_a = _peer(100, "claude", ax, 0, now)
        me_b = _peer(200, "codex", bx, 0, now)
        a = mover.update(me_a, [me_b], now)
        b = waiter.update(me_b, [me_a], now)
        if a is None or b is None:
            break
        assert a.phase == b.phase, f"out of step at {now}: {a.phase} vs {b.phase}"
        assert {a.role, b.role} == {peers.ROLE_MOVER, peers.ROLE_WAITER}
        assert a.role == peers.ROLE_MOVER, "the larger pid walked"
        phases.append(a.phase)
        roles.append(a.role)
        if a.phase == peers.PHASE_APPROACH:
            ax = min(bx, ax + 78.0)          # WALK_SPEED, one second of walking
    assert peers.PHASE_APPROACH in phases
    assert peers.PHASE_MEET in phases
    assert phases[-1] == peers.PHASE_PART


# ── the encounter ──────────────────────────────────────────────────────────

def _run(encounter, me_at, peer_at, span, brand="codex", pid=200, start=0.0):
    """`span` seconds at 1 Hz with both of them standing still. Returns the
    phases seen, in order."""
    seen = []
    for step in range(int(span)):
        now = start + float(step)
        me = _peer(100, "claude", *me_at, at=now)
        peer = _peer(pid, brand, *peer_at, at=now)
        meeting = encounter.update(me, [peer], now)
        seen.append(None if meeting is None else meeting.phase)
    return seen


def test_two_mascots_parked_side_by_side_greet_each_other_once():
    """The failure this state machine exists for. Two characters dropped in the
    same corner satisfy the meeting condition on every read, forever. A cooldown
    on its own only makes the loop periodic — one greeting every three minutes
    for as long as the desktop is up — so re-noticing also requires having been
    apart since."""
    encounter = peers.Encounter()
    seen = _run(encounter, (0, 0), (60, 0), 3600)
    assert seen.count(peers.PHASE_PART) == 1, "greeted again without moving"
    assert seen[0] == peers.PHASE_MEET
    assert seen[-1] is None


def test_the_end_of_a_meeting_is_announced_exactly_once():
    """The companion restores its own wandering when it sees PHASE_PART. Twice
    and it does it twice; never and it stands there."""
    encounter = peers.Encounter()
    seen = _run(encounter, (0, 0), (60, 0), 60)
    assert seen.count(peers.PHASE_PART) == 1
    assert seen.index(peers.PHASE_PART) == int(peers.MEET_SECONDS)


def test_they_notice_each_other_again_after_one_of_them_wanders_off():
    """The other half of the cooldown: it has to end. A pair that met once and
    then spent an afternoon apart are strangers again."""
    encounter = peers.Encounter()
    first = _run(encounter, (0, 0), (60, 0), 30)
    assert first.count(peers.PHASE_PART) == 1

    apart = _run(encounter, (0, 0), (peers.FORGET_RADIUS + 200, 0), 30, start=30.0)
    assert set(apart) == {None}
    later = 60.0 + peers.DISINTEREST_SECONDS
    back = _run(encounter, (0, 0), (60, 0), 30, start=later)
    assert back[0] == peers.PHASE_MEET, "never spoke to it again"


def test_a_pair_that_walked_away_is_forgotten_rather_than_remembered_forever():
    """A companion left running for days otherwise keeps one record per pid it
    has ever stood next to."""
    encounter = peers.Encounter()
    _run(encounter, (0, 0), (60, 0), 30)
    assert list(encounter._closed) == [200]
    _run(encounter, (0, 0), (peers.FORGET_RADIUS + 200, 0), 30,
         start=30.0 + peers.DISINTEREST_SECONDS)
    assert encounter._closed == {}


def test_an_approach_that_never_arrives_is_given_up():
    """The other one is docked in a corner the user put it in, or walking away
    as fast as this one follows. Without a limit the character spends the rest
    of the session walking toward something it will never reach."""
    encounter = peers.Encounter()
    seen = _run(encounter, (0, 0), (300, 0), 60)
    assert seen[0] == peers.PHASE_APPROACH
    assert seen.count(peers.PHASE_PART) == 1
    assert seen.index(peers.PHASE_PART) == int(peers.APPROACH_SECONDS)
    assert seen[-1] is None, "started the approach over"


def test_a_peer_that_stops_publishing_releases_the_character():
    """Closed, killed, or its cache went away in the middle of the meeting. The
    encounter holds the character still while it runs, so a state machine that
    never lets go is a mascot that never moves again."""
    encounter = peers.Encounter()
    me = _peer(100, "claude", 0, 0, 0.0)
    assert encounter.update(me, [_peer(200, "codex", 60, 0, 0.0)], 0.0) is not None
    assert encounter.busy
    assert encounter.update(_peer(100, "claude", 0, 0, 1.0), [], 1.0) is None
    assert not encounter.busy


def test_a_meeting_broken_up_by_the_user_ends_where_it_stands():
    """One of them is picked up mid-meeting and dropped on the other monitor.
    The one left behind has to stop facing an empty patch of desktop."""
    encounter = peers.Encounter()
    me = _peer(100, "claude", 0, 0, 0.0)
    assert encounter.update(me, [_peer(200, "codex", 60, 0, 0.0)], 0.0).phase \
        == peers.PHASE_MEET
    hauled = _peer(200, "codex", peers.FORGET_RADIUS + 100, 0, 1.0)
    assert encounter.update(_peer(100, "claude", 0, 0, 1.0), [hauled], 1.0).phase \
        == peers.PHASE_PART
    assert not encounter.busy


def test_the_two_brands_are_told_apart_without_the_reaction_being_decided_here():
    """Clawd meeting Rex is not Clawd meeting another Clawd, and which line
    that earns is the companion's business, not this module's."""
    same = peers.Encounter().update(_peer(100, "claude", 0, 0),
                                    [_peer(200, "claude", 60, 0)], 0.0)
    other = peers.Encounter().update(_peer(100, "claude", 0, 0),
                                     [_peer(200, "codex", 60, 0)], 0.0)
    assert same.same_brand and same.peer.brand == "claude"
    assert not other.same_brand and other.peer.brand == "codex"
    assert same.phase == other.phase, "the brand changed the state machine"


def test_a_meeting_that_starts_already_touching_does_not_wait_to_approach():
    """Two mascots that are already next to each other have nothing to
    approach, and starting them in APPROACH leaves the pair standing at arm's
    length until the approach times out twenty seconds later."""
    encounter = peers.Encounter()
    meeting = encounter.update(_peer(100, "claude", 0, 0),
                               [_peer(200, "codex", peers.MEET_RADIUS - 1, 0)], 0.0)
    assert meeting.phase == peers.PHASE_MEET


def test_nothing_at_all_happens_on_an_empty_desktop():
    """The common case: one companion, nobody else running."""
    encounter = peers.Encounter()
    assert encounter.update(_peer(100, "claude", 0, 0), [], 0.0) is None
    assert encounter.update(_peer(100, "claude", 0, 0), None, 1.0) is None
    assert not encounter.busy


def test_the_installer_copying_the_script_is_not_mistaken_for_a_companion(tmp_path):
    """Matching the script name in any argument answers yes to

        cp scripts/usage-buddy-companion.py ~/.local/bin/

    which is install.sh running. A presence file left by a dead companion
    whose pid the installer then reuses would be kept alive by that, and the
    character walks toward a position nobody is publishing any more.

    The window is the first two arguments, because a shebang script is exec'd
    as `python3 /path/script.py` and argv[0] is the interpreter — matching
    only argv[0] is the opposite mistake, and companion-ctl.sh documents
    paying for it.
    """
    cases = {
        b"/usr/bin/python3\x00/home/u/.local/bin/usage-buddy-companion.py\x00": True,
        b"/home/u/.local/bin/usage-buddy-companion.py\x00": True,
        b"/usr/bin/cp\x00scripts/usage-buddy-companion.py\x00/home/u/.local/bin/\x00": False,
        b"/usr/bin/vim\x00scripts/usage-buddy-companion.py\x00": False,
        b"/bin/sh\x00-c\x00echo usage-buddy-companion.py\x00": False,
    }
    for index, (argv, expected) in enumerate(cases.items()):
        root = tmp_path / str(index)
        (root / "4242").mkdir(parents=True)
        (root / "4242" / "cmdline").write_bytes(argv)
        got = peers.is_companion(4242, proc=str(root))
        assert got is expected, f"{argv!r} -> {got}, expected {expected}"
