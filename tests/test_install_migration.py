"""install.sh must detect the OLD install, never the new one.

The rename sweep once rewrote these strings from claude-usage-* to
usage-buddies-*, which turned the migration into a detector for the install it
had just made: it stopped helping upgraders and started offering to run the
uninstaller against a fresh install. These tests pin both directions.
"""
import os
import subprocess
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

HARNESS = r'''
set -uo pipefail
RED=''; GREEN=''; AMBER=''; BLUE=''; BOLD=''; DIM=''; NC=''
REPO_DIR="{repo}"
ok(){{ echo "OK:$1"; }}; warn(){{ echo "WARN:$1"; }}; step_desc(){{ echo "STEP:$1"; }}
eval "$(sed -n '/^migrate_legacy_install() {{/,/^}}/p' "$REPO_DIR/install.sh")"
migrate_legacy_install
echo "RC=$?"
'''


def _make(home: Path, layout):
    for rel, kind in layout.items():
        p = home / rel
        if kind == "d":
            p.mkdir(parents=True, exist_ok=True)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x")


def _run(home: Path):
    script = HARNESS.format(repo=REPO)
    env = dict(os.environ, HOME=str(home))
    # stdin closed: the function must take the non-interactive branch and never
    # invoke the uninstaller from a test.
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                          env=env, stdin=subprocess.DEVNULL)


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


def _run_interactive(home: Path, answer: str = "y\n"):
    """Run the function with a real pty so `[ -t 0 ]` is true and the migration
    path actually executes. With a pipe it takes the non-interactive branch and
    the uninstaller never runs — the test would pass without testing anything."""
    import pty

    script = HARNESS.format(repo=REPO)
    pid, fd = pty.fork()
    if pid == 0:                                    # child
        os.environ["HOME"] = str(home)
        os.execvp("bash", ["bash", "-c", script])
    os.write(fd, answer.encode())
    out = b""
    while True:
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
    os.waitpid(pid, 0)
    return out.decode(errors="replace")


def test_migration_actually_runs_the_uninstaller(tmp_path):
    """Guard for the test below: if the uninstaller never runs, preserving the
    config proves nothing."""
    _make(tmp_path, OLD)
    out = _run_interactive(tmp_path)
    assert "non-interactive" not in out, f"took the non-interactive branch:\n{out}"
    assert not (tmp_path / ".local/bin/claude-usage-collector.py").exists(), (
        f"old collector still present, uninstaller did not run:\n{out}"
    )


def test_migration_preserves_widget_config(tmp_path):
    """legacy/uninstall.sh deletes widget-config.json — right for an uninstall,
    wrong for a migration: it holds the org id and the notification settings,
    and install.sh never recreates it."""
    _make(tmp_path, OLD)
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)
    cfg = claude / "widget-config.json"
    cfg.write_text('{"org_id":"abc","notifications":{"sounds":{"sessionEnded":"custom"}}}')

    out = _run_interactive(tmp_path)

    assert cfg.exists(), f"widget-config.json lost during migration:\n{out}"
    body = cfg.read_text()
    assert '"org_id"' in body and '"custom"' in body, (
        f"config survived but was rewritten: {body}"
    )
