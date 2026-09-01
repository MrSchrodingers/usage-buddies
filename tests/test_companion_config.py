"""The widget and the companion agree on a command line and a command file.

They are two processes with no shared code. Every setting crosses between them
as a flag spelled out in a QML string and parsed by an argparse call in another
language, and every mismatch there fails the same quiet way: the flag is either
rejected at startup, so the companion never appears, or accepted and ignored,
so the option in the dialog does nothing at all. Neither leaves a message where
anybody looks.

Three separate ways to end up with a dead option, all of them silent:

  - an entry declared in main.xml that nothing in main.qml ever reads;
  - a flag emitted with a spelling the Python side does not parse;
  - a setting that reaches the command line but has no onXChanged handler, so
    it only takes effect the next time the widget is reloaded.

The fourth thing checked here is not a spelling but a decision: the default of
buddyInsistence must not be the step that takes the mouse cursor away from the
person using it. That one is worth a test because it is a one-word change that
reviews well and is only noticed in use.
"""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
QML = REPO / "plasmoid" / "contents" / "ui" / "main.qml"
CONFIG_QML = REPO / "plasmoid" / "contents" / "ui" / "configGeneral.qml"
KCFG = REPO / "plasmoid" / "contents" / "config" / "main.xml"

# The contract, written once. Both sides are checked against this list rather
# than against each other, so neither can drift by agreeing with itself.
COMPANION_FLAGS = {
    "--codex", "--pt", "--alerts-only", "--live",
    "--focus-minutes", "--insistence", "--quiet-hours", "--memes",
    "--no-shadow", "--escort",
}

# Settings added for the focus/insistence work. Each has to be readable, on the
# command line, wired to a change handler and present on the config page.
NEW_ENTRIES = (
    "buddyFocusMinutes", "buddyInsistence", "buddyQuietHours",
    "buddyMemes", "buddyShadow", "buddyEscort",
)

INSISTENCE_LADDER = ["off", "speak", "walk", "wave", "pointer"]


def _entries():
    """Every entry in main.xml, name to default, namespace-insensitive."""
    root = ET.parse(KCFG).getroot()
    out = {}
    for entry in root.iter():
        if not entry.tag.endswith("entry"):
            continue
        name = entry.get("name")
        default = ""
        for child in entry:
            if child.tag.endswith("default"):
                default = (child.text or "").strip()
        out[name] = default
    return out


def _function_body(text, name):
    """The braced body of a QML function, matched by counting braces.

    Anchoring on indentation would silently miss a one-line handler, which is
    how the same class of check has passed while watching nothing before.
    """
    at = text.find("function %s(" % name)
    assert at != -1, "function %s not found" % name
    start = text.find("{", at)
    depth, i = 1, start + 1
    while i < len(text) and depth:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return text[start + 1:i - 1]


def test_the_parsers_find_what_this_file_watches():
    """A check on an empty set passes. Prove both instruments see the real
    file before believing anything they report."""
    entries = _entries()
    assert set(entries) >= set(NEW_ENTRIES), sorted(entries)
    body = _function_body(QML.read_text(), "syncCompanion")
    assert "companion-ctl.sh" in body, "syncCompanion no longer builds the ctl line"


@pytest.mark.parametrize("name", sorted(_entries()))
def test_every_declared_entry_is_read_by_the_widget(name):
    """A setting nobody reads is an option on the user's screen that does
    nothing when they change it, and there is no warning anywhere that it is
    inert — the dialog looks exactly the same as a working one."""
    assert "Plasmoid.configuration.%s" % name in QML.read_text(), (
        "%s is declared in main.xml but never read in main.qml" % name
    )


def test_sync_companion_emits_only_contracted_flags():
    """The Python side parses these names literally. An abbreviation or a
    plural invented here is rejected by argparse, and the companion exits
    before it draws anything."""
    body = _function_body(QML.read_text(), "syncCompanion")
    emitted = set(re.findall(r"--[a-z][a-z-]*", body))
    assert emitted <= COMPANION_FLAGS, (
        "flags not in the contract: %s" % sorted(emitted - COMPANION_FLAGS)
    )


@pytest.mark.parametrize("flag", sorted(COMPANION_FLAGS))
def test_every_contracted_flag_is_actually_emitted(flag):
    body = _function_body(QML.read_text(), "syncCompanion")
    assert flag in body, "%s is in the contract but never reaches the command line" % flag


@pytest.mark.parametrize("name", NEW_ENTRIES)
def test_every_new_setting_reaches_the_command_line(name):
    """Reading the setting is not enough: it has to be on the line the
    companion is started with."""
    body = _function_body(QML.read_text(), "syncCompanion")
    assert name in body, "%s is read but never passed to the companion" % name


@pytest.mark.parametrize("name", NEW_ENTRIES)
def test_changing_a_setting_restarts_the_companion(name):
    """The companion reads its flags once, at startup. Without a handler the
    user changes the option, nothing happens, and it stays wrong until the
    widget is reloaded — the kind of defect that is abandoned rather than
    reported."""
    handler = "on%s%sChanged" % (name[0].upper(), name[1:])
    src = QML.read_text()
    at = src.find(handler)
    assert at != -1, "%s has no %s handler" % (name, handler)
    assert "syncCompanion" in src[at:at + 200], (
        "%s exists but does not resync the companion" % handler
    )


def test_insistence_default_is_not_the_pointer_step():
    """The last rung of the ladder moves the user's mouse cursor. That is a
    thing to opt into, never a thing an installation inherits from a default
    someone raised because the ladder looked incomplete."""
    default = _entries()["buddyInsistence"]
    assert default != "pointer", (
        "buddyInsistence defaults to the step that seizes the mouse pointer"
    )
    assert default in INSISTENCE_LADDER, default
    assert default == "walk", "the documented default is walk, found %r" % default


def test_the_widget_clamps_insistence_to_the_ladder():
    """The value is interpolated into a shell command line, and the config is
    a text file on disk. Anything outside the ladder has to fall back rather
    than travel."""
    src = QML.read_text()
    at = src.find("property string buddyInsistence")
    assert at != -1
    window = src[at:at + 400]
    for step in INSISTENCE_LADDER:
        assert '"%s"' % step in window, "%s missing from the clamp list" % step


@pytest.mark.parametrize("name", NEW_ENTRIES)
def test_the_config_page_exposes_every_new_entry(name):
    """KCM binds a control to `cfg_<name>`. Without the property the entry
    exists in the config file and nowhere in the dialog."""
    assert re.search(r"property \w+ cfg_%s\b" % name, CONFIG_QML.read_text()), (
        "configGeneral.qml has no cfg_%s" % name
    )


def test_the_pointer_step_is_labelled_as_moving_the_cursor():
    """Nobody should learn what this does by watching it happen.

    Read from the branch that fires on the pointer value, not from the file as
    a whole: an earlier version of this check searched the whole page, and the
    word "cursor" anywhere in it — including in an unrelated line — satisfied
    it while the option itself said nothing."""
    src = CONFIG_QML.read_text()
    assert '"pointer"' in src, "the ladder does not offer the pointer step"
    branch = re.search(r'=== "pointer"\s*\?\s*"(.*?)"\s*:', src, re.S)
    assert branch, "no text on the page depends on the pointer step"
    assert re.search(r"(?i)(mouse|cursor)", branch.group(1)), (
        "the pointer step is offered with no mention of the cursor it takes"
    )


# ── the command file ───────────────────────────────────────────────────────
#
# Starting a focus session cannot go through the command line: the flags are
# read once, so it would mean restarting the companion and losing its state.
# It goes through a file the companion watches.


def test_the_command_file_is_the_agreed_path():
    body = _function_body(QML.read_text(), "sendCompanionCommand")
    assert "usage-buddies" in body and "companion-command.json" in body, body


def test_the_command_file_is_written_atomically():
    """A watcher wakes on the first write. Written in place, it reads a
    truncated file, discards it, and the command is lost with no trace on
    either side. Rename within one filesystem is atomic."""
    body = _function_body(QML.read_text(), "sendCompanionCommand")
    assert "mktemp" in body, "no temporary file: the reader can see a partial write"
    assert re.search(r'"mv ', body), "the temporary file is never renamed into place"


def test_the_temporary_file_shares_the_target_directory():
    """A rename across filesystems is a copy, and a copy is not atomic. The
    temporary has to be beside the file it replaces, not in /tmp."""
    body = _function_body(QML.read_text(), "sendCompanionCommand")
    mktemp = re.search(r"mktemp \" \+ (\w+)", body)
    assert mktemp, "cannot tell where the temporary file is created"
    assert mktemp.group(1) == "dir", (
        "the temporary is not created in the target directory"
    )


def test_every_command_carries_a_timestamp():
    """Without it the file is an order that stands forever: the companion
    reads it while starting up, and a restart the next morning re-enters the
    focus session asked for yesterday."""
    body = _function_body(QML.read_text(), "sendCompanionCommand")
    assert "issuedAt" in body, "commands are written with no issuedAt"
    assert "toISOString" in body, "issuedAt is not an ISO 8601 timestamp"


def test_the_focus_control_sends_both_commands():
    body = _function_body(QML.read_text(), "toggleFocusSession")
    assert "focus.start" in body and "focus.stop" in body, (
        "the focus control cannot both start and end a session"
    )
    assert "minutes" in body, "focus.start carries no duration"


def test_the_focus_control_is_hidden_with_the_companion_off():
    """It writes a command file for a process that is not running: a control
    that looks live and does nothing."""
    src = QML.read_text()
    at = src.find("id: focusBtn")
    assert at != -1, "no focus button in the header"
    block = src[at:at + 400]
    assert re.search(r'visible:\s*root\.buddyMode !== "off"', block), (
        "the focus button is not gated on the companion being on"
    )


def test_the_command_payload_is_shell_quoted():
    """The JSON goes onto a shell command line. Unquoted, a value containing a
    quote or a semicolon stops being data."""
    body = _function_body(QML.read_text(), "sendCompanionCommand")
    assert "shellQuote(" in body, "the payload reaches the shell unquoted"
