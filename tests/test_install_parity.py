"""Whatever the installer copies out of scripts/, the uninstaller takes back.

The companion's modules are listed in two places — a copy instruction in
install.sh and a path in the uninstaller's removal loop — and nothing tied the
two together. Four library modules were being installed and never removed, so
uninstalling left buddy_sprites.py, repo_brief.py, buddy_voice.py and
virtual_pointer.py behind. Nothing raises: the next install overwrites them and
the leftovers stay invisible until someone wonders why a removed program still
has files on disk.

Scope is deliberately the scripts/ tree. The tray binary is compiled rather than
copied and the plasmoid is removed by directory, so holding either to a
per-file list would assert against something that was never meant to be one.
Both sides are filtered through the same set of real filenames, so a module that
does not exist yet is invisible to this file rather than half-visible.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

SCRIPTS = {p.name for p in (REPO / "scripts").iterdir() if p.is_file()}

# Three spellings are in use, and a parser that knows only one reports a clean
# sweep while watching a third of the file:
#   cp "$REPO_DIR/scripts/name.py" "$HOME/.local/bin/"
#   cp "$REPO_DIR/scripts/name.py" "$COLLECTOR"        (variable destination)
#   for f in a.py b.sh; do cp "$REPO_DIR/scripts/$f" "$HOME/.local/bin/"
BIN_VAR = re.compile(r'^(\w+)="\$HOME/\.local/bin/([\w.-]+)"')
DIRECT = re.compile(r'cp\s+"\$REPO_DIR/scripts/([\w.-]+)"\s+"(?:\$HOME/\.local/bin/|\$(\w+)")')
LOOP = re.compile(r'^\s*for\s+\w+\s+in\s+([^;]+);\s*do\s*$')


def _installed_names():
    lines = (REPO / "install.sh").read_text().splitlines()
    bin_vars, names, pending = {}, set(), []
    for line in lines:
        if line.lstrip().startswith("#"):
            continue
        var = BIN_VAR.match(line)
        if var:
            bin_vars[var.group(1)] = var.group(2)
        for name, dest_var in DIRECT.findall(line):
            # A copy into a variable only counts when that variable is known to
            # point inside ~/.local/bin; otherwise this would count the plasmoid.
            if not dest_var or dest_var in bin_vars:
                names.add(name)
        loop = LOOP.match(line)
        if loop:
            pending = [w for w in loop.group(1).split() if w in SCRIPTS]
        elif pending and '"$REPO_DIR/scripts/$' in line and '.local/bin/' in line:
            names.update(pending)
            pending = []
    return names & SCRIPTS


def _removed_names():
    text = (REPO / "uninstall.sh").read_text()
    return set(re.findall(r'\$HOME/\.local/bin/([\w.-]+)', text)) & SCRIPTS


def test_the_parser_finds_all_three_copy_forms():
    """Every spelling has to be seen, or the assertions below pass while
    watching only the part of the file the pattern happened to match."""
    installed = _installed_names()
    assert "buddy_sprites.py" in installed, "the direct cp form went unseen"
    assert "sessions-probe.py" in installed, "the for-loop form went unseen"
    assert "usage-buddies-collector.py" in installed, "the variable form went unseen"


def test_every_installed_script_is_removed_by_the_uninstaller():
    installed, removed = _installed_names(), _removed_names()
    assert not (installed - removed), \
        f"installed but never removed: {sorted(installed - removed)}"


def test_the_uninstaller_does_not_chase_a_file_the_installer_stopped_copying():
    """A path in the removal loop that the installer no longer writes is a
    rename that only got done on one side, which means the file really on disk
    is the one nobody deletes."""
    installed, removed = _installed_names(), _removed_names()
    assert not (removed - installed), \
        f"removed but never installed: {sorted(removed - installed)}"
