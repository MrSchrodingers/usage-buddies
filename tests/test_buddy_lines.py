"""The shape of the dialogue table, which is not the same thing as its content.

Nothing here judges whether a line is funny. What it holds are the properties a
person cannot check by reading 512 sentences, and each one is a defect this
table has actually shipped.

A diagnosis with no number in it. 133 of the 416 lines whose category exists to
report a measurement never mentioned the measurement, so "days left, quota not"
went out at thirty percent and at ninety and read identically both times. That
is what was reported as the sentences sounding generic, and it is the half of
the complaint a test can hold: which categories owe a value is read off what
the signals actually emit, so the rule covers a category nobody remembered to
add to a list.

One rhythm for the whole table. Every line used to be "clause. clause." - a
statement and a dry remark, a hundred and thirty-nine times. Read once it is a
style; read all afternoon on a desktop it is a stutter, and the person watching
described it as the sentences running each other over. A cap per category is
the only version of that complaint a test can hold.

One length for the whole table. A ceiling raised from 110 to 150 does nothing
if every line lands on 100: the monotony is in the spread, not in the maximum.

A placeholder nothing fills. `{name}` with no value renders the braces into the
bubble. tests/test_buddy_signals.py checks the names against what the detector
emits; this one substitutes for real and looks at what is left, which is what
the person actually sees.

An emoji. Banned across the repository, and easier to catch here than to notice
in a diff of five hundred strings.
"""
import functools
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import buddy_lines
import buddy_voice

LINES = buddy_lines.LINES
MAX_CHARS = buddy_voice.MAX_CHARS

LANGS = ("en", "pt")

# Eight, and the same eight in both languages. Below that the rotation repeats
# inside a single quiet afternoon; the number is the one the table was written
# to and is pinned so that a category added later cannot arrive with three.
PER_CATEGORY = 8

# How many lines in a category may be built as "Statement. Dry remark." Three
# of eight leaves the form available - it is a good form, it was just the only
# one - while forcing the other five to be something else.
TWO_CLAUSE_MAX = 3

# The spread that has to be used. The short end is a reaction of a few words,
# the long end a sentence that needs the whole bubble; a category that lands
# between the two on all eight lines has recreated the monotony this replaced.
SHORT_ENOUGH = 55
LONG_ENOUGH = 95

# Anything in these ranges is an emoji, a pictograph, an arrow or a variation
# selector. Written as escapes rather than as the characters themselves,
# because a repository that bans them in its artefacts bans them here too.
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2190-\u21FF\uFE0F]")


# A value the companion drops into the sentence before showing it. `{n}` and
# `${usd}` both count; a lone brace does not, and catching that one is the job
# of the render check at the bottom of this file.
PLACEHOLDER = re.compile(r"{\w+}")


def _sentence_breaks(line):
    """Full stops with a sentence on both sides of them.

    A break is punctuation followed by whitespace and more text, so "3.5" and a
    line that simply ends do not count. Exactly one of these is the two-clause
    shape the cap is about.
    """
    return len(re.findall(r"[.!?]\s+\S", line))


@functools.cache
def _scenario_vars():
    """The variables each signal really emits, borrowed from its own suite.

    Imported rather than restated: a second copy of the payloads here would
    drift, and then this would be substituting values nothing produces.

    Cached because it is now read by three tests rather than one, and executing
    the sibling module a couple of hundred times to get back the same
    dictionary is most of this file's runtime spent on nothing.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "lines_scenarios", REPO / "tests" / "test_buddy_signals.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["lines_scenarios"] = module
    spec.loader.exec_module(module)
    found = {}
    for key, (positive, _) in module.SCENARIOS.items():
        found[key] = module.fired(positive)[key].vars
    # The two categories no signal names: the companion falls back to them when
    # nothing fired, and it passes no variables at all when it does.
    for key in module.FALLBACK_CATEGORIES:
        found[key] = {}
    return found


CATEGORIES = sorted(LINES["en"])


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("key", CATEGORIES)
def test_a_category_is_eight_lines_in_both_languages(lang, key):
    assert len(LINES[lang][key]) == PER_CATEGORY, len(LINES[lang][key])


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("key", CATEGORIES)
def test_a_category_says_the_value_it_was_given_or_is_given_none(lang, key):
    """The complaint about the sentences being generic, as a property.

    Which side a category falls on is not written down here. It is whether the
    signal that selects the category hands the line anything to say: quotaHigh
    arrives with a percentage, philosophy arrives with nothing. So a category
    added to buddy_signals with a variable is held to the rule from its first
    run, and one added without a variable is held to the opposite, and neither
    depends on somebody remembering to edit a list in this file.

    The rule runs in both directions on purpose. A diagnosis missing its number
    reads the same in every state it can fire in - "days left, quota not" is
    the line that shipped, and it is as true at thirty percent as at ninety.
    A placeholder in the five categories that describe no measurement is the
    mirror defect: those are where the voice lives, and a value dropped into
    one of them would print braces, because no signal fills it.
    """
    variables = _scenario_vars()
    assert key in variables, f"{key} has no scenario, so nothing classifies it"
    silent = [line for line in LINES[lang][key] if not PLACEHOLDER.search(line)]
    speaking = [line for line in LINES[lang][key] if PLACEHOLDER.search(line)]
    if variables[key]:
        assert not silent, (
            f"{lang}/{key} is handed {sorted(variables[key])} and "
            f"{len(silent)} of {PER_CATEGORY} lines never say it:\n"
            + "\n".join(silent))
    else:
        assert not speaking, (
            f"{lang}/{key} is handed nothing, so these print braces:\n"
            + "\n".join(speaking))


def test_the_split_those_rules_run_on_has_two_sides():
    """The instrument, against a case it is known to have to find.

    Both halves of the rule above read the same dictionary, so a _scenario_vars
    that came back empty for everything - a renamed field, a sibling suite that
    stopped exporting its table - would silently reclassify every category as
    voice and turn a real property into "nothing may carry a value". That would
    fail loudly rather than pass, which is the right direction, but it would
    fail for the wrong reason and send the next person to the wrong file. This
    says out loud that the split has two sides and puts one known member on
    each: staleData, which exists to quote a duration, and philosophy, which
    exists to quote nothing.
    """
    variables = _scenario_vars()
    fact = sorted(key for key in CATEGORIES if variables.get(key))
    voice = sorted(key for key in CATEGORIES if not variables.get(key))
    assert fact and voice, f"degenerate split: {len(fact)} fact, {len(voice)} voice"
    assert "staleData" in fact, fact
    assert "philosophy" in voice, voice


@pytest.mark.parametrize("lang", LANGS)
def test_stale_data_says_how_old_the_reading_is(lang):
    """The one category whose job is refusing to answer.

    Nothing read generatedAt until the freshness guard went in, so a dead
    collector left the companion quoting the last figures with the confidence
    it had when they were fresh. Refusing without saying how stale is the same
    defect one step quieter, so {age} is required in all eight rather than in
    the category somewhere.
    """
    assert "staleData" in LINES[lang], sorted(LINES[lang])
    lines = LINES[lang]["staleData"]
    assert len(lines) == PER_CATEGORY, len(lines)
    mute = [line for line in lines if "{age}" not in line]
    assert not mute, (
        f"{lang}/staleData: {len(mute)} lines refuse without saying how old:\n"
        + "\n".join(mute))


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("key", CATEGORIES)
def test_no_category_is_all_the_same_rhythm(lang, key):
    """The complaint that started this, as a number.

    Counting is per category rather than over the table, because rotation
    happens inside a category: a desktop sitting on one signal for an hour
    hears those eight lines and nothing else.
    """
    lines = LINES[lang][key]
    two_clause = [line for line in lines if _sentence_breaks(line) == 1]
    assert len(two_clause) <= TWO_CLAUSE_MAX, (
        f"{lang}/{key}: {len(two_clause)} of {len(lines)} are "
        f"'clause. clause.'\n" + "\n".join(two_clause))


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("key", CATEGORIES)
def test_a_category_uses_the_whole_range_of_lengths(lang, key):
    """A ceiling nobody approaches and a floor nobody reaches is one length."""
    lengths = sorted(len(line) for line in LINES[lang][key])
    assert lengths[-1] <= MAX_CHARS, f"{lang}/{key}: {lengths[-1]} characters"
    assert lengths[0] <= SHORT_ENOUGH, f"{lang}/{key}: shortest is {lengths[0]}"
    assert lengths[-1] >= LONG_ENOUGH, f"{lang}/{key}: longest is {lengths[-1]}"


@pytest.mark.parametrize("lang", LANGS)
def test_nothing_in_the_table_is_an_emoji(lang):
    found = [line for lines in LINES[lang].values() for line in lines
             if EMOJI.search(line)]
    assert not found, found


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("key", CATEGORIES)
def test_every_line_renders_with_nothing_left_in_braces(lang, key):
    """Substituted for real, the way Brain._pick does it, and then read.

    The sibling check in tests/test_buddy_signals.py compares placeholder names
    against the signal's variables, which catches a name that is wrong. This
    catches what reaches the screen: an unclosed brace, a doubled one, a
    placeholder written `{ name }`, or a category the substitution never covers
    at all.
    """
    variables = _scenario_vars()
    assert key in variables, f"{key} has no scenario to render it with"
    for line in LINES[lang][key]:
        rendered = line
        for name, value in variables[key].items():
            rendered = rendered.replace("{" + name + "}", str(value))
        assert "{" not in rendered and "}" not in rendered, \
            f"{lang}/{key}: {rendered}"
