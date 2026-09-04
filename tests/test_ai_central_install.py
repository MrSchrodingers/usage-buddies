from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


CENTRAL_SCRIPTS = {
    "claude-hub",
    "claude-hub-gui.py",
    "ai-central-open.py",
    "ai-central-web.py",
    "ai-central-enable-https.sh",
    "ai-hub-state.py",
    "ai-hub-restore.py",
    "ai_hub_registry.py",
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
