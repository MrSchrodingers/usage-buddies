import os
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


CENTRAL_SCRIPTS = {
    "claude-hub",
    "ch",
    "claude-hub-gui.py",
    "ai-central-open.py",
    "ai-central-web.py",
    "ai-central-enable-https.sh",
    "ai-hub-state.py",
    "ai-hub-restore.py",
    "ai_hub_registry.py",
    "ai-hub-registry.py",
}


def test_central_installer_and_uninstaller_cover_the_same_commands():
    installer = (REPO / "install-ai-central.sh").read_text(encoding="utf-8")
    uninstaller = (REPO / "uninstall-ai-central.sh").read_text(encoding="utf-8")
    for name in CENTRAL_SCRIPTS:
        assert name in installer
        assert name in uninstaller


def test_systemd_units_do_not_embed_the_developers_home_or_tailnet_ip():
    units = "\n".join(path.read_text(encoding="utf-8") for path in (REPO / "systemd").glob("ai-*.service"))
    assert "/home/ti" not in units
    assert "100.121.129.49" not in units
    assert "%h/.local/bin" in units


def test_web_service_resolves_its_tailnet_address_at_startup():
    unit = (REPO / "systemd" / "ai-central-web.service").read_text(encoding="utf-8")
    server = (REPO / "scripts" / "ai-central-web.py").read_text(encoding="utf-8")
    assert "--host tailscale" in unit
    assert 'if args.host == "tailscale"' in server


def test_hub_unit_exists_before_dependent_units_are_enabled():
    assert (REPO / "systemd" / "claude-hub.service").is_file()
    for name in ("ai-central-web.service", "ai-hub-restore.service"):
        assert "Requires=claude-hub.service" in (REPO / "systemd" / name).read_text(encoding="utf-8")


def test_registry_is_installed_under_import_and_executable_names():
    installer = (REPO / "install-ai-central.sh").read_text(encoding="utf-8")
    assert '"ai-hub-registry.py"' in installer
    assert '"$REPO_DIR/scripts/ai_hub_registry.py" "$BIN_DIR/$script"' in installer


def run_script(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(REPO / name), *args],
        cwd=REPO,
        env={**os.environ, "LC_ALL": "C.UTF-8"},
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )


def test_pc_installer_help_and_dry_run_are_non_mutating_entrypoints():
    help_result = run_script("install-ai-central.sh", "--help")
    assert help_result.returncode == 0
    assert "--auto" in help_result.stdout
    assert "--android" in help_result.stdout

    dry_run = run_script("install-ai-central.sh", "--dry-run", "--auto", "--android")
    assert dry_run.returncode == 0, dry_run.stderr
    assert "Dry-run" in dry_run.stdout
    assert "Android por ADB:    true" in dry_run.stdout


def test_pc_installer_has_transaction_and_enables_one_terminal_by_default():
    installer = (REPO / "install-ai-central.sh").read_text(encoding="utf-8")
    assert "backup_current" in installer
    assert "rollback" in installer
    assert "MUTATION_STARTED" in installer
    assert "COMMITTED=true" in installer
    assert "ENABLE_TERMINAL=true" in installer
    assert "systemctl --user enable --now ai-central-terminal.service" in installer
    assert "loginctl enable-linger" in installer
    assert "python_bin=/usr/bin/python3" in installer


def test_android_installer_uses_verified_isolated_adb_flow():
    installer = (REPO / "install-ai-central-android.sh").read_text(encoding="utf-8")
    result = run_script("install-ai-central-android.sh", "--help")
    assert result.returncode == 0
    assert "--manual" in result.stdout
    assert "--require-boot" in result.stdout
    assert "sha256sum" in installer
    assert "KEYCODE_CTRL_LEFT KEYCODE_ALT_LEFT KEYCODE_C" in installer
    assert "install-result.txt" in installer
    assert "id_ed25519.pub" in installer
    assert "tmux detach-client" in installer
    assert "am startservice" not in installer
    assert "allow-external-apps=true" not in installer
    pc_installer = (REPO / "install-ai-central.sh").read_text(encoding="utf-8")
    assert "$ALWAYS_ON && args+=(--require-boot)" in pc_installer


def test_android_check_validates_an_authorized_device_and_boot_requirement(tmp_path):
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()

    adb = fake_bin / "adb"
    adb.write_text(
        """#!/usr/bin/env bash
if [ "${1:-}" = devices ]; then
  printf 'List of devices attached\\nSERIAL123\\tdevice product:test\\n'
  exit 0
fi
if [ "${1:-}" = -s ] && [ "${3:-}" = shell ] && [ "${4:-}" = pm ] && [ "${5:-}" = path ]; then
  if [ "${6:-}" = com.termux.boot ] && [ "${NO_BOOT:-}" = 1 ]; then exit 0; fi
  printf 'package:/data/app/%s.apk\\n' "${6:-unknown}"
  exit 0
fi
exit 0
""",
        encoding="utf-8",
    )
    adb.chmod(0o755)
    tailscale = fake_bin / "tailscale"
    tailscale.write_text("#!/usr/bin/env bash\necho 100.100.20.30\n", encoding="utf-8")
    tailscale.chmod(0o755)
    ss = fake_bin / "ss"
    ss.write_text("#!/usr/bin/env bash\necho 'LISTEN 0 128 0.0.0.0:22 0.0.0.0:*'\n", encoding="utf-8")
    ss.chmod(0o755)
    env = {**os.environ, "PATH": f"{fake_bin}:/usr/bin:/bin"}

    accepted = subprocess.run(
        [str(REPO / "install-ai-central-android.sh"), "--check", "--require-boot"],
        cwd=REPO,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert accepted.returncode == 0, accepted.stderr
    assert "Pré-validação concluída" in accepted.stdout

    missing_boot = subprocess.run(
        [str(REPO / "install-ai-central-android.sh"), "--check", "--require-boot"],
        cwd=REPO,
        env={**env, "NO_BOOT": "1"},
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert missing_boot.returncode == 4
    assert "Termux:Boot é obrigatório" in missing_boot.stderr


def test_termux_install_is_rollback_capable_and_owns_only_a_marked_config_block():
    installer = (REPO / "mobile" / "install-termux.sh").read_text(encoding="utf-8")
    properties = (REPO / "mobile" / "termux.properties").read_text(encoding="utf-8")
    assert "restore_backup" in installer
    assert "MUTATED=true" in installer
    assert "ssh-keygen" in installer
    assert "ai-central-boot" in installer
    assert properties.count("# BEGIN AI CENTRAL MANAGED SETTINGS") == 1
    assert properties.count("# END AI CENTRAL MANAGED SETTINGS") == 1


def test_android_boot_preflight_never_attaches_a_hidden_tmux_client():
    boot = (REPO / "mobile" / "ai-central-boot").read_text(encoding="utf-8")
    assert "claude-hub init" in boot
    assert "claude-hub mobile" not in boot
    assert "tmux attach" not in boot


def test_pc_installer_restores_previous_files_when_systemd_gate_fails(tmp_path):
    home = tmp_path / "home"
    bin_dir = home / ".local" / "bin"
    fake_bin = tmp_path / "fake-bin"
    bin_dir.mkdir(parents=True)
    fake_bin.mkdir()
    old_ch = bin_dir / "ch"
    old_ch.write_text("previous-install\n", encoding="utf-8")

    def executable(name: str, body: str) -> None:
        path = fake_bin / name
        path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
        path.chmod(0o755)

    executable("tmux", "exit 0\n")
    executable("ssh", "exit 0\n")
    executable("konsole", "exit 0\n")
    executable("tailscale", 'if [ "${1:-}" = ip ]; then echo 100.64.0.1; fi\n')
    executable(
        "systemctl",
        """
if [ "$*" = "--user show-environment" ]; then exit 0; fi
if [[ "$*" == "--user is-enabled"* ]]; then echo disabled; exit 0; fi
if [[ "$*" == "--user is-active"* ]]; then echo inactive; exit 0; fi
if [[ "$*" == "--user enable --now"* ]]; then exit 42; fi
exit 0
""",
    )

    result = subprocess.run(
        [str(REPO / "install-ai-central.sh")],
        cwd=REPO,
        env={
            **os.environ,
            "HOME": str(home),
            "USER": "installer-test",
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "PYTHONPATH": os.pathsep.join(sys.path),
        },
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 42
    assert old_ch.read_text(encoding="utf-8") == "previous-install\n"
    assert not (bin_dir / "claude-hub").exists()
    assert "Rollback concluído" in result.stderr
    assert list((home / ".local" / "state" / "ai-central" / "backups").iterdir())
