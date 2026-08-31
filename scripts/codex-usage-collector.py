#!/usr/bin/env python3
"""Codex counterpart of claude-usage-collector.py.

Writes ~/.codex/widget-data.json in the same shape the plasmoid already reads
for Claude, from two sources: the local Codex CLI session log
(~/.codex/sessions/**.jsonl) and, when a Chromium profile is signed in, the
ChatGPT usage endpoints. It never reads ~/.codex/auth.json.
"""

from __future__ import annotations

import json
import os
import hashlib
import shutil
import sqlite3
import subprocess
import tempfile
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

CODEX_HOME = Path.home() / ".codex"
SESSIONS_DIR = CODEX_HOME / "sessions"
# Mirrors the Claude collector's contract (~/.claude/widget-data.json) so the
# plasmoid only has to swap a path when the provider changes.
DATA_DIR = CODEX_HOME
OUTPUT_FILE = DATA_DIR / "widget-data.json"
USAGE_ENDPOINTS = {
    "usage": "https://chatgpt.com/backend-api/wham/usage",
    "resetCredits": "https://chatgpt.com/backend-api/wham/rate-limit-reset-credits",
    "limitsConfig": "https://chatgpt.com/backend-api/pageConfigs/usage_limits",
}


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def token_total(usage: dict[str, Any]) -> int:
    return int(usage.get("total_tokens", 0) or 0)


def _chrome_key(browser_dir: Path) -> bytes:
    """Return Chrome's Linux cookie key, with its documented basic fallback."""
    secret = ""
    candidates = [
        ["secret-tool", "lookup", "xdg:schema", "chrome_libsecret_os_crypt_password_v2", "application", "chrome"],
        ["kwallet-query", "-r", "Chrome Safe Storage", "-f", "Chrome Keys", "kdewallet"],
        ["kwallet-query", "-r", "Brave Safe Storage", "-f", "Brave Keys", "kdewallet"],
    ]
    for command in candidates:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=3)
            if result.returncode == 0 and result.stdout.strip():
                secret = result.stdout.strip()
                break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    # Chrome's Linux fallback is intentionally used if no desktop keyring entry
    # is available. It is also retried below when a configured key fails.
    return hashlib.pbkdf2_hmac("sha1", (secret or "peanuts").encode(), b"saltysalt", 1, 16)


def _decrypt_chrome_cookie(value: bytes, key: bytes) -> str | None:
    if not value or value[:3] not in (b"v10", b"v11"):
        return None
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.padding import PKCS7
        decryptor = Cipher(algorithms.AES128(key), modes.CBC(b" " * 16)).decryptor()
        padded = decryptor.update(value[3:]) + decryptor.finalize()
        unpadder = PKCS7(128).unpadder()
        clear = unpadder.update(padded) + unpadder.finalize()
        for candidate in (clear[32:], clear):  # Chrome 130+ prefixes an integrity hash.
            try:
                return candidate.decode("utf-8")
            except UnicodeDecodeError:
                pass
    except Exception:
        return None
    return None


def browser_cookies() -> str:
    """Read ChatGPT cookies from Chromium-family profiles without persisting them."""
    browser_dirs = [
        Path.home() / ".config" / "google-chrome",
        Path.home() / ".config" / "chromium",
        Path.home() / ".config" / "BraveSoftware" / "Brave-Browser",
    ]
    for browser_dir in browser_dirs:
        if not browser_dir.exists():
            continue
        key = _chrome_key(browser_dir)
        fallback_key = hashlib.pbkdf2_hmac("sha1", b"peanuts", b"saltysalt", 1, 16)
        for profile in browser_dir.iterdir():
            cookie_db = profile / "Network" / "Cookies"
            if not cookie_db.exists():
                cookie_db = profile / "Cookies"
            if not cookie_db.exists():
                continue
            temporary = Path(tempfile.mkstemp(prefix="codex-usage-cookies-", suffix=".sqlite")[1])
            try:
                shutil.copy2(cookie_db, temporary)
                for suffix in ("-wal", "-shm"):
                    source = Path(str(cookie_db) + suffix)
                    if source.exists():
                        shutil.copy2(source, Path(str(temporary) + suffix))
                with sqlite3.connect(temporary) as database:
                    rows = database.execute(
                        "SELECT name, value, encrypted_value FROM cookies "
                        "WHERE host_key LIKE '%chatgpt.com%' OR host_key LIKE '%openai.com%'"
                    ).fetchall()
                pairs = []
                for name, plain, encrypted in rows:
                    decoded = plain or _decrypt_chrome_cookie(encrypted, key)
                    if not decoded and key != fallback_key:
                        decoded = _decrypt_chrome_cookie(encrypted, fallback_key)
                    if decoded:
                        pairs.append(f"{name}={decoded}")
                if pairs:
                    return "; ".join(pairs)
            except (OSError, sqlite3.Error):
                continue
            finally:
                for suffix in ("", "-wal", "-shm"):
                    Path(str(temporary) + suffix).unlink(missing_ok=True)
    return ""


def fetch_authenticated_usage() -> tuple[dict[str, Any], dict[str, str]]:
    """Fetch the user-requested ChatGPT usage views, returning safe errors only."""
    cookies = browser_cookies()
    if not cookies:
        return {}, {"authentication": "No ChatGPT browser session found"}
    results: dict[str, Any] = {}
    errors: dict[str, str] = {}
    common_headers = {
        "Cookie": cookies,
        "Accept": "application/json",
        "Origin": "https://chatgpt.com",
        "Referer": "https://chatgpt.com/",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    }
    # The browser session cookie establishes the session; backend routes also
    # expect the short-lived access token that ChatGPT obtains from this route.
    access_token = ""
    try:
        session_request = urllib.request.Request("https://chatgpt.com/api/auth/session", headers=common_headers)
        with urllib.request.urlopen(session_request, timeout=12) as response:
            session = json.loads(response.read().decode("utf-8"))
            access_token = session.get("accessToken", session.get("access_token", ""))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        errors["authentication"] = type(error).__name__
    for name, url in USAGE_ENDPOINTS.items():
        headers = dict(common_headers)
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                results[name] = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            errors[name] = f"HTTP {error.code}"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            errors[name] = type(error).__name__
    return results, errors


def find_rate_limit_blocks(value: Any) -> list[dict[str, Any]]:
    """Locate API objects that look like a Codex 5h/weekly rate-limit window."""
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        keys = set(value)
        if ("used_percent" in keys and ("window_minutes" in keys or "limit_window_seconds" in keys)) or ("usedPercent" in keys and "windowMinutes" in keys):
            found.append(value)
        for child in value.values():
            found.extend(find_rate_limit_blocks(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(find_rate_limit_blocks(child))
    return found


def normalize_api_block(block: dict[str, Any], now: datetime) -> dict[str, Any]:
    raw = {
        "used_percent": block.get("used_percent", block.get("usedPercent", 0)),
        "window_minutes": block.get("window_minutes", block.get("windowMinutes", (block.get("limit_window_seconds", 0) or 0) / 60)),
        "resets_at": block.get("resets_at", block.get("resetsAt", block.get("reset_at", block.get("resetAt")))),
    }
    if isinstance(raw["resets_at"], str):
        reset = parse_time(raw["resets_at"])
        if reset:
            raw["resets_at"] = reset.timestamp()
    return rate_block(raw, now) or {}


def rate_block(snapshot: dict[str, Any] | None, now: datetime) -> dict[str, Any] | None:
    if not snapshot:
        return None
    resets_at = snapshot.get("resets_at")
    reset = None
    if isinstance(resets_at, (int, float)):
        reset = datetime.fromtimestamp(resets_at, tz=timezone.utc)
    used = float(snapshot.get("used_percent", 0) or 0)
    # Codex emits a fraction today, but tolerate a future percentage format.
    if used <= 1:
        used *= 100
    return {
        "percentUsed": max(0, min(100, used)),
        "windowMinutes": int(snapshot.get("window_minutes", 0) or 0),
        "resetsAt": reset.isoformat().replace("+00:00", "Z") if reset else "",
        "resetsInSeconds": max(0, int((reset - now).total_seconds())) if reset else 0,
    }


def collect() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=7)
    daily = defaultdict(lambda: {"tokens": 0, "turns": 0})
    latest: tuple[datetime, dict[str, Any]] | None = None
    sessions: set[str] = set()
    turns = 0
    tokens = 0

    if SESSIONS_DIR.exists():
        for path in SESSIONS_DIR.rglob("*.jsonl"):
            try:
                if datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc) < cutoff:
                    continue
                with path.open(encoding="utf-8") as source:
                    for line in source:
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        timestamp = parse_time(record.get("timestamp"))
                        if not timestamp:
                            continue
                        payload = record.get("payload", {})
                        if record.get("type") == "session_meta":
                            session_id = payload.get("session_id") or payload.get("id")
                            if session_id and timestamp >= cutoff:
                                sessions.add(str(session_id))
                        if record.get("type") != "event_msg":
                            continue
                        # Current Codex logs token counts directly in the event
                        # payload. Older logs can wrap the same object in item.
                        item = payload if payload.get("type") == "token_count" else payload.get("item", {})
                        if item.get("type") != "token_count":
                            continue
                        info = item.get("info", {})
                        limits = item.get("rate_limits", {})
                        if latest is None or timestamp > latest[0]:
                            latest = (timestamp, {"info": info, "limits": limits})
                        if timestamp >= cutoff:
                            usage = info.get("last_token_usage", {})
                            amount = token_total(usage)
                            key = timestamp.astimezone().strftime("%a")
                            daily[key]["tokens"] += amount
                            daily[key]["turns"] += 1
                            tokens += amount
                            turns += 1
            except OSError:
                continue

    days = []
    for offset in range(6, -1, -1):
        day = (now - timedelta(days=offset)).astimezone()
        key = day.strftime("%a")
        days.append({"label": day.strftime("%a"), **daily[key]})

    latest_info = latest[1]["info"] if latest else {}
    latest_limits = latest[1]["limits"] if latest else {}
    remote, remote_errors = fetch_authenticated_usage()
    remote_usage = remote.get("usage", {})
    remote_blocks = find_rate_limit_blocks(remote_usage.get("rate_limit", {}))
    normalized = [normalize_api_block(block, now) for block in remote_blocks]
    normalized = [block for block in normalized if block.get("windowMinutes")]
    # Usage currently exposes a short rolling window and a seven-day window.
    # Choose by duration instead of relying on an undocumented response shape.
    remote_session = min(normalized, key=lambda block: block["windowMinutes"], default=None)
    remote_weekly = max(normalized, key=lambda block: block["windowMinutes"], default=None)
    local_session = rate_block(latest_limits.get("primary"), now)
    local_weekly = rate_block(latest_limits.get("secondary"), now)
    session = remote_session or local_session or {}
    weekly = remote_weekly or local_weekly or {}
    credits = remote_usage.get("credits") or latest_limits.get("credits", {})
    def widget_window(block: dict[str, Any]) -> dict[str, Any]:
        reset = parse_time(block.get("resetsAt"))
        return {
            "percentUsed": block.get("percentUsed", 0),
            "resetsAt": block.get("resetsAt", ""),
            "resetsInMinutes": max(0, int(block.get("resetsInSeconds", 0) / 60)),
            "resetsLabel": reset.astimezone().strftime("%a %H:%M") if reset else "",
        }
    result = {
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "source": "ChatGPT browser session" if remote_session else "local Codex session log",
        "available": latest is not None or remote_session is not None,
        "rateLimits": {
            "session": session,
            "weekly": weekly,
            "plan": remote_usage.get("plan_type") or latest_limits.get("plan_type", ""),
            "credits": credits,
        },
        "browserApi": {
            "available": bool(remote),
            "endpoints": {name: ("ok" if name in remote else remote_errors.get(name, "unavailable")) for name in USAGE_ENDPOINTS},
            # Keep the widget data non-sensitive while making API-shape changes diagnosable.
            "responseKeys": {name: sorted(value.keys()) if isinstance(value, dict) else [] for name, value in remote.items()},
        },
        "account": {
            "allowed": remote_usage.get("rate_limit", {}).get("allowed"),
            "limitReached": remote_usage.get("rate_limit", {}).get("limit_reached"),
            "limitReachedType": remote_usage.get("rate_limit_reached_type"),
            "spendControlReached": remote_usage.get("spend_control", {}).get("reached"),
            "resetCreditsAvailable": remote.get("resetCredits", {}).get("available_count", remote_usage.get("rate_limit_reset_credits", {}).get("available_count", 0)),
            "canBuyCredits": remote.get("limitsConfig", {}).get("show_buy_credits"),
            "canManageAutoReload": remote.get("limitsConfig", {}).get("show_manage_auto_reload"),
        },
        "activity": {
            "last7DaysTokens": tokens,
            "last7DaysTurns": turns,
            "last7DaysSessions": len(sessions),
            "daily": days,
            "currentThreadTokens": token_total(latest_info.get("total_token_usage", {})),
        },
    }
    # Compatibility contract for the richer Plasma UI, deliberately limited to
    # the two windows Codex currently returns for this account.
    result["rateLimits"].update({
        "session": widget_window(session),
        "weeklyAll": widget_window(weekly),
        "source": "api" if remote_session else "local_log",
        "credits": {
            "amount": credits.get("balance", "0"),
            "currency": "USD",
            "autoReload": bool(result["account"]["canManageAutoReload"]),
        },
    })
    # Only measured values are emitted. The widget hides every panel whose
    # field is absent, so a Claude-only metric (dumbness score, burn rate,
    # service health, per-model weekly window) must NOT be faked here.
    result["lifetime"] = {"totalSessions": len(sessions)}
    return result


def main() -> None:
    data = collect()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="usage-widget-", suffix=".json", dir=DATA_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            json.dump(data, target, separators=(",", ":"))
            target.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, OUTPUT_FILE)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(json.dumps(data))


if __name__ == "__main__":
    main()
