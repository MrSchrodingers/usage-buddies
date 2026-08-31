"""Windows support must survive the PySide6 -> Tauri rebuild.

PR #8 swapped the Windows *UI*, but the data-acquisition and notification
layers stayed in this Python collector. These tests pin the Windows branches
that were removed alongside the old UI: the collector is the only thing that
can read cookies or raise a toast on Windows, and win-widget does neither.
"""
import os


def _force_windows(monkeypatch, collector, home):
    monkeypatch.setattr(collector.platform, "system", lambda: "Windows")
    monkeypatch.setattr(collector.Path, "home", staticmethod(lambda: home))
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))


def test_firefox_profile_found_on_windows(collector, monkeypatch, tmp_path):
    """%APPDATA%\\Mozilla\\Firefox\\Profiles is the only automatic cookie source
    on Windows: Chrome/Edge use App-Bound Encryption, which the collector never
    decrypted (it only ever handled v10/v11 DPAPI blobs)."""
    import platform as _p
    profiles = tmp_path / "AppData" / "Roaming" / "Mozilla" / "Firefox" / "Profiles"
    profiles.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.setattr(_p, "system", lambda: "Windows")
    monkeypatch.setattr(collector.Path, "home", staticmethod(lambda: tmp_path))

    seen = []
    real_exists = collector.Path.exists

    def spy_exists(self):
        seen.append(str(self))
        return real_exists(self)

    monkeypatch.setattr(collector.Path, "exists", spy_exists)
    collector._get_firefox_cookies()

    assert any("Roaming" in p and "Firefox" in p and "Profiles" in p for p in seen), (
        "collector never probed the Windows Firefox profile directory; "
        f"probed instead: {seen}"
    )


def test_notify_desktop_raises_toast_on_windows(collector, monkeypatch):
    """_notify_desktop must not return silently on Windows."""
    import platform as _p
    monkeypatch.setattr(_p, "system", lambda: "Windows")

    import subprocess as _sp
    launched = []
    monkeypatch.setattr(_sp, "Popen",
                        lambda cmd, **kw: launched.append(cmd) or None)

    collector._notify_desktop("titulo", "corpo", "normal")

    assert launched, "no subprocess launched: the Windows toast is a silent no-op"
    assert "powershell" in launched[0][0].lower()
    assert any("ShowBalloonTip" in str(a) for a in launched[0])


def test_play_event_sound_accepts_win_sound(collector, monkeypatch):
    """The sounds.<event>Win config keys must still reach PowerShell."""
    import platform as _p
    monkeypatch.setattr(_p, "system", lambda: "Windows")

    import subprocess as _sp
    launched = []
    monkeypatch.setattr(_sp, "Popen",
                        lambda cmd, **kw: launched.append(cmd) or None)

    collector._play_event_sound("dialog-warning", win_sound="Exclamation")

    assert launched, "no subprocess launched for the Windows sound"
    assert any("Exclamation" in str(a) for a in launched[0]), (
        f"win_sound not forwarded to PowerShell: {launched[0]}"
    )


def test_event_defaults_carry_win_sound(collector):
    """Every usage event keeps a Windows SystemSounds equivalent."""
    for event, cfg in collector.USAGE_EVENT_DEFAULTS.items():
        assert cfg.get("winSound"), f"{event} lost its winSound default"


def test_health_check_probes_windows_firefox(collector):
    """run_health_check must look where Firefox actually lives on Windows,
    otherwise it reports 'no browser profile' to a logged-in user."""
    src = collector.__file__
    import inspect
    body = inspect.getsource(collector.run_health_check)
    assert 'APPDATA' in body and 'Firefox' in body, (
        "health check has no Windows Firefox path; it will misreport on Windows"
    )
