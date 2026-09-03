from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def test_shared_tui_uses_smallest_attached_client_grid():
    source = (REPO / "scripts" / "claude-hub").read_text(encoding="utf-8")
    assert "tmux set-option -g window-size smallest" in source


def test_termux_has_a_native_keyboard_recovery_key():
    properties = (REPO / "mobile" / "termux.properties").read_text(encoding="utf-8")
    assert "key:'KEYBOARD'" in properties
    assert "display:'TECLA'" in properties
