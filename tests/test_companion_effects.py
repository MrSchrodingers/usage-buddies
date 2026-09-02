"""Nothing drawn is unreachable, and nothing reachable goes undrawn.

This project has paid for the other arrangement once. The `twoRed` category
shipped with four English lines and four Portuguese ones about two red quotas
at the same time, and no code path could select it — eight written sentences
that could not appear, for as long as nobody looked. Art is the same defect
with a bigger diff: a prop nothing triggers and a mood nothing sets are work
that renders in no session, and the suite is green either way.

So each of the three tables is held to the thing that can produce it. A mood
is a `dumbness.level` the collector writes, a prop trigger is a signal key the
detector emits, and a particle effect is a clip the animator can be in. The
companion resolves all three *through* the tables rather than by hand — which
is what makes a new entry work without new code, and also what makes an
unreachable entry silent.
"""
import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import buddy_signals as signals
import buddy_sprites as sprites

COMPANION = REPO / "scripts" / "usage-buddy-companion.py"
COLLECTOR = REPO / "scripts" / "usage-buddies-collector.py"

# A prop the companion raises from its own state rather than from a signal the
# detector emits. Named here rather than skipped silently, so a second one
# cannot be added without this list saying so.
NOT_A_SIGNAL = {"focus"}


def _collector_levels():
    """The dumbness levels the collector can write into widget-data.json."""
    text = COLLECTOR.read_text()
    return set(re.findall(r'"level":\s*"(\w+)"', text)) | \
        set(re.findall(r"level\s*=\s*['\"](\w+)['\"]", text))


def test_the_level_scan_finds_the_collectors_own_vocabulary():
    """Read by pattern, so the pattern has to be shown to match. Finding
    nothing would make every mood below reachable by vacuum."""
    levels = _collector_levels()
    assert len(levels) >= 4, sorted(levels)
    assert "braindead" in levels, sorted(levels)


@pytest.mark.parametrize("mood", sorted(sprites.MOODS))
def test_every_mood_is_a_level_the_collector_can_write(mood):
    """A mood keyed on a level nothing produces is drawn in no session. The
    companion reads `level if level in sprites.MOODS`, so the miss is silent:
    no exception, no mood, no clue."""
    assert mood in _collector_levels(), (
        "%s is drawn but no dumbness level of that name is ever written" % mood)


@pytest.mark.parametrize("trigger", sorted(sprites.PROP_TRIGGERS))
def test_every_prop_trigger_is_something_that_can_fire(trigger):
    """The companion looks the prop up as PROP_TRIGGERS[key] where key is the
    signal that just spoke, so a trigger naming a key the detector cannot emit
    is a prop that never appears."""
    if trigger in NOT_A_SIGNAL:
        return
    assert trigger in signals.PRIORITY, (
        "%s triggers a prop and is not a key buddy_signals can emit" % trigger)


@pytest.mark.parametrize("trigger,prop", sorted(sprites.PROP_TRIGGERS.items()))
def test_every_prop_trigger_names_a_prop_that_exists(trigger, prop):
    """PROP_TRIGGERS[key] is indexed straight into the prop table."""
    assert prop in sprites.PROPS, "%s -> %s, which is not a prop" % (trigger, prop)


@pytest.mark.parametrize("effect", sorted(sprites.PARTICLE_EFFECTS))
def test_every_particle_effect_is_a_clip_the_character_can_be_in(effect):
    """Particles are keyed by clip name so the question "which effect is
    playing" is the question "which clip is playing" and cannot drift from it.
    An effect named for a clip that does not exist never plays."""
    assert effect in sprites.CLIPS, (
        "%s has particles and is not a clip anything can enter" % effect)


@pytest.mark.parametrize("prop", sorted(sprites.PROPS))
def test_every_prop_has_something_that_raises_it(prop):
    """The other direction, which is the one that catches art nobody wired.
    A prop drawn, anchored for both brands and reachable by nothing is exactly
    the twoRed defect wearing a different hat."""
    assert prop in set(sprites.PROP_TRIGGERS.values()), (
        "%s is drawn and anchored and no trigger raises it" % prop)


@pytest.mark.parametrize("particle", sorted(sprites.PARTICLES))
def test_every_particle_is_used_by_some_effect(particle):
    """Same direction, one level down: a mote drawn and never laid out."""
    used = {name
            for effect in sprites.PARTICLE_EFFECTS.values()
            for _anchor, motes in effect
            for name, _dx, _dy in motes}
    assert particle in used, "%s is drawn and no effect places it" % particle


def test_the_companion_resolves_through_the_tables_rather_than_by_hand():
    """The reachability above is only worth anything while the companion reads
    the tables. A hardcoded `if key == "incident": prop = "umbrella"` would
    keep every assertion above true and quietly ignore the other five."""
    source = COMPANION.read_text()
    for table in ("PROP_TRIGGERS", "MOODS", "PARTICLE_EFFECTS"):
        assert "sprites.%s" % table in source, (
            "the companion no longer reads sprites.%s, so entries added to it "
            "reach nothing" % table)


def _load():
    spec = importlib.util.spec_from_file_location("companion_effects", COMPANION)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["companion_effects"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("level", sorted(sprites.MOODS))
def test_a_level_the_collector_wrote_becomes_the_mood_that_is_drawn(level):
    """End to end through the companion's own resolution, so the parametrised
    checks above cannot all hold while the one function that uses them returns
    the empty string for everything."""
    mod = _load()
    assert mod.Companion._level_of({"dumbness": {"level": level}}) == level


def test_a_level_nobody_drew_resolves_to_no_mood_rather_than_to_a_crash():
    """widget-data.json is written by a separate process on a timer, and a
    level this build has no art for has to be absence, not an exception on the
    paint path."""
    mod = _load()
    assert mod.Companion._level_of({"dumbness": {"level": "enlightened"}}) == ""
    assert mod.Companion._level_of({}) == ""
    assert mod.Companion._level_of({"dumbness": None}) == ""
