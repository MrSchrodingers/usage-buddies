"""Sanity tests for browser path resolution in the collector.

These assertions guard the Linux path list against accidental regression —
specifically the Snap and Flatpak entries that Ubuntu users depend on.
"""
from pathlib import Path

COLLECTOR = Path(__file__).resolve().parents[1] / "scripts" / "usage-buddies-collector.py"


def test_firefox_linux_paths_present():
    content = COLLECTOR.read_text()
    for fragment in [
        '.mozilla" / "firefox"',
        'snap" / "firefox" / "common" / ".mozilla" / "firefox"',
        '.var" / "app" / "org.mozilla.firefox" / ".mozilla" / "firefox"',
    ]:
        assert fragment in content, f"Missing Firefox path fragment: {fragment}"


def test_chrome_linux_paths_present():
    content = COLLECTOR.read_text()
    for fragment in [
        '.config" / "google-chrome"',
        '.config" / "chromium"',
        'snap" / "chromium" / "common" / "chromium"',
        '.var" / "app" / "com.google.Chrome" / "config" / "google-chrome"',
        '.var" / "app" / "org.chromium.Chromium" / "config" / "chromium"',
    ]:
        assert fragment in content, f"Missing Chrome path fragment: {fragment}"


def test_health_check_mentions_firefox_snap():
    """Task 4 introduces a Snap-specific advice path in --health-check."""
    content = COLLECTOR.read_text()
    assert "Firefox Snap" in content, (
        "Health check should mention 'Firefox Snap' explicitly when the Snap profile "
        "is detected without a valid sessionKey cookie."
    )
