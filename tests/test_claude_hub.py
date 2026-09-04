from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def test_shared_tui_follows_the_client_being_used():
    source = (REPO / "scripts" / "claude-hub").read_text(encoding="utf-8")
    assert "tmux set-option -g window-size latest" in source
    assert "tmux set-option -g window-size smallest" not in source


def test_termux_has_a_native_keyboard_recovery_key():
    properties = (REPO / "mobile" / "termux.properties").read_text(encoding="utf-8")
    assert "key:'KEYBOARD'" in properties
    assert "display:'TECLA'" in properties


def test_mobile_ssh_fails_fast_instead_of_leaving_a_dead_menu():
    config = (REPO / "mobile" / "ssh-config.template").read_text(encoding="utf-8")
    assert "ServerAliveInterval 5" in config
    assert "ServerAliveCountMax 2" in config
    assert "ConnectTimeout 5" in config
    assert "ConnectionAttempts 1" in config


def test_mobile_shortcut_uses_its_isolated_managed_ssh_config():
    shortcut = (REPO / "mobile" / "PC-Hub").read_text(encoding="utf-8")
    assert 'ssh -F "$SSH_CONFIG" pc-hub' in shortcut
    assert "Conexao interrompida" in shortcut
    assert "wake_tailscale" in shortcut
