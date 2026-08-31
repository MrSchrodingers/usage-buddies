"""install.sh must detect the OLD install, never the new one.

The rename sweep once rewrote these strings from claude-usage-* to
usage-buddies-*, which turned the migration into a detector for the install it
had just made: it stopped helping upgraders and started offering to run the
uninstaller against a fresh install. These tests pin both directions.
"""
import os
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INSTALL_SH = REPO / "install.sh"

# What an install made under the old name is actually called on disk.
OLD = {
    ".local/bin/claude-usage-collector.py": "f",
    ".local/bin/claude-usage-tray": "f",
    ".config/systemd/user/claude-usage-collector.timer": "f",
    ".local/share/plasma/plasmoids/org.kde.plasma.claudeusage": "d",
    ".config/autostart/claude-usage-tray.desktop": "f",
}
NEW = {
    ".local/bin/usage-buddies-collector.py": "f",
    ".local/bin/usage-buddies-tray": "f",
    ".config/systemd/user/usage-buddies-collector.timer": "f",
    ".local/share/plasma/plasmoids/org.kde.plasma.usagebuddies": "d",
    ".config/autostart/usage-buddies-tray.desktop": "f",
}

# The harness sources only migrate_legacy_install out of install.sh and points
# REPO_DIR at a throwaway directory holding a STUB legacy/uninstall.sh.
#
# The real uninstaller runs `systemctl --user disable --now` and
# `rm -f /tmp/claude_*.sqlite*`. `systemctl --user` talks to the caller's own
# session manager and ignores HOME, so running it from a test would disable the
# operator's timer and delete files outside tmp_path. A test must not be able to
# do that, however isolated its HOME looks.
HARNESS = r"""
set -uo pipefail
RED=''; GREEN=''; AMBER=''; BLUE=''; BOLD=''; DIM=''; NC=''
REPO_DIR="{repo}"
ok(){{ echo "OK:$1"; }}; warn(){{ echo "WARN:$1|${{2:-}}"; }}; step_desc(){{ echo "STEP:$1"; }}
eval "$(sed -n '/^migrate_legacy_install() {{/,/^}}/p' "{install_sh}")"
migrate_legacy_install
echo "RC=$?"
"""

# Stands in for legacy/uninstall.sh: deletes the same ~/.claude files and the
# same install artifacts, with no systemd or /tmp contact.
STUB_UNINSTALLER = """#!/bin/bash
set -uo pipefail
rm -f "$HOME/.local/bin/claude-usage-collector.py" "$HOME/.local/bin/claude-usage-tray"
rm -f "$HOME/.config/autostart/claude-usage-tray.desktop"
rm -rf "$HOME/.local/share/plasma/plasmoids/org.kde.plasma.claudeusage"
rm -f "$HOME/.config/systemd/user/claude-usage-collector."{timer,service}
for f in widget-data.json widget-config.json widget-status-prev.json; do
    rm -f "$HOME/.claude/$f"
done
echo "stub-uninstaller: done"
STUB_EXIT
"""


def _fake_repo(tmp_path, exit_code=0, die_midway=False):
    """A REPO_DIR whose legacy/uninstall.sh is the stub above."""
    repo = tmp_path / "fake-repo"
    (repo / "legacy").mkdir(parents=True)
    body = STUB_UNINSTALLER
    if die_midway:
        # Delete the config, then fail — the case that loses data if the
        # restore is skipped.
        body = body.replace('echo "stub-uninstaller: done"',
                            'echo "stub-uninstaller: dying after deleting config" >&2')
    body = body.replace("STUB_EXIT", f"exit {exit_code}")
    u = repo / "legacy" / "uninstall.sh"
    u.write_text(body)
    u.chmod(0o755)
    return repo


def _make(home: Path, layout):
    for rel, kind in layout.items():
        p = home / rel
        if kind == "d":
            p.mkdir(parents=True, exist_ok=True)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x")


def _script(repo):
    return HARNESS.format(repo=repo, install_sh=INSTALL_SH)


def _run(home: Path, repo=None):
    """Non-interactive: stdin closed, so the function must warn and return
    without invoking any uninstaller."""
    return subprocess.run(["bash", "-c", _script(repo or REPO)],
                          capture_output=True, text=True,
                          env=dict(os.environ, HOME=str(home)),
                          stdin=subprocess.DEVNULL, timeout=30)


def _run_interactive(home: Path, repo, answer: str = "y\n"):
    """Drive it through a real pty so `[ -t 0 ]` is true and the migration path
    actually executes. Over a pipe it takes the non-interactive branch and the
    uninstaller never runs, which would make these tests pass vacuously."""
    import pty
    import select

    pid, fd = pty.fork()
    if pid == 0:                                    # child
        os.environ["HOME"] = str(home)
        os.execvp("bash", ["bash", "-c", _script(repo)])
    os.write(fd, answer.encode())
    out, deadline = b"", time.monotonic() + 30
    while time.monotonic() < deadline:
        if not select.select([fd], [], [], 1.0)[0]:
            continue
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
    else:                                           # pragma: no cover
        os.kill(pid, 9)
        os.waitpid(pid, 0)
        raise AssertionError(f"migrate_legacy_install did not finish in 30s:\n{out.decode(errors='replace')}")
    os.waitpid(pid, 0)
    return out.decode(errors="replace")


def test_detects_an_old_install(tmp_path):
    _make(tmp_path, OLD)
    r = _run(tmp_path)
    assert "Previous install found" in r.stdout, r.stdout
    for name in ("claude-usage-collector.py", "claude-usage-tray",
                 "claude-usage-collector.timer", "org.kde.plasma.claudeusage"):
        assert name in r.stdout, f"{name} not listed:\n{r.stdout}"
    assert "RC=0" in r.stdout


def test_ignores_a_current_install(tmp_path):
    """A re-run over the new install must be silent. Otherwise the installer
    offers to run legacy/uninstall.sh against the install it just made."""
    _make(tmp_path, NEW)
    r = _run(tmp_path)
    assert "Previous install found" not in r.stdout, (
        "detector fired on the CURRENT install; legacy/uninstall.sh would be "
        f"offered against a fresh install:\n{r.stdout}"
    )
    assert "RC=0" in r.stdout


def test_clean_home_is_silent(tmp_path):
    r = _run(tmp_path)
    assert r.stdout.strip() == "RC=0", r.stdout


def test_install_sh_still_spells_the_old_names(tmp_path):
    """Guard against another rename sweep flattening the detector."""
    body = INSTALL_SH.read_text()
    fn = body[body.index("migrate_legacy_install() {"):]
    fn = fn[:fn.index("\n}\n")]
    for name in ("claude-usage-collector.py", "claude-usage-tray",
                 "claude-usage-collector.timer", "org.kde.plasma.claudeusage",
                 "claude-usage-tray.desktop"):
        assert name in fn, f"migrate_legacy_install lost the old name {name!r}"


def test_migration_actually_runs_the_uninstaller(tmp_path):
    """Guard for the tests below: if the uninstaller never runs, preserving the
    config across it proves nothing."""
    _make(tmp_path, OLD)
    repo = _fake_repo(tmp_path)
    out = _run_interactive(tmp_path, repo)
    assert "non-interactive" not in out, f"took the non-interactive branch:\n{out}"
    assert "stub-uninstaller: done" in out, f"uninstaller did not run:\n{out}"
    assert not (tmp_path / ".local/bin/claude-usage-collector.py").exists(), out


def test_migration_preserves_widget_config(tmp_path):
    """legacy/uninstall.sh deletes widget-config.json — right for an uninstall,
    wrong for a migration: it holds the org id and the notification settings,
    and install.sh never recreates it."""
    _make(tmp_path, OLD)
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)
    cfg = claude / "widget-config.json"
    cfg.write_text('{"org_id":"abc","notifications":{"sounds":{"sessionEnded":"custom"}}}')

    out = _run_interactive(tmp_path, _fake_repo(tmp_path))

    assert cfg.exists(), f"widget-config.json lost during migration:\n{out}"
    body = cfg.read_text()
    assert '"org_id"' in body and '"custom"' in body, f"config rewritten: {body}"


def test_config_survives_an_uninstaller_that_dies_midway(tmp_path):
    """install.sh runs under `set -e`. An uninstaller that deletes the config
    and then fails would abort the script before the restore loop, losing the
    file and orphaning the backup in a temp dir nobody is told about."""
    _make(tmp_path, OLD)
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)
    cfg = claude / "widget-config.json"
    cfg.write_text('{"org_id":"REAL-ORG-ID"}')

    out = _run_interactive(tmp_path, _fake_repo(tmp_path, exit_code=130, die_midway=True))

    assert cfg.exists(), (
        f"widget-config.json lost when the uninstaller failed midway:\n{out}"
    )
    assert '"org_id"' in cfg.read_text()
    assert "RC=0" in out, f"migration should not abort the installer:\n{out}"
    assert "exited 130" in out, f"partial removal not reported to the user:\n{out}"


def test_stub_uninstaller_touches_no_system_state():
    """The real legacy/uninstall.sh calls `systemctl --user` and removes
    /tmp/claude_*.sqlite*. `systemctl --user` ignores HOME and reaches the
    caller's own session manager, so no test may run it — they drive the stub."""
    real = (REPO / "legacy" / "uninstall.sh").read_text()
    assert "systemctl --user" in real, (
        "guard is stale: the real uninstaller no longer calls systemctl, so this "
        "test no longer guards anything"
    )
    for forbidden in ("systemctl", "pkill", "/tmp/"):
        assert forbidden not in STUB_UNINSTALLER, (
            f"the stub uninstaller must not reference {forbidden!r}"
        )
