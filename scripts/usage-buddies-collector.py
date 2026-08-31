#!/usr/bin/env python3
"""
Usage Buddies Data Collector
Parses ~/.claude/ local data and outputs structured JSON for the Plasma widget.
Runs periodically via systemd timer or called directly.
"""

import json
import os
import glob
import sys
import urllib.request
import urllib.error
import http.cookiejar
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict

CLAUDE_DIR = Path.home() / ".claude"
OUTPUT_FILE = CLAUDE_DIR / "widget-data.json"
STATUS_CACHE_FILE = CLAUDE_DIR / "widget-status-prev.json"
EVENTS_STATE_FILE = CLAUDE_DIR / "widget-events-state.json"
CONFIG_FILE = CLAUDE_DIR / "widget-config.json"

# Defaults para os 4 eventos de uso.
# - sound: nome freedesktop (Linux/macOS via paplay) ou caminho absoluto.
# - winSound: System.Media.SystemSounds equivalente no Windows.
# Membros de System.Media.SystemSounds. Allowlist: ver _play_event_sound().
SYSTEM_SOUNDS = frozenset({"Asterisk", "Beep", "Exclamation", "Hand", "Question"})

USAGE_EVENT_DEFAULTS = {
    "sessionEnded": {"sound": "dialog-warning",
                     "winSound": "Exclamation",
                     "urgency": "normal",
                     "title": "Sessão Claude esgotada",
                     "body": "A janela de 5h atingiu 100%."},
    "sessionReset": {"sound": "complete",
                     "winSound": "Asterisk",
                     "urgency": "low",
                     "title": "Sessão Claude renovada",
                     "body": "A janela de 5h foi resetada."},
    "weeklyEnded":  {"sound": "phone-outgoing-busy",
                     "winSound": "Hand",
                     "urgency": "critical",
                     "title": "Limite semanal Claude esgotado",
                     "body": "A janela de 7 dias atingiu 100%."},
    "weeklyReset":  {"sound": "service-login",
                     "winSound": "Asterisk",
                     "urgency": "normal",
                     "title": "Limite semanal Claude renovado",
                     "body": "A janela de 7 dias foi resetada."},
}

# Anthropic pricing (per 1M tokens) — May 2025 public prices
PRICING = {
    "claude-opus-4-6":            {"input": 15.00, "output": 75.00, "cache_read": 1.50,  "cache_create": 18.75},
    "claude-sonnet-4-6":          {"input":  3.00, "output": 15.00, "cache_read": 0.30,  "cache_create":  3.75},
    "claude-sonnet-4-5-20250929": {"input":  3.00, "output": 15.00, "cache_read": 0.30,  "cache_create":  3.75},
    "claude-haiku-4-5-20251001":  {"input":  0.80, "output":  4.00, "cache_read": 0.08,  "cache_create":  1.00},
}

MODEL_DISPLAY = {
    "claude-opus-4-6":            "Opus",
    "claude-sonnet-4-6":          "Sonnet",
    "claude-sonnet-4-5-20250929": "Sonnet 4.5",
    "claude-haiku-4-5-20251001":  "Haiku",
}

MODEL_COLORS = {
    "Opus":       "#D97706",
    "Sonnet":     "#2563EB",
    "Sonnet 4.5": "#6366F1",
    "Haiku":      "#10B981",
}

# Statuspage.io component IDs → short display names
COMPONENT_SHORT_NAMES = {
    "rwppv331jlwc": "claude.ai",
    "0qbwn08sd68x": "Platform",
    "k8w3r06qmzrp": "API",
    "yyzkbfz2thpt": "Claude Code",
    "bpp5gb3hpjcl": "Cowork",
    "0scnb50nvy53": "Gov",
}


def calculate_cost(model, input_t, output_t, cache_read_t, cache_create_t):
    """Calculate cost in USD for a given model and token counts."""
    p = PRICING.get(model)
    if not p:
        return 0.0
    return (
        (input_t / 1_000_000) * p["input"]
        + (output_t / 1_000_000) * p["output"]
        + (cache_read_t / 1_000_000) * p["cache_read"]
        + (cache_create_t / 1_000_000) * p["cache_create"]
    )


def load_stats_cache():
    """Load the stats-cache.json file."""
    path = CLAUDE_DIR / "stats-cache.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_timestamp(ts):
    """Parse a timestamp value (int ms, float, or ISO-8601 string) to datetime."""
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts, tz=timezone.utc)
    elif isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def parse_sessions_in_window(cutoff_utc, end_utc=None):
    """Parse JSONL session files for records within a time window.

    Returns: (model_tokens, sessions_list, message_count, per_model_tokens)

    per_model_tokens is a dict keyed by family ("sonnet", "opus", "fable"),
    each value a defaultdict of token counters — so weekly per-model quotas can
    be estimated locally when the claude.ai API is unavailable.
    """
    if end_utc is None:
        end_utc = datetime.now(timezone.utc)

    model_tokens = defaultdict(lambda: {
        "input": 0, "output": 0, "cache_read": 0, "cache_create": 0
    })
    # Per-family buckets. Keys match the family substring matched in the model
    # id; consumers read per_model_tokens["opus"] etc.
    per_model_tokens = {
        family: defaultdict(lambda: {
            "input": 0, "output": 0, "cache_read": 0, "cache_create": 0
        })
        for family in ("sonnet", "opus", "fable")
    }
    sessions = []
    session_set = set()
    total_messages = 0

    # Skip files not modified recently (optimization)
    mtime_cutoff = (cutoff_utc - timedelta(hours=1)).timestamp()

    projects_dir = CLAUDE_DIR / "projects"
    if not projects_dir.exists():
        return model_tokens, sessions, total_messages, sonnet_tokens

    for jsonl_file in projects_dir.rglob("*.jsonl"):
        # Skip old files
        try:
            if jsonl_file.stat().st_mtime < mtime_cutoff:
                continue
        except OSError:
            continue

        is_subagent = "subagents" in str(jsonl_file)
        project_name = jsonl_file.parts[-2] if not is_subagent else jsonl_file.parts[-3]
        if project_name.startswith("-"):
            project_name = project_name[1:].replace("-", "/")

        try:
            with open(jsonl_file, encoding="utf-8", errors="replace") as f:
                session_has_window = False
                session_messages = 0
                session_start = None

                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    rec_type = record.get("type", "")
                    msg = record.get("message", {})

                    # Parse timestamp
                    ts = record.get("timestamp")
                    rec_date = parse_timestamp(ts) if ts else None
                    if not rec_date:
                        continue

                    # Check if within window
                    if rec_date < cutoff_utc or rec_date > end_utc:
                        continue

                    if session_start is None:
                        session_start = rec_date
                    session_has_window = True

                    # Count messages
                    if rec_type in ("user", "assistant") or msg.get("role") in ("user", "assistant"):
                        session_messages += 1
                        if msg.get("role") == "assistant":
                            total_messages += 1

                    # Extract token usage
                    usage = msg.get("usage", {})
                    model = msg.get("model", "")
                    if usage and model:
                        inp = usage.get("input_tokens", 0)
                        out = usage.get("output_tokens", 0)
                        cr = usage.get("cache_read_input_tokens", 0)
                        cc = usage.get("cache_creation_input_tokens", 0)

                        model_tokens[model]["input"] += inp
                        model_tokens[model]["output"] += out
                        model_tokens[model]["cache_read"] += cr
                        model_tokens[model]["cache_create"] += cc

                        # Track per-family usage (Sonnet/Opus/Fable) so the
                        # local-estimate path can populate weekly per-model bars.
                        ml = model.lower()
                        for family in ("sonnet", "opus", "fable"):
                            if family in ml:
                                bucket = per_model_tokens[family][model]
                                bucket["input"] += inp
                                bucket["output"] += out
                                bucket["cache_read"] += cr
                                bucket["cache_create"] += cc
                                break

                if session_has_window and not is_subagent:
                    sid = jsonl_file.stem
                    if sid not in session_set:
                        session_set.add(sid)
                        sessions.append({
                            "id": sid[:8],
                            "project": project_name,
                            "messages": session_messages,
                            "start": session_start.isoformat() if session_start else "",
                        })

        except (PermissionError, OSError):
            continue

    return (
        dict(model_tokens),
        sessions,
        total_messages,
        {family: dict(buckets) for family, buckets in per_model_tokens.items()},
    )


def compute_window_cost(model_tokens):
    """Compute total cost from model token dict."""
    total = 0.0
    for model, t in model_tokens.items():
        total += calculate_cost(model, t["input"], t["output"], t["cache_read"], t["cache_create"])
    return total


def compute_window_output_tokens(model_tokens):
    """Sum output tokens across all models (primary rate limit metric)."""
    return sum(t["output"] for t in model_tokens.values())


def _get_chrome_key(chrome_dir, is_mac=False):
    """Derive Chrome cookie decryption key on Linux/macOS.

    Tries GNOME Keyring, KWallet, then falls back to 'peanuts'.
    Returns 16-byte AES key derived via PBKDF2.
    macOS uses 1003 iterations; Linux uses 1.
    """
    import hashlib
    import subprocess as _sp

    password = None

    # --- GNOME Keyring via secret-tool ---
    # Try v2 then v1 schemas, for both Chrome and Chromium
    gnome_lookups = [
        ("chrome_libsecret_os_crypt_password_v2", "chrome"),
        ("chrome_libsecret_os_crypt_password_v1", "chrome"),
        ("chrome_libsecret_os_crypt_password_v2", "chromium"),
        ("chrome_libsecret_os_crypt_password_v1", "chromium"),
    ]
    for schema, app in gnome_lookups:
        if password:
            break
        try:
            result = _sp.run(
                ["secret-tool", "lookup", "xdg:schema", schema, "application", app],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                password = result.stdout.strip()
                break
        except (FileNotFoundError, _sp.TimeoutExpired, OSError):
            continue

    # --- KWallet ---
    if not password:
        kwallet_lookups = [
            ("Chrome Safe Storage", "Chrome Keys"),
            ("Chrome Safe Storage", "Passwords"),
            ("Chromium Safe Storage", "Chromium Keys"),
            ("Chromium Safe Storage", "Passwords"),
        ]
        for storage_name, folder in kwallet_lookups:
            if password:
                break
            try:
                result = _sp.run(
                    ["kwallet-query", "-r", storage_name,
                     "-f", folder, "kdewallet"],
                    capture_output=True, timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    password = result.stdout.strip()
                    if "--verbose" in sys.argv:
                        print(f"[chrome] Got key from KWallet: {folder}/{storage_name}")
                    break
            except (FileNotFoundError, _sp.TimeoutExpired, OSError):
                continue

    # --- Fallback ---
    if not password:
        password = b"peanuts"
    if isinstance(password, str):
        password = password.encode("utf-8")
    elif isinstance(password, bytes):
        # Ensure consistent encoding for bytes from keyring
        try:
            password = password.decode("utf-8").encode("utf-8")
        except UnicodeDecodeError:
            pass

    # macOS uses 1003 iterations; Linux uses 1
    iterations = 1003 if is_mac else 1
    return hashlib.pbkdf2_hmac("sha1", password, b"saltysalt", iterations, dklen=16)


def _decrypt_chrome_value(encrypted_value, key):
    """Decrypt a Chrome encrypted cookie value.

    Handles v10/v11 prefix, AES-128-CBC, PKCS7 unpadding, and
    Chrome 130+ (DB schema >= v24) 32-byte SHA-256 integrity hash.
    Returns decoded UTF-8 string or None.
    """
    if not encrypted_value or len(encrypted_value) < 4:
        return None

    # Strip v10/v11 prefix (3 bytes)
    prefix = encrypted_value[:3]
    if prefix not in (b"v10", b"v11"):
        return None
    ciphertext = encrypted_value[3:]

    iv = b" " * 16  # 16 space characters

    plaintext = None

    # Try cryptography package first
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.padding import PKCS7

        cipher = Cipher(algorithms.AES128(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()

        unpadder = PKCS7(128).unpadder()
        plaintext = unpadder.update(padded) + unpadder.finalize()
    except ImportError:
        # Fallback: openssl CLI
        import subprocess as _sp
        try:
            result = _sp.run(
                ["openssl", "enc", "-aes-128-cbc", "-d",
                 "-K", key.hex(), "-iv", iv.hex(), "-nopad"],
                input=ciphertext, capture_output=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout:
                padded = result.stdout
                # Manual PKCS7 unpadding
                pad_len = padded[-1]
                if 1 <= pad_len <= 16 and padded[-pad_len:] == bytes([pad_len]) * pad_len:
                    plaintext = padded[:-pad_len]
                else:
                    plaintext = padded
        except (FileNotFoundError, _sp.TimeoutExpired, OSError):
            return None
    except Exception:
        return None

    if plaintext is None:
        return None

    # Chrome 130+ (DB schema >= v24): 32-byte SHA-256 integrity hash prepended.
    # Try with hash stripped first; if that fails UTF-8, try without stripping.
    if len(plaintext) > 32:
        stripped = plaintext[32:]
        try:
            return stripped.decode("utf-8")
        except UnicodeDecodeError:
            pass

    try:
        return plaintext.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _get_chrome_cookies():
    """Extract claude.ai cookies from Chrome/Chromium.

    Searches multiple browser paths and profiles, decrypts encrypted values.
    Supports Linux and macOS paths.
    Returns cookie string or empty string.
    """
    import sqlite3
    import shutil
    import platform
    import tempfile

    is_mac = platform.system() == "Darwin"

    if is_mac:
        app_support = Path.home() / "Library" / "Application Support"
        base_dirs = [
            app_support / "Google" / "Chrome",
            app_support / "Chromium",
            app_support / "BraveSoftware" / "Brave-Browser",
        ]
    else:
        base_dirs = [
            Path.home() / ".config" / "google-chrome",
            Path.home() / ".config" / "chromium",
            Path.home() / "snap" / "chromium" / "common" / "chromium",
            Path.home() / ".var" / "app" / "com.google.Chrome" / "config" / "google-chrome",
            Path.home() / ".var" / "app" / "org.chromium.Chromium" / "config" / "chromium",
        ]

    key = None  # lazily derived

    verbose = "--verbose" in sys.argv

    def _find_cookie_db(profile_dir):
        # Chrome 108+ stores at Profile/Network/Cookies; older at Profile/Cookies
        for rel in (Path("Network") / "Cookies", Path("Cookies")):
            candidate = profile_dir / rel
            if candidate.exists():
                return candidate
        return None

    for base in base_dirs:
        if not base.exists():
            continue
        if verbose:
            print(f"[chrome] Found browser dir: {base}")
        # Dynamic profile scan: find all dirs containing a Cookies file (new or legacy layout)
        try:
            profile_dirs = [d for d in base.iterdir() if d.is_dir() and _find_cookie_db(d) is not None]
        except PermissionError:
            continue
        for profile_dir in profile_dirs:
            cookie_db = _find_cookie_db(profile_dir)
            if verbose:
                print(f"[chrome] Found cookie DB: {cookie_db}")
            tmp_dir = Path(tempfile.gettempdir())
            tmp_db = tmp_dir / f"claude_chrome_{os.getpid()}.sqlite"
            try:
                # Copy DB + WAL/SHM files (Chrome uses WAL journal mode)
                shutil.copy2(cookie_db, tmp_db)
                for suffix in ["-wal", "-shm", "-journal"]:
                    wal_src = Path(str(cookie_db) + suffix)
                    wal_dst = Path(str(tmp_db) + suffix)
                    if wal_src.exists():
                        shutil.copy2(wal_src, wal_dst)
                        if verbose:
                            print(f"[chrome] Copied {suffix} file")

                conn = sqlite3.connect(str(tmp_db))
                cursor = conn.execute(
                    "SELECT name, value, encrypted_value FROM cookies "
                    "WHERE host_key LIKE '%claude.ai%'"
                )
                rows = cursor.fetchall()
                if verbose:
                    print(f"[chrome] Found {len(rows)} claude.ai cookies in {profile_dir.name}")
                pairs = []
                failed = []  # cookies not decrypted by primary key (Linux/mac only)
                for name, value, encrypted_value in rows:
                    if value:
                        pairs.append(f"{name}={value}")
                    elif encrypted_value:
                        if key is None:
                            key = _get_chrome_key(base, is_mac=is_mac)
                        decrypted = _decrypt_chrome_value(encrypted_value, key)
                        if decrypted:
                            pairs.append(f"{name}={decrypted}")
                        else:
                            failed.append((name, encrypted_value))
                            if verbose:
                                print(f"[chrome] FAILED to decrypt cookie: {name} (len={len(encrypted_value)})")

                # Keyring key may be stale (Chrome 120+ on KDE/Wayland can fall back to
                # "basic"/peanuts when XDG portal init fails — see os_crypt.portal in
                # Local State). Retry failed cookies with the peanuts fallback key.
                if failed and not pairs:
                    import hashlib as _h
                    iterations = 1003 if is_mac else 1
                    peanuts_key = _h.pbkdf2_hmac("sha1", b"peanuts", b"saltysalt", iterations, dklen=16)
                    if peanuts_key != key:
                        if verbose:
                            print(f"[chrome] Primary key decrypted 0 cookies — retrying with peanuts")
                        for name, ev in failed:
                            decrypted = _decrypt_chrome_value(ev, peanuts_key)
                            if decrypted:
                                pairs.append(f"{name}={decrypted}")
                        if verbose and pairs:
                            print(f"[chrome] Peanuts recovered {len(pairs)} cookies")
                conn.close()
                if pairs:
                    if verbose:
                        print(f"[chrome] Got {len(pairs)} cookies: {[p.split('=')[0] for p in pairs]}")
                    return "; ".join(pairs)
            except Exception as e:
                if verbose:
                    print(f"[chrome] Error reading {cookie_db}: {e}")
                continue
            finally:
                # Always cleanup temp files
                for suffix in ["", "-wal", "-shm", "-journal"]:
                    Path(str(tmp_db) + suffix).unlink(missing_ok=True)
    return ""


def _get_firefox_cookies():
    """Extract claude.ai cookies from Firefox (plain text, no decryption needed).

    Searches native, snap, flatpak, Windows, and macOS Firefox paths.
    Returns cookie string or empty string.
    """
    import sqlite3
    import shutil
    import platform

    firefox_dirs = [
        # Linux
        Path.home() / ".mozilla" / "firefox",
        Path.home() / "snap" / "firefox" / "common" / ".mozilla" / "firefox",
        Path.home() / ".var" / "app" / "org.mozilla.firefox" / ".mozilla" / "firefox",
    ]
    if platform.system() == "Windows":
        # Chrome/Edge on Windows encrypt cookies with App-Bound Encryption, which
        # the DPAPI path never handled (it only read v10/v11 blobs). Firefox keeps
        # them in plaintext SQLite, so it is the only automatic source on Windows.
        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        firefox_dirs.insert(0, appdata / "Mozilla" / "Firefox" / "Profiles")
    elif platform.system() == "Darwin":
        firefox_dirs.insert(0, Path.home() / "Library" / "Application Support" / "Firefox" / "Profiles")

    import tempfile

    for firefox_dir in firefox_dirs:
        if not firefox_dir.exists():
            continue
        try:
            profiles = [d for d in firefox_dir.iterdir() if d.is_dir()]
        except PermissionError:
            continue
        for profile in profiles:
            cookie_db = profile / "cookies.sqlite"
            if not cookie_db.exists():
                continue
            tmp_dir = Path(tempfile.gettempdir())
            tmp_db = tmp_dir / f"claude_ff_{os.getpid()}.sqlite"
            try:
                shutil.copy2(cookie_db, tmp_db)
                # Copy WAL/SHM files (Firefox uses WAL journal mode)
                for suffix in ["-wal", "-shm", "-journal"]:
                    src = Path(str(cookie_db) + suffix)
                    dst = Path(str(tmp_db) + suffix)
                    if src.exists():
                        shutil.copy2(src, dst)
                conn = sqlite3.connect(str(tmp_db))
                cursor = conn.execute(
                    "SELECT name, value FROM moz_cookies WHERE host LIKE '%claude.ai%'"
                )
                pairs = [f"{name}={value}" for name, value in cursor.fetchall()]
                conn.close()
                if pairs:
                    return "; ".join(pairs)
            except Exception:
                continue
            finally:
                for suffix in ["", "-wal", "-shm", "-journal"]:
                    Path(str(tmp_db) + suffix).unlink(missing_ok=True)
    return ""


def _get_manual_cookies():
    """Read cookie from a manual file at ~/.claude/widget-cookies.txt.

    Accepted formats (one line):
      - bare value: "eyJhbGciOi..." (assumed to be sessionKey)
      - keyed: "sessionKey=eyJ..."
      - full string: "sessionKey=eyJ...; lastActiveOrg=abc"
    """
    path = CLAUDE_DIR / "widget-cookies.txt"
    verbose = "--verbose" in sys.argv
    if not path.exists():
        return ""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except Exception as e:
        if verbose:
            print(f"[manual] read error: {e}")
        return ""
    if not raw:
        return ""
    if "sessionKey=" in raw:
        cookies = raw
    else:
        cookies = f"sessionKey={raw}"
    if verbose:
        print(f"[manual] using widget-cookies.txt ({len(cookies)} chars)")
    return cookies


def get_claude_cookies():
    """Extract claude.ai cookies for API auth.

    Priority: manual file → Firefox (plain text) → Chrome (encrypted, may be locked).
    Returns cookie string or empty string.
    """
    def _has_session(c):
        return "sessionKey=" in c

    cookies = _get_manual_cookies()
    if cookies and _has_session(cookies):
        return cookies

    cookies = _get_firefox_cookies()
    if cookies and _has_session(cookies):
        return cookies

    cookies = _get_chrome_cookies()
    if cookies and _has_session(cookies):
        return cookies

    return ""


def load_config():
    """Load widget config from ~/.claude/widget-config.json."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_config(cfg):
    """Persist widget config."""
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass


def detect_org_id(cookies):
    """Auto-detect org_id from lastActiveOrg cookie or /api/organizations."""
    # 1. Try lastActiveOrg cookie (fastest)
    for pair in cookies.split(";"):
        pair = pair.strip()
        if pair.startswith("lastActiveOrg="):
            val = pair.split("=", 1)[1].strip()
            if len(val) > 10:
                return val

    # 2. Fallback: query /api/organizations
    try:
        req = urllib.request.Request("https://claude.ai/api/organizations")
        req.add_header("Cookie", cookies)
        req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64; rv:145.0) Gecko/20100101 Firefox/145.0")
        req.add_header("anthropic-client-platform", "web_claude_ai")
        with urllib.request.urlopen(req, timeout=10) as resp:
            orgs = json.loads(resp.read().decode())
            if orgs and isinstance(orgs, list):
                return orgs[0].get("uuid") or orgs[0].get("id", "")
    except Exception:
        pass
    return ""


def get_org_id(cookies=""):
    """Return org_id from config, or detect and save it."""
    cfg = load_config()
    org_id = cfg.get("org_id", "")
    if org_id:
        return org_id

    if not cookies:
        cookies = get_claude_cookies()
    org_id = detect_org_id(cookies)
    if org_id:
        cfg["org_id"] = org_id
        save_config(cfg)
    return org_id


def _api_request(path):
    """Make an authenticated request to claude.ai API."""
    cookies = get_claude_cookies()
    if not cookies:
        return None

    org_id = get_org_id(cookies)
    if not org_id:
        return None

    url = f"https://claude.ai/api/organizations/{org_id}/{path}"
    req = urllib.request.Request(url)
    req.add_header("Cookie", cookies)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64; rv:145.0) Gecko/20100101 Firefox/145.0")
    req.add_header("anthropic-client-platform", "web_claude_ai")
    req.add_header("anthropic-client-version", "1.0.0")

    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read().decode())
    except Exception:
        return None


def fetch_usage_from_api():
    """Fetch usage/utilization data with five_hour, seven_day, etc."""
    return _api_request("usage")


def fetch_credits_from_api():
    """Fetch prepaid credits balance."""
    return _api_request("prepaid/credits")


def fetch_overage_data():
    """Fetch extra usage (overage) spend limit and credit grant."""
    spend_limit = _api_request("overage_spend_limit")
    credit_grant = _api_request("overage_credit_grant")
    if not spend_limit and not credit_grant:
        return None
    result = {}
    if spend_limit:
        currency = spend_limit.get("currency", "USD")
        result["enabled"] = spend_limit.get("is_enabled", False)
        result["monthlyLimit"] = (spend_limit.get("monthly_credit_limit") or 0) / 100
        result["usedCredits"] = (spend_limit.get("used_credits") or 0) / 100
        result["currency"] = currency
        result["disabledReason"] = spend_limit.get("disabled_reason", "")
        result["outOfCredits"] = spend_limit.get("out_of_credits", False)
    if credit_grant:
        result["grantAvailable"] = credit_grant.get("available", False)
        result["grantAmount"] = (credit_grant.get("amount_minor_units") or 0) / 100
        result["grantCurrency"] = credit_grant.get("currency") or "USD"
    return result


def fetch_service_status():
    """Fetch Claude service health from status.claude.com (Statuspage.io API)."""
    try:
        req = urllib.request.Request("https://status.claude.com/api/v2/summary.json")
        req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64; rv:145.0) Gecko/20100101 Firefox/145.0")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return None

    # Showcase components only (the main ones)
    components = []
    for c in data.get("components", []):
        if c.get("showcase", False):
            components.append({
                "id": c["id"],
                "name": COMPONENT_SHORT_NAMES.get(c["id"], c["name"].split(" ")[0]),
                "status": c["status"],
            })

    # Active (non-resolved) incidents
    active_incidents = []
    for inc in data.get("incidents", []):
        if inc.get("resolved_at") is None:
            updates = inc.get("incident_updates", [])
            latest_body = updates[0].get("body", "") if updates else ""
            active_incidents.append({
                "name": inc["name"],
                "status": inc["status"],
                "impact": inc.get("impact", ""),
                "latest_update": latest_body,
                "started_at": inc.get("started_at", ""),
                "url": inc.get("shortlink", ""),
            })

    overall = data.get("status", {})
    return {
        "indicator": overall.get("indicator", "none"),
        "description": overall.get("description", "All Systems Operational"),
        "updated_at": data.get("page", {}).get("updated_at", ""),
        "components": components,
        "active_incidents": active_incidents,
    }


def notify_status_change(new_status):
    """Send KDE desktop notification when Claude service status changes."""
    if new_status is None:
        return

    new_indicator = new_status.get("indicator", "none")
    prev_indicator = "none"

    if STATUS_CACHE_FILE.exists():
        try:
            prev = json.loads(STATUS_CACHE_FILE.read_text(encoding="utf-8"))
            prev_indicator = prev.get("indicator", "none")
        except Exception:
            pass

    # Save current state
    try:
        STATUS_CACHE_FILE.write_text(json.dumps({"indicator": new_indicator}))
    except Exception:
        pass

    # Only notify on change
    if new_indicator == prev_indicator:
        return

    import subprocess
    import platform

    if new_indicator == "none":
        title = "Claude Status"
        body = "All Systems Operational"
        urgency = "normal"
    else:
        title = "Claude Status Alert"
        incidents = new_status.get("active_incidents", [])
        body = incidents[0]["name"] if incidents else new_status.get("description", "Service issue detected")
        urgency = "critical" if new_indicator in ("major", "critical") else "normal"

    # Only send desktop notifications on Linux with a display server
    if platform.system() != "Linux":
        return
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return

    try:
        subprocess.run(
            ["notify-send", "--urgency", urgency, "--icon", "claude-logo",
             "--app-name", "Claude Status", title, body],
            check=False, timeout=5
        )
    except Exception:
        pass


_FREEDESKTOP_SOUND_DIRS = [
    "/usr/share/sounds/freedesktop/stereo",
    "/usr/share/sounds/freedesktop",
    "/usr/share/sounds/gnome/default/alerts",  # fallback Ubuntu/GNOME
]

# Players cross-platform tentados em ordem (primeiro disponível vence)
_LINUX_PLAYERS = ["paplay", "pw-play", "aplay", "ffplay", "play"]


def _which(cmd):
    import shutil
    return shutil.which(cmd)


def _resolve_sound_path(sound_spec):
    """Resolve nome freedesktop para caminho .oga/.ogg/.wav.
    Retorna spec original se já for caminho válido, ou None."""
    if not sound_spec:
        return None
    p = Path(sound_spec)
    if p.is_absolute() or "/" in sound_spec or "\\" in sound_spec:
        return str(p) if p.exists() else None
    for d in _FREEDESKTOP_SOUND_DIRS:
        for ext in (".oga", ".ogg", ".wav"):
            cand = Path(d) / f"{sound_spec}{ext}"
            if cand.exists():
                return str(cand)
    return None


def _play_event_sound(sound_spec, win_sound=None):
    """Toca som de forma cross-platform. Fire-and-forget."""
    import subprocess
    import platform

    system = platform.system()

    if system == "Windows":
        # PowerShell + System.Media.SystemSounds (sempre disponível).
        # win_sound vem de ~/.claude/widget-config.json (sounds.<evento>Win) e é
        # interpolado num comando PowerShell, então só nomes conhecidos passam:
        # um valor arbitrário aqui seria execução de comando a partir de um
        # arquivo de dados. Valor desconhecido cai no padrão, nunca é concatenado.
        win_name = win_sound if win_sound in SYSTEM_SOUNDS else "Asterisk"
        if win_sound and win_name != win_sound:
            print(f"warn: som Windows desconhecido {win_sound!r}, usando Asterisk",
                  file=sys.stderr)
        ps_cmd = f"[System.Media.SystemSounds]::{win_name}.Play(); Start-Sleep -Milliseconds 600"
        try:
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as e:
            print(f"warn: falha ao tocar som Windows '{win_name}': {e}", file=sys.stderr)
        return

    if system == "Darwin":  # macOS
        path = _resolve_sound_path(sound_spec) or f"/System/Library/Sounds/{sound_spec}.aiff"
        if not Path(path).exists():
            path = "/System/Library/Sounds/Glass.aiff"
        try:
            subprocess.Popen(["afplay", path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        except Exception as e:
            print(f"warn: falha ao tocar som macOS: {e}", file=sys.stderr)
        return

    # Linux: tenta paplay/pw-play/aplay no arquivo resolvido; fallback canberra
    path = _resolve_sound_path(sound_spec)
    cmd = None
    if path:
        for player in _LINUX_PLAYERS:
            if _which(player):
                cmd = [player, path]
                break
    if cmd is None and _which("canberra-gtk-play"):
        cmd = ["canberra-gtk-play", "-i", sound_spec]
    if cmd is None:
        print(f"warn: nenhum player de áudio encontrado para '{sound_spec}'", file=sys.stderr)
        return
    try:
        subprocess.Popen(cmd,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except Exception as e:
        print(f"warn: falha ao tocar som '{sound_spec}': {e}", file=sys.stderr)


def _load_events_state():
    if not EVENTS_STATE_FILE.exists():
        return None
    try:
        return json.loads(EVENTS_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_events_state(state):
    try:
        EVENTS_STATE_FILE.write_text(json.dumps(state, indent=2))
        try:
            os.chmod(EVENTS_STATE_FILE, 0o600)
        except OSError:
            pass
    except Exception as e:
        print(f"warn: falha ao gravar events state: {e}", file=sys.stderr)


def detect_usage_transitions(prev_state, curr_data):
    """Função pura: compara snapshot anterior com dados atuais e retorna
    a lista de IDs de eventos disparados ('sessionEnded', 'sessionReset',
    'weeklyEnded', 'weeklyReset'). Também devolve o snapshot novo."""
    rate_limits = curr_data.get("rateLimits") or {}
    scopes = {
        "session":   ("sessionEnded",  "sessionReset"),
        "weeklyAll": ("weeklyEnded",   "weeklyReset"),
    }

    events = []
    new_snapshot = {"lastRun": datetime.now(timezone.utc).isoformat()}

    for scope_key, (ended_id, reset_id) in scopes.items():
        curr = rate_limits.get(scope_key) or {}
        curr_pct = curr.get("percentUsed")
        curr_reset = curr.get("resetsAt") or ""

        prev_scope = (prev_state or {}).get(scope_key) or {}
        prev_pct = prev_scope.get("percentUsed")
        prev_reset = prev_scope.get("resetsAt") or ""

        # ACABOU: 1ª execução já em 100%, ou transição de <100 para >=100
        if curr_pct is not None and curr_pct >= 100:
            if prev_pct is None or prev_pct < 100:
                events.append(ended_id)

        # RESETOU: resetsAt avançou claramente E havia uso significativo antes
        if prev_reset and curr_reset:
            try:
                p = parse_timestamp(prev_reset)
                c = parse_timestamp(curr_reset)
                if p and c and (c - p) > timedelta(hours=1) and (prev_pct or 0) > 5:
                    events.append(reset_id)
            except Exception:
                pass

        new_snapshot[scope_key] = {
            "percentUsed": curr_pct,
            "resetsAt": curr_reset,
        }

    return events, new_snapshot


def _notify_desktop(title, body, urgency, icon="claude-logo", app_name="Usage Buddies"):
    """Envia notificação visual cross-platform."""
    import subprocess
    import platform

    system = platform.system()

    if system == "Linux":
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            return
        if not _which("notify-send"):
            return
        try:
            subprocess.run(
                ["notify-send", "--urgency", urgency,
                 "--icon", icon, "--app-name", app_name, title, body],
                check=False, timeout=5,
            )
        except Exception as e:
            print(f"warn: notify-send falhou: {e}", file=sys.stderr)
        return

    if system == "Windows":
        # Toast nativo via PowerShell (sem dependências externas)
        # Escape de aspas simples para PowerShell
        t = title.replace("'", "''")
        b = body.replace("'", "''")
        ps_cmd = (
            "[reflection.assembly]::loadwithpartialname('System.Windows.Forms') | Out-Null;"
            "[reflection.assembly]::loadwithpartialname('System.Drawing') | Out-Null;"
            "$n = New-Object System.Windows.Forms.NotifyIcon;"
            "$n.Icon = [System.Drawing.SystemIcons]::Information;"
            "$n.BalloonTipTitle = '" + t + "';"
            "$n.BalloonTipText  = '" + b + "';"
            "$n.Visible = $true;"
            "$n.ShowBalloonTip(8000);"
            "Start-Sleep -Seconds 9;"
            "$n.Dispose();"
        )
        try:
            subprocess.Popen(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as e:
            print(f"warn: notificação Windows falhou: {e}", file=sys.stderr)
        return

    if system == "Darwin":
        try:
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{body}" with title "{title}"'],
                check=False, timeout=5,
            )
        except Exception as e:
            print(f"warn: notificação macOS falhou: {e}", file=sys.stderr)


def notify_usage_event(event_id, config):
    """Dispara som + notificação visual para um evento de uso."""
    defaults = USAGE_EVENT_DEFAULTS.get(event_id)
    if not defaults:
        return

    sounds_cfg = (config.get("notifications") or {}).get("sounds") or {}
    sound = sounds_cfg.get(event_id, defaults["sound"])
    win_sound = sounds_cfg.get(event_id + "Win", defaults.get("winSound"))

    _play_event_sound(sound, win_sound=win_sound)
    _notify_desktop(defaults["title"], defaults["body"], defaults["urgency"])


def process_usage_events(curr_data, config):
    """Ponto de entrada chamado pelo main(): detecta transições, dispara,
    grava novo snapshot. Respeita notifications.enabled (default True)."""
    notif_cfg = config.get("notifications") or {}
    if notif_cfg.get("enabled", True) is False:
        return

    prev_state = _load_events_state()
    events, new_snapshot = detect_usage_transitions(prev_state, curr_data)
    for ev in events:
        notify_usage_event(ev, config)
    _save_events_state(new_snapshot)


def run_test_sounds(config):
    """Toca os 4 sons em sequência (sem notificação, sem mexer em estado)."""
    import time
    sounds_cfg = (config.get("notifications") or {}).get("sounds") or {}
    order = ["sessionEnded", "sessionReset", "weeklyEnded", "weeklyReset"]
    for ev in order:
        sound = sounds_cfg.get(ev, USAGE_EVENT_DEFAULTS[ev]["sound"])
        win_sound = sounds_cfg.get(ev + "Win", USAGE_EVENT_DEFAULTS[ev].get("winSound"))
        print(f"▶ {ev} → {sound}")
        _play_event_sound(sound, win_sound=win_sound)
        time.sleep(1.5)
    print("OK: 4 sons testados.")


def detect_adaptive_thinking():
    """Check Claude Code settings for adaptive thinking / 1M context."""
    settings_file = CLAUDE_DIR / "settings.json"
    result = {"adaptive_thinking": True, "context_1m": True}
    if settings_file.exists():
        try:
            settings = json.loads(settings_file.read_text(encoding="utf-8"))
            env = settings.get("env", {})
            result["adaptive_thinking"] = env.get("CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING", "0") != "1"
            result["context_1m"] = env.get("CLAUDE_CODE_DISABLE_1M_CONTEXT", "0") != "1"
        except Exception:
            pass
    return result


def read_claude_settings_summary():
    """Surface a compact view of ~/.claude/settings.json for the widget.

    Returns None if the file is missing or unreadable, so the UI can hide the
    card rather than render empty values.
    """
    settings_file = CLAUDE_DIR / "settings.json"
    if not settings_file.exists():
        return None
    try:
        s = json.loads(settings_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    env = s.get("env") or {}
    plugins = s.get("enabledPlugins") or {}
    return {
        "effortLevel": s.get("effortLevel") or "",
        "alwaysThinking": bool(s.get("alwaysThinkingEnabled")),
        "skipDangerousPrompt": bool(s.get("skipDangerousModePermissionPrompt")),
        "adaptiveThinkingDisabled": env.get("CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING", "0") == "1",
        "context1mDisabled": env.get("CLAUDE_CODE_DISABLE_1M_CONTEXT", "0") == "1",
        "enabledPlugins": sorted([k for k, v in plugins.items() if v]),
        "pluginCount": sum(1 for v in plugins.values() if v),
    }


def read_mcp_auth_pending():
    """Return the list of MCP servers waiting for re-authentication."""
    path = CLAUDE_DIR / "mcp-needs-auth-cache.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, dict):
        pending = [name for name, flag in data.items() if flag]
    elif isinstance(data, list):
        pending = [str(x) for x in data]
    else:
        pending = []
    return pending


def _jsonl_files_newer_than(cutoff):
    """Yield JSONL files under ~/.claude/projects whose mtime >= cutoff - 1h."""
    projects_dir = CLAUDE_DIR / "projects"
    if not projects_dir.exists():
        return
    mtime_cutoff = (cutoff - timedelta(hours=1)).timestamp()
    for jsonl_file in projects_dir.rglob("*.jsonl"):
        try:
            if jsonl_file.stat().st_mtime < mtime_cutoff:
                continue
        except OSError:
            continue
        yield jsonl_file


def calculate_tool_use(days=7, limit=50):
    """Count tool invocations by name in the last N days across JSONL files.

    Returns {"byTool": {name: count, ...}, "total": int} — capped at `limit`
    entries in byTool (top N by count, rest grouped as "other").
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    counts = {}
    total = 0
    for jsonl_file in _jsonl_files_newer_than(cutoff):
        try:
            with open(jsonl_file, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if '"tool_use"' not in line:
                        continue
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = r.get("timestamp")
                    d = parse_timestamp(ts) if ts else None
                    if not d or d < cutoff:
                        continue
                    msg = r.get("message") or {}
                    content = msg.get("content") or []
                    if not isinstance(content, list):
                        continue
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "tool_use":
                            name = c.get("name") or "?"
                            counts[name] = counts.get(name, 0) + 1
                            total += 1
        except (PermissionError, OSError):
            continue
    # Keep only the top `limit`; fold the rest into "other"
    if len(counts) > limit:
        top = dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:limit])
        other = sum(v for k, v in counts.items() if k not in top)
        top["other"] = other
        counts = top
    return {"byTool": counts, "total": total}


def calculate_compaction_events(days=7):
    """Count context-compaction events in the last N days.

    Compactions are system records whose subtype mentions 'compact' or whose
    content signals a snapshot rewrite. Best-effort: returns 0 when the schema
    doesn't match anything (no false positives).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    count = 0
    last_ts = None
    for jsonl_file in _jsonl_files_newer_than(cutoff):
        try:
            with open(jsonl_file, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if 'compact' not in line.lower():
                        continue
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    subtype = str(r.get("subtype", "")).lower()
                    op = str(r.get("operation", "")).lower()
                    is_compact = (
                        "compact" in subtype
                        or "compact" in op
                        or r.get("isSnapshotUpdate") is True
                    )
                    if not is_compact:
                        continue
                    ts = r.get("timestamp")
                    d = parse_timestamp(ts) if ts else None
                    if not d or d < cutoff:
                        continue
                    count += 1
                    if last_ts is None or d > last_ts:
                        last_ts = d
        except (PermissionError, OSError):
            continue
    return {
        "count": count,
        "lastAt": last_ts.isoformat() if last_ts else "",
    }


def detect_opus_fallbacks(days=1):
    """Best-effort: count messages where an Opus-priced model was expected but
    Sonnet/Haiku was actually used, as a proxy for silent downgrades.

    Heuristic: within the rolling window, compute (opus_msg / total_msg). If
    today's ratio is notably below the 7-day baseline, flag the gap. Without
    explicit `requested_model` in the payload we can't prove a single downgrade,
    but a sustained dip is still actionable as a 'watch' signal.
    """
    now = datetime.now(timezone.utc)
    day_cutoff = now - timedelta(days=days)
    week_cutoff = now - timedelta(days=7)

    def _count_models(start):
        by_model = {"opus": 0, "sonnet": 0, "haiku": 0, "other": 0}
        for jsonl_file in _jsonl_files_newer_than(start):
            try:
                with open(jsonl_file, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if '"model"' not in line:
                            continue
                        try:
                            r = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        ts = r.get("timestamp")
                        d = parse_timestamp(ts) if ts else None
                        if not d or d < start:
                            continue
                        m = (r.get("message") or {}).get("model") or ""
                        ml = m.lower()
                        if "opus" in ml:
                            by_model["opus"] += 1
                        elif "sonnet" in ml:
                            by_model["sonnet"] += 1
                        elif "haiku" in ml:
                            by_model["haiku"] += 1
                        elif m:
                            by_model["other"] += 1
            except (PermissionError, OSError):
                continue
        return by_model

    today = _count_models(day_cutoff)
    week = _count_models(week_cutoff)
    today_total = sum(today.values()) or 0
    week_total = sum(week.values()) or 0
    today_opus_ratio = (today["opus"] / today_total) if today_total >= 10 else None
    week_opus_ratio = (week["opus"] / week_total) if week_total >= 30 else None
    suspicious = False
    dropped_ratio = 0.0
    if today_opus_ratio is not None and week_opus_ratio is not None:
        # Flag a likely fallback when today's Opus share is >25 pp below the
        # trailing week AND the baseline was at least 20% — below that the user
        # probably wasn't using Opus much to begin with.
        if week_opus_ratio >= 0.20 and (week_opus_ratio - today_opus_ratio) > 0.25:
            suspicious = True
            dropped_ratio = week_opus_ratio - today_opus_ratio
    return {
        "suspicious": suspicious,
        "today": today,
        "week": week,
        "todayOpusRatio": round(today_opus_ratio, 3) if today_opus_ratio is not None else None,
        "weekOpusRatio": round(week_opus_ratio, 3) if week_opus_ratio is not None else None,
        "gap": round(dropped_ratio, 3),
    }


def compute_cost_projection(today_cost_usd, burn_rate, credits_usd, session_reset_minutes, weekly_reset_label):
    """Project USD spend until next weekly reset and estimate credit runway.

    Uses output tokens/hour at current model mix as a stand-in. If the user has
    no credits configured, runway is None (widget hides the field).
    """
    # Use 2h burn-rate output as the forward estimate.
    hourly_output = (burn_rate or {}).get("output_per_hour", 0) or 0
    # Translate tokens/hour to USD/hour assuming Sonnet-priced output at $15/Mtok
    # as a neutral average — undercounts Opus-heavy users, overcounts Haiku-heavy.
    usd_per_hour = hourly_output / 1_000_000 * 15.0
    # Hours until the weekly cap resets (rough: 7d − minutes already consumed).
    hours_to_week_reset = max(1, int((7 * 24) * 0.5))  # conservative 3.5 days
    projected_week_usd = round(usd_per_hour * hours_to_week_reset, 2)
    runway_hours = None
    if credits_usd and usd_per_hour > 0.01:
        runway_hours = credits_usd / usd_per_hour
    return {
        "todayUSD": round(today_cost_usd, 2),
        "usdPerHour": round(usd_per_hour, 3),
        "projectedWeekUSD": projected_week_usd,
        "runwayHours": round(runway_hours, 1) if runway_hours is not None else None,
        "runwayDays": round(runway_hours / 24, 2) if runway_hours is not None else None,
    }


def calculate_error_rate(hours=2):
    """Count API errors in recent JSONL files (429, 529, overloaded, etc.)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    mtime_cutoff = (cutoff - timedelta(hours=1)).timestamp()
    errors = {"rate_limit": 0, "overloaded": 0, "server_error": 0, "other": 0, "total": 0}

    projects_dir = CLAUDE_DIR / "projects"
    if not projects_dir.exists():
        return errors

    for jsonl_file in projects_dir.rglob("*.jsonl"):
        try:
            if jsonl_file.stat().st_mtime < mtime_cutoff:
                continue
        except OSError:
            continue
        try:
            with open(jsonl_file, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if '"api_error"' not in line and '"error"' not in line:
                        continue
                    try:
                        record = json.loads(line.strip())
                    except json.JSONDecodeError:
                        continue
                    ts = record.get("timestamp")
                    rec_date = parse_timestamp(ts) if ts else None
                    if not rec_date or rec_date < cutoff:
                        continue
                    if record.get("subtype") != "api_error" and record.get("type") != "system":
                        continue
                    err = record.get("error", {})
                    status = err.get("status", 0)
                    nested = err.get("error", {}).get("error", {})
                    err_type = str(nested.get("type", ""))

                    errors["total"] += 1
                    if status == 429 or "rate_limit" in err_type:
                        errors["rate_limit"] += 1
                    elif status == 529 or "overloaded" in err_type:
                        errors["overloaded"] += 1
                    elif status >= 500:
                        errors["server_error"] += 1
                    else:
                        errors["other"] += 1
        except (PermissionError, OSError):
            continue
    return errors


def calculate_burn_rate():
    """Token consumption rate (tokens/hour) for rolling 2h window."""
    now = datetime.now(timezone.utc)
    two_h = now - timedelta(hours=2)
    tokens, _, _, _ = parse_sessions_in_window(two_h, now)
    total_output = sum(t["output"] for t in tokens.values())
    total_all = sum(
        t["input"] + t["output"] + t["cache_read"] + t["cache_create"]
        for t in tokens.values()
    )
    return {
        "output_per_hour": round(total_output / 2),
        "total_per_hour": round(total_all / 2),
    }


def compute_dumbness_score(
    service_status,
    session_pct,
    error_rate,
    adaptive_config,
    weekly_all_pct=0,
    weekly_sonnet_pct=0,
    weekly_opus_pct=0,
    weekly_design_pct=0,
    burn_rate=None,
    latency=None,
):
    """Composite 'dumbness' score: 0 (genius) to 100 (braindead).

    Multi-parameter, continuous-curve scoring. Factors (max 100):
      - Service health             0-30   from status.claude.com
      - Session utilization        0-20   (pct/100)^1.2 * 20 — ramps smoothly
      - Weekly all-models          0-12   (pct/100)^1.1 * 12
      - Weekly Sonnet              0-8    linear pressure above 30%
      - API errors (2h)            0-15   1.8 pts per error, capped
      - Response latency           0-10   degraded feel if consistently slow
      - Burn-rate panic            0-7    session projected to cap before reset
      - Adaptive thinking ON       0-5    tends to produce lazy responses
      - 1M context OFF             0-2    milder penalty
      - Active incidents hint      0-3    "investigating" status even without impact

    Level thresholds are tight on the genius side so a perfectly idle state is
    the only way to hit it; most working sessions land in smart/slow.
    """
    score = 0.0
    reasons = []

    # ── 1. Service health (0-30) ──────────────────────────────────────────
    ind = "none"
    active_incidents = 0
    if service_status:
        ind = service_status.get("indicator", "none")
        active_incidents = len(service_status.get("active_incidents", []))
    if ind == "critical":
        score += 30; reasons.append("Critical outage")
    elif ind == "major":
        score += 22; reasons.append("Major outage")
    elif ind == "minor":
        score += 11; reasons.append("Degraded service")
    elif active_incidents > 0:
        score += 3; reasons.append(f"{active_incidents} incident(s) investigating")

    # ── 2. Session utilization (0-20) ─────────────────────────────────────
    if session_pct > 0:
        pts = min(20.0, (session_pct / 100.0) ** 1.2 * 20.0)
        score += pts
        if session_pct >= 80:
            reasons.append(f"Session {session_pct:.0f}% — near cap")
        elif session_pct >= 50:
            reasons.append(f"Session {session_pct:.0f}%")

    # ── 3. Weekly all-models (0-12) ───────────────────────────────────────
    if weekly_all_pct > 0:
        pts = min(12.0, (weekly_all_pct / 100.0) ** 1.1 * 12.0)
        score += pts
        if weekly_all_pct >= 70:
            reasons.append(f"Weekly {weekly_all_pct:.0f}%")

    # ── 4. Per-model weekly pressure (Sonnet/Opus/Design) (0-8 combined) ──
    model_pressure = 0.0
    if weekly_sonnet_pct > 30:
        model_pressure += (weekly_sonnet_pct - 30) / 8.75
        if weekly_sonnet_pct >= 60:
            reasons.append(f"Sonnet weekly {weekly_sonnet_pct:.0f}%")
    if weekly_opus_pct > 30:
        model_pressure += (weekly_opus_pct - 30) / 8.75
        if weekly_opus_pct >= 60:
            reasons.append(f"Opus weekly {weekly_opus_pct:.0f}%")
    if weekly_design_pct > 30:
        model_pressure += (weekly_design_pct - 30) / 8.75
        if weekly_design_pct >= 60:
            reasons.append(f"Design weekly {weekly_design_pct:.0f}%")
    score += min(8.0, model_pressure)

    # ── 5. API errors in 2h window (0-15) ─────────────────────────────────
    total_err = error_rate.get("total", 0) if error_rate else 0
    rate_limit_err = error_rate.get("rate_limit", 0) if error_rate else 0
    if total_err > 0:
        # Rate-limit errors are 2x as painful as generic ones
        weighted = total_err + rate_limit_err
        pts = min(15.0, weighted * 1.8)
        score += pts
        if total_err >= 5:
            reasons.append(f"{total_err} errors/2h")
        elif total_err >= 2:
            reasons.append(f"{total_err} errors/2h")

    # ── 6. Response latency (0-10) ────────────────────────────────────────
    if latency:
        avg = latency.get("avgSeconds", 0)
        sample = latency.get("sampleSize", 0)
        if sample >= 5 and avg > 0:
            # 8s = 0, 12s = 3, 18s = 7, 25s+ = 10
            if avg > 25:
                pts = 10.0
            elif avg > 8:
                pts = min(10.0, (avg - 8) * 0.7)
            else:
                pts = 0.0
            score += pts
            if avg > 18:
                reasons.append(f"Slow responses ({avg:.0f}s avg)")

    # ── 7. Burn-rate panic (0-7) ──────────────────────────────────────────
    if burn_rate and session_pct > 0:
        output_per_h = burn_rate.get("output_per_hour", 0)
        # High burn + already stressed session = panic. Weight smoothly.
        if output_per_h > 200_000 and session_pct > 30:
            panic = min(7.0, (session_pct - 30) / 10.0 + (output_per_h - 200_000) / 300_000)
            if panic > 0:
                score += panic
                if panic >= 4:
                    reasons.append("High burn rate — limit approaching fast")

    # ── 8. Config penalties ───────────────────────────────────────────────
    if adaptive_config and adaptive_config.get("adaptive_thinking", True):
        score += 5; reasons.append("Adaptive thinking ON (lazy responses)")
    if adaptive_config and not adaptive_config.get("context_1m", True):
        score += 2; reasons.append("1M context OFF")

    score = min(100, int(round(score)))

    # Tight genius band so even light activity moves the needle.
    if score < 5:
        level = "genius"
    elif score < 20:
        level = "smart"
    elif score < 45:
        level = "slow"
    elif score < 70:
        level = "dumb"
    else:
        level = "braindead"

    return {"score": score, "level": level, "reasons": reasons}


def calculate_latency(hours=2):
    """Average response latency (seconds) from user→assistant timestamp gaps."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    mtime_cutoff = (cutoff - timedelta(hours=1)).timestamp()
    gaps = []

    projects_dir = CLAUDE_DIR / "projects"
    if not projects_dir.exists():
        return {"avgSeconds": 0, "sampleSize": 0}

    for jsonl_file in projects_dir.rglob("*.jsonl"):
        if "subagents" in str(jsonl_file):
            continue
        try:
            if jsonl_file.stat().st_mtime < mtime_cutoff:
                continue
        except OSError:
            continue
        try:
            last_user_ts = None
            with open(jsonl_file, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = record.get("timestamp")
                    rec_date = parse_timestamp(ts) if ts else None
                    if not rec_date or rec_date < cutoff:
                        last_user_ts = None
                        continue
                    role = record.get("message", {}).get("role", "") or record.get("type", "")
                    if role == "user":
                        last_user_ts = rec_date
                    elif role == "assistant" and last_user_ts:
                        delta = (rec_date - last_user_ts).total_seconds()
                        if 0.5 < delta < 300:  # reasonable range
                            gaps.append(delta)
                        last_user_ts = None
                    if len(gaps) >= 50:
                        break
        except (PermissionError, OSError):
            continue
        if len(gaps) >= 50:
            break

    avg = round(sum(gaps) / len(gaps), 1) if gaps else 0
    return {"avgSeconds": avg, "sampleSize": len(gaps)}


def calculate_streak():
    """Count consecutive days with Claude usage ending today."""
    stats = load_stats_cache()
    active_dates = set()
    if stats:
        for d in stats.get("dailyActivity", []):
            if d.get("sessionCount", 0) > 0:
                active_dates.add(d["date"])

    today = datetime.now().strftime("%Y-%m-%d")
    # Today might not be in stats-cache yet, check if we have sessions
    # (caller will pass today_has_sessions flag)
    return active_dates, today


def _compute_streak(active_dates, today, today_has_sessions):
    """Walk backwards counting consecutive active days."""
    if today_has_sessions:
        active_dates.add(today)
    streak = 0
    d = datetime.now()
    for _ in range(365):
        date_str = d.strftime("%Y-%m-%d")
        if date_str in active_dates:
            streak += 1
        else:
            break
        d -= timedelta(days=1)
    return {"days": streak, "includesToday": today_has_sessions}


def predict_limit_eta(session_pct, reset_minutes):
    """Predict when session limit will hit 100% at current rate."""
    if session_pct <= 0 or session_pct >= 100:
        return None
    elapsed = (5 * 60) - reset_minutes  # minutes into the 5h window
    if elapsed <= 5:
        return None  # not enough data
    rate_per_min = session_pct / elapsed
    if rate_per_min <= 0:
        return None
    minutes_to_100 = int((100 - session_pct) / rate_per_min)
    if minutes_to_100 > 600:
        return None  # too far away to be useful
    if minutes_to_100 >= 60:
        label = f"~{minutes_to_100 // 60}h {minutes_to_100 % 60}m"
    else:
        label = f"~{minutes_to_100}m"
    return {"minutesToLimit": minutes_to_100, "label": label}


def get_claude_code_version():
    """Get installed Claude Code version."""
    import subprocess as _sp
    try:
        r = _sp.run(["claude", "--version"], capture_output=True, text=True, timeout=3)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().split("\n")[0].strip()
    except Exception:
        pass
    return ""


def build_rate_limits():
    """Fetch rate limits from Claude.ai API (real data).

    Falls back to local estimates if API is unavailable.
    """
    now = datetime.now(timezone.utc)

    # Try real API first
    api_data = fetch_usage_from_api()
    credits_data = fetch_credits_from_api()

    if api_data:
        five_hour = api_data.get("five_hour") or {}
        seven_day = api_data.get("seven_day") or {}

        # Calculate reset time (parse_timestamp handles Z suffix on Python < 3.11)
        reset_dt = parse_timestamp(five_hour.get("resets_at", ""))
        reset_minutes = max(0, int((reset_dt - now).total_seconds() / 60)) if reset_dt else 0

        # Weekly all models reset
        wr_dt = parse_timestamp(seven_day.get("resets_at", ""))
        weekly_reset_label = wr_dt.strftime("%a %I:%M %p") if wr_dt else ""

        def _weekly_block(payload):
            """Shape a seven_day_* entry. Returns None if the API omitted it (null)."""
            if not payload:
                return None
            d = parse_timestamp(payload.get("resets_at", ""))
            return {
                "percentUsed": payload.get("utilization", 0) or 0,
                "resetsLabel": d.strftime("%a %I:%M %p") if d else "",
            }

        # weeklySonnet is always present for backward compatibility with existing
        # consumers (QML, Tauri JS) that read rateLimits.weeklySonnet
        # directly. It defaults to 0% when the API returned null.
        sonnet_payload = api_data.get("seven_day_sonnet") or {}
        ss_dt = parse_timestamp(sonnet_payload.get("resets_at", ""))
        result = {
            "session": {
                "percentUsed": five_hour.get("utilization", 0) or 0,
                "resetsInMinutes": reset_minutes,
                "windowHours": 5,
                # detect_usage_transitions() compares resetsAt across runs to
                # fire sessionReset; without it that event can never trigger.
                "resetsAt": five_hour.get("resets_at", "") or "",
            },
            "weeklyAll": {
                "percentUsed": seven_day.get("utilization", 0) or 0,
                "resetsLabel": weekly_reset_label,
                "resetsAt": seven_day.get("resets_at", ""),
            },
            "weeklySonnet": {
                "percentUsed": sonnet_payload.get("utilization", 0) or 0,
                "resetsLabel": ss_dt.strftime("%a %I:%M %p") if ss_dt else "",
            },
            "plan": "Max (20x)",
            "source": "api",
        }

        # New per-model weekly blocks (Opus, Claude Design/omelette, OAuth apps,
        # Cowork). Each is omitted when the API returned null so consumers can
        # check `if "weeklyOpus" in rateLimits` cleanly without confusing a real
        # zero with an unavailable metric.
        weekly_opus = _weekly_block(api_data.get("seven_day_opus"))
        if weekly_opus:
            result["weeklyOpus"] = weekly_opus
        weekly_fable = _weekly_block(api_data.get("seven_day_fable"))
        if weekly_fable:
            result["weeklyFable"] = weekly_fable
        # "omelette" is Anthropic's internal codename for the Claude Design surface.
        weekly_design = _weekly_block(api_data.get("seven_day_omelette"))
        if weekly_design:
            result["weeklyDesign"] = weekly_design
        weekly_oauth_apps = _weekly_block(api_data.get("seven_day_oauth_apps"))
        if weekly_oauth_apps:
            result["weeklyOauthApps"] = weekly_oauth_apps
        # "cowork" covers the Claude Code teams / collaboration tier when active.
        weekly_cowork = _weekly_block(api_data.get("seven_day_cowork"))
        if weekly_cowork:
            result["weeklyCowork"] = weekly_cowork

        # Per-model weekly quota, from the unified `limits` array (2026 schema).
        # The legacy seven_day_* fields are being deprecated to null; per-model
        # caps now arrive as entries with kind "weekly_scoped" carrying
        # scope.model.display_name.
        #
        # Two consumers with different needs, so each entry feeds both:
        #  - rateLimits.weekly<Model> — UIs that bind a widget to a fixed model
        #    family (the QML plasmoid's fableBarOnly mode reads weeklyFable).
        #    Covers N models per response.
        #  - rateLimits.weeklyScoped — model-agnostic, labelled by the API
        #    itself, so a model we have no field for still surfaces instead of
        #    being dropped. Holds the first scoped entry.
        MODEL_FIELD = {"opus": "weeklyOpus", "sonnet": "weeklySonnet",
                       "fable": "weeklyFable", "haiku": "weeklyHaiku"}
        for entry in (api_data.get("limits") or []):
            if entry.get("kind") != "weekly_scoped":
                continue
            model = ((entry.get("scope") or {}).get("model") or {})
            display = (model.get("display_name") or "").strip()
            d = parse_timestamp(entry.get("resets_at", ""))
            block = {
                "percentUsed": entry.get("percent", 0) or 0,
                "modelName": display,
                "resetsLabel": d.strftime("%a %I:%M %p") if d else "",
                "resetsAt": entry.get("resets_at", "") or "",
            }
            # Substring match: display_name may be the bare family ("Fable")
            # or a full model name ("Claude Fable 5") depending on API version.
            name = display.lower()
            field = next((f for k, f in MODEL_FIELD.items() if k in name), None)
            if field:
                result[field] = block
            # First scoped entry wins; later ones keep their named field only.
            result.setdefault("weeklyScoped", block)

        # Inline extra_usage summary (the `usage` endpoint also carries a quick
        # snapshot; the full shape lives under overage_spend_limit below).
        inline_eu = api_data.get("extra_usage") or {}
        if inline_eu.get("is_enabled"):
            result["extraUsageInline"] = {
                "enabled": True,
                "monthlyLimit": (inline_eu.get("monthly_limit") or 0) / 100,
                "usedCredits": (inline_eu.get("used_credits") or 0) / 100,
                "utilization": inline_eu.get("utilization") or 0,
                "currency": inline_eu.get("currency") or "USD",
            }

        # Add credits info (full details)
        if credits_data:
            amount = credits_data.get("amount") or 0
            currency = credits_data.get("currency") or "USD"
            auto_reload = credits_data.get("auto_reload_settings")
            pending = credits_data.get("pending_invoice_amount_cents")
            result["credits"] = {
                "amount": amount / 100,
                "currency": currency,
                "autoReload": auto_reload is not None,
                "autoReloadSettings": auto_reload,
                "pendingInvoice": (pending / 100) if pending else 0,
            }

        # Extra usage / overage
        overage = fetch_overage_data()
        if overage:
            result["extraUsage"] = overage

        return result

    # Fallback: estimate from local data
    five_h_cutoff = now - timedelta(hours=5)
    five_h_tokens, _, _, _ = parse_sessions_in_window(five_h_cutoff, now)
    five_h_output = compute_window_output_tokens(five_h_tokens)

    week_cutoff = now - timedelta(days=7)
    week_tokens, _, _, week_per_model = parse_sessions_in_window(week_cutoff, now)
    week_output = compute_window_output_tokens(week_tokens)
    week_sonnet_output = compute_window_output_tokens(week_per_model.get("sonnet", {}))
    week_opus_output = compute_window_output_tokens(week_per_model.get("opus", {}))
    week_fable_output = compute_window_output_tokens(week_per_model.get("fable", {}))

    SESSION_LIMIT = 4_000_000
    WEEKLY_ALL_LIMIT = 40_000_000
    WEEKLY_SONNET_LIMIT = 80_000_000
    # Opus is the scarcest quota on Max plans; Fable shares Sonnet-class limits.
    WEEKLY_OPUS_LIMIT = 20_000_000
    WEEKLY_FABLE_LIMIT = 80_000_000

    def _weekly_pct(output_tokens, limit):
        return round(min(100, output_tokens / limit * 100), 1)

    return {
        "session": {
            "percentUsed": round(min(100, five_h_output / SESSION_LIMIT * 100), 1),
            "resetsInMinutes": 300,
            "windowHours": 5,
        },
        "weeklyAll": {
            "percentUsed": _weekly_pct(week_output, WEEKLY_ALL_LIMIT),
            "resetsLabel": "",
        },
        "weeklySonnet": {
            "percentUsed": _weekly_pct(week_sonnet_output, WEEKLY_SONNET_LIMIT),
            "resetsLabel": "",
        },
        "weeklyOpus": {
            "percentUsed": _weekly_pct(week_opus_output, WEEKLY_OPUS_LIMIT),
            "resetsLabel": "",
        },
        "weeklyFable": {
            "percentUsed": _weekly_pct(week_fable_output, WEEKLY_FABLE_LIMIT),
            "resetsLabel": "",
        },
        "plan": "Max (20x)",
        "source": "local_estimate",
    }


def compute_daily_trend(days=8):
    """Per-day total tokens + message/session counts for the last `days` days,
    computed directly from the JSONL logs.

    stats-cache.json's dailyModelTokens can lag several days behind the live
    logs, which left the 7-day chart flat. Reading JSONL keeps it current.
    """
    now_local = datetime.now()
    start_utc = datetime.now(timezone.utc) - timedelta(days=days)
    buckets = defaultdict(lambda: {"tokens": 0, "messages": 0, "sessions": set()})

    for jsonl_file in _jsonl_files_newer_than(start_utc):
        is_sub = "subagents" in str(jsonl_file)
        sid = jsonl_file.stem
        try:
            with open(jsonl_file, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = r.get("timestamp")
                    d = parse_timestamp(ts) if ts else None
                    if not d or d < start_utc:
                        continue
                    day = d.astimezone().strftime("%Y-%m-%d")
                    msg = r.get("message", {})
                    usage = msg.get("usage", {})
                    if usage:
                        buckets[day]["tokens"] += (
                            usage.get("input_tokens", 0)
                            + usage.get("output_tokens", 0)
                            + usage.get("cache_read_input_tokens", 0)
                            + usage.get("cache_creation_input_tokens", 0)
                        )
                    if not is_sub and msg.get("role") == "assistant":
                        buckets[day]["messages"] += 1
                    if not is_sub:
                        buckets[day]["sessions"].add(sid)
        except (PermissionError, OSError):
            continue

    trend = []
    for i in range(days - 1, -1, -1):
        dt = now_local - timedelta(days=i)
        key = dt.strftime("%Y-%m-%d")
        b = buckets.get(key)
        trend.append({
            "date": key,
            "label": dt.strftime("%a"),
            "tokens": b["tokens"] if b else 0,
            "messages": b["messages"] if b else 0,
            "sessions": len(b["sessions"]) if b else 0,
        })
    return trend


def build_widget_data():
    """Build the complete widget data JSON."""
    stats = load_stats_cache()
    now = datetime.now(timezone.utc)

    # Today's data (midnight UTC to now)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_tokens, today_sessions, today_msg_count, _ = parse_sessions_in_window(today_start, now)

    # Rate limits
    rate_limits = build_rate_limits()

    # Service health from status.claude.com
    service_status = fetch_service_status()
    notify_status_change(service_status)

    # New metrics
    error_rate = calculate_error_rate()
    burn_rate = calculate_burn_rate()
    adaptive_config = detect_adaptive_thinking()
    session_pct = rate_limits.get("session", {}).get("percentUsed", 0)
    reset_mins = rate_limits.get("session", {}).get("resetsInMinutes", 0)
    weekly_all_pct = rate_limits.get("weeklyAll", {}).get("percentUsed", 0)
    weekly_sonnet_pct = rate_limits.get("weeklySonnet", {}).get("percentUsed", 0)
    weekly_opus_pct = (rate_limits.get("weeklyOpus") or {}).get("percentUsed", 0)
    weekly_design_pct = (rate_limits.get("weeklyDesign") or {}).get("percentUsed", 0)
    latency = calculate_latency()
    dumbness = compute_dumbness_score(
        service_status, session_pct, error_rate, adaptive_config,
        weekly_all_pct=weekly_all_pct,
        weekly_sonnet_pct=weekly_sonnet_pct,
        weekly_opus_pct=weekly_opus_pct,
        weekly_design_pct=weekly_design_pct,
        burn_rate=burn_rate,
        latency=latency,
    )
    active_dates, today_str = calculate_streak()
    limit_eta = predict_limit_eta(session_pct, reset_mins)
    cc_version = get_claude_code_version()

    # New signals (all best-effort — degrade to empty when data is missing)
    settings_summary = read_claude_settings_summary() or {}
    mcp_auth_pending = read_mcp_auth_pending()
    tool_use = calculate_tool_use()
    compaction = calculate_compaction_events()
    opus_fallbacks = detect_opus_fallbacks()

    # Today's summary
    today_total_input = 0
    today_total_output = 0
    today_total_cache_read = 0
    today_total_cache_create = 0
    today_total_cost = 0.0
    model_breakdown = []

    for model, tokens in today_tokens.items():
        display = MODEL_DISPLAY.get(model, model.split("-")[1].title() if "-" in model else model)
        color = MODEL_COLORS.get(display, "#9CA3AF")
        cost = calculate_cost(model, tokens["input"], tokens["output"], tokens["cache_read"], tokens["cache_create"])
        total_tokens = tokens["input"] + tokens["output"] + tokens["cache_read"] + tokens["cache_create"]

        today_total_input += tokens["input"]
        today_total_output += tokens["output"]
        today_total_cache_read += tokens["cache_read"]
        today_total_cache_create += tokens["cache_create"]
        today_total_cost += cost

        model_breakdown.append({
            "model": display,
            "color": color,
            "input": tokens["input"],
            "output": tokens["output"],
            "cacheRead": tokens["cache_read"],
            "cacheCreate": tokens["cache_create"],
            "totalTokens": total_tokens,
            "cost": round(cost, 4),
        })

    # Sort by cost descending
    model_breakdown.sort(key=lambda x: x["cost"], reverse=True)

    # Calculate percentages
    grand_total_tokens = sum(m["totalTokens"] for m in model_breakdown)
    for m in model_breakdown:
        m["percentage"] = round((m["totalTokens"] / grand_total_tokens * 100) if grand_total_tokens > 0 else 0, 1)

    # 7-day trend computed from JSONL. stats-cache.json's dailyModelTokens can
    # lag days behind the live logs (leaving the chart flat), so we read the
    # JSONL directly to reflect real recent activity.
    trend_7d = compute_daily_trend()

    # Lifetime stats
    lifetime = {}
    if stats:
        lifetime = {
            "totalSessions": stats.get("totalSessions", 0),
            "totalMessages": stats.get("totalMessages", 0),
            "firstSession": stats.get("firstSessionDate", ""),
            "longestSession": stats.get("longestSession", {}),
            "peakHours": stats.get("hourCounts", {}),
            # New: speculative-decoding time saved across all sessions. The
            # field is provided by Claude Code itself; we just surface it.
            "speculationTimeSavedMs": stats.get("totalSpeculationTimeSavedMs", 0) or 0,
        }

        lifetime_cost = 0.0
        model_usage = stats.get("modelUsage", {})
        for model, usage in model_usage.items():
            lifetime_cost += calculate_cost(
                model,
                usage.get("inputTokens", 0),
                usage.get("outputTokens", 0),
                usage.get("cacheReadInputTokens", 0),
                usage.get("cacheCreationInputTokens", 0),
            )
        lifetime["totalCostUSD"] = round(lifetime_cost, 2)

        total_lt = sum(
            u.get("inputTokens", 0) + u.get("outputTokens", 0)
            + u.get("cacheReadInputTokens", 0) + u.get("cacheCreationInputTokens", 0)
            for u in model_usage.values()
        )
        lifetime["totalTokens"] = total_lt

    # Cache efficiency
    cache_total = today_total_cache_read + today_total_cache_create + today_total_input
    cache_hit_rate = (today_total_cache_read / cache_total * 100) if cache_total > 0 else 0

    # Cost projection (needs today_total_cost above and credits from rate_limits)
    credits_block = rate_limits.get("credits") or {}
    credits_amount_usd = credits_block.get("amount") or 0
    cost_projection = compute_cost_projection(
        today_cost_usd=today_total_cost,
        burn_rate=burn_rate,
        credits_usd=credits_amount_usd,
        session_reset_minutes=reset_mins,
        weekly_reset_label=rate_limits.get("weeklyAll", {}).get("resetsLabel", ""),
    )

    widget_data = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "rateLimits": rate_limits,
        "today": {
            "inputTokens": today_total_input,
            "outputTokens": today_total_output,
            "cacheReadTokens": today_total_cache_read,
            "cacheCreateTokens": today_total_cache_create,
            "totalTokens": today_total_input + today_total_output + today_total_cache_read + today_total_cache_create,
            "costUSD": round(today_total_cost, 4),
            "messages": today_msg_count,
            "sessions": len(today_sessions),
            "cacheHitRate": round(cache_hit_rate, 1),
        },
        "modelBreakdown": model_breakdown,
        "sessions": sorted(today_sessions, key=lambda s: s.get("start", ""), reverse=True)[:10],
        "trend7d": trend_7d,
        "lifetime": lifetime,
        "serviceStatus": service_status,
        "errorRate": error_rate,
        "burnRate": burn_rate,
        "adaptiveThinking": adaptive_config,
        "dumbness": dumbness,
        "latency": latency,
        "responseQuality": {
            "avgTokensPerResponse": round(today_total_output / today_msg_count) if today_msg_count > 0 else 0,
            "totalResponses": today_msg_count,
        },
        "streak": _compute_streak(active_dates, today_str, len(today_sessions) > 0),
        "limitEta": limit_eta,
        "claudeCodeVersion": cc_version,
        # New — each block is either a populated dict/list or empty/None so
        # consumers can short-circuit with `if data.settings` etc.
        "settings": settings_summary,
        "mcpAuthPending": mcp_auth_pending,
        "toolUse": tool_use,
        "compaction": compaction,
        "opusFallbacks": opus_fallbacks,
        "costProjection": cost_projection,
    }

    return widget_data


TEST_STATES = {
    "genius":    {"score": 5,  "level": "genius",    "reasons": []},
    "smart":     {"score": 15, "level": "smart",     "reasons": ["Adaptive thinking OFF"]},
    "slow":      {"score": 35, "level": "slow",      "reasons": ["Degraded service", "3 errors/2h"]},
    "dumb":      {"score": 60, "level": "dumb",      "reasons": ["Degraded service", "Session >80%", "5 errors/2h"]},
    "braindead": {"score": 85, "level": "braindead",  "reasons": ["Critical outage", "Session >90%", "12 errors/2h", "Adaptive thinking OFF"]},
}


def run_health_check():
    """Diagnose cookie extraction end-to-end and print a structured report.

    Exit 0 if we can reach the live API, 1 otherwise.
    Designed to be called by installers or manually by users after install.
    """
    import platform
    report = {
        "ok": False,
        "source": None,
        "firefox": {"present": False, "cookies": 0, "hasSessionKey": False, "reason": None},
        "chrome":  {"present": False, "cookies": 0, "decrypted": 0, "keyStrategy": None, "reason": None},
        "winner": None,
        "advice": [],
    }

    # ── Firefox: inspect DB directly (fast, plain text) ──
    import sqlite3, shutil, tempfile
    firefox_dirs = [
        Path.home() / ".mozilla" / "firefox",
        Path.home() / "snap" / "firefox" / "common" / ".mozilla" / "firefox",
        Path.home() / ".var" / "app" / "org.mozilla.firefox" / ".mozilla" / "firefox",
    ]
    if platform.system() == "Windows":
        firefox_dirs.insert(0, Path(os.environ.get("APPDATA", Path.home())) / "Mozilla" / "Firefox" / "Profiles")
    elif platform.system() == "Darwin":
        firefox_dirs.insert(0, Path.home() / "Library" / "Application Support" / "Firefox" / "Profiles")

    ff_cookies = _get_firefox_cookies()
    for fd in firefox_dirs:
        if fd.exists():
            report["firefox"]["present"] = True
            break
    if ff_cookies:
        report["firefox"]["cookies"] = ff_cookies.count("=") + (1 if ff_cookies and not ff_cookies.endswith("=") else 0)
        report["firefox"]["cookies"] = len(ff_cookies.split("; "))
        report["firefox"]["hasSessionKey"] = "sessionKey=" in ff_cookies
        if not report["firefox"]["hasSessionKey"]:
            report["firefox"]["reason"] = "cookies present but no sessionKey (not logged in or session expired)"
    elif report["firefox"]["present"]:
        report["firefox"]["reason"] = "profile exists but no claude.ai cookies found"

    # ── Chrome: parallel path that tracks which key strategy wins ──
    is_mac = platform.system() == "Darwin"
    if is_mac:
        asup = Path.home() / "Library" / "Application Support"
        chrome_bases = [asup / "Google" / "Chrome", asup / "Chromium",
                        asup / "BraveSoftware" / "Brave-Browser"]
    else:
        chrome_bases = [Path.home() / ".config" / "google-chrome",
                        Path.home() / ".config" / "chromium",
                        Path.home() / "snap" / "chromium" / "common" / "chromium",
                        Path.home() / ".var" / "app" / "com.google.Chrome" / "config" / "google-chrome",
                        Path.home() / ".var" / "app" / "org.chromium.Chromium" / "config" / "chromium"]
    for cb in chrome_bases:
        if cb.exists():
            report["chrome"]["present"] = True
            chrome_base = cb
            break
    else:
        chrome_base = None

    ch_cookies = _get_chrome_cookies()
    if ch_cookies:
        report["chrome"]["decrypted"] = len(ch_cookies.split("; "))
        report["chrome"]["cookies"] = report["chrome"]["decrypted"]
        report["chrome"]["hasSessionKey"] = "sessionKey=" in ch_cookies
        # Detect which key strategy actually worked, for diagnostic output
        if chrome_base:
            primary = _get_chrome_key(chrome_base, is_mac=is_mac)
            import hashlib as _h
            peanuts = _h.pbkdf2_hmac("sha1", b"peanuts", b"saltysalt", 1003 if is_mac else 1, dklen=16)
            report["chrome"]["keyStrategy"] = "peanuts-fallback" if primary != peanuts else "peanuts"
            # If primary isn't peanuts but the fallback recovered cookies, that's the stale-keyring case
            if primary != peanuts:
                # Test primary key against the first encrypted cookie to see if it actually works
                try:
                    import tempfile as _tf
                    db = chrome_base / "Default" / "Cookies"
                    if db.exists():
                        with _tf.NamedTemporaryFile(delete=False, suffix=".sqlite") as t:
                            shutil.copy2(db, t.name)
                            for suf in ("-wal","-shm","-journal"):
                                s = Path(str(db)+suf)
                                if s.exists(): shutil.copy2(s, t.name+suf)
                            cx = sqlite3.connect(t.name)
                            row = cx.execute("SELECT encrypted_value FROM cookies WHERE host_key LIKE '%claude.ai%' AND encrypted_value IS NOT NULL LIMIT 1").fetchone()
                            cx.close()
                        for suf in ("","-wal","-shm","-journal"):
                            Path(t.name+suf).unlink(missing_ok=True)
                        if row and _decrypt_chrome_value(row[0], primary):
                            report["chrome"]["keyStrategy"] = "keyring"
                        else:
                            report["chrome"]["keyStrategy"] = "peanuts-fallback"
                            report["chrome"]["reason"] = "stale keyring entry — Chrome is using basic/peanuts encryption (common on KDE/Wayland when XDG portal fails)"
                except Exception:
                    pass
    elif report["chrome"]["present"]:
        report["chrome"]["reason"] = "profile exists but no claude.ai cookies decrypted"

    # ── Determine winner & API source ──
    cookies = get_claude_cookies()
    if cookies and "sessionKey=" in cookies:
        # Match which browser produced the winning cookies (Firefox is tried first)
        if ff_cookies and "sessionKey=" in ff_cookies:
            report["winner"] = "firefox"
        else:
            report["winner"] = "chrome"
        # Try hitting the API to confirm credentials aren't rejected
        try:
            # reuse existing rate_limits builder — source=='api' means it worked
            rl = build_rate_limits()
            report["source"] = rl.get("source", "local_estimate")
            report["ok"] = report["source"] == "api"
        except Exception as e:
            # Reaching this branch means the API responded but our code crashed
            # processing the payload — it's a collector bug, not an auth problem.
            report["source"] = "local_estimate"
            report["collectorError"] = f"{type(e).__name__}: {e}"
            report["advice"].append(
                f"Collector bug (not an auth failure): {type(e).__name__}: {e}. "
                "Please report this at https://github.com/MrSchrodingers/usage-buddies/issues "
                "with the output of: usage-buddies-collector.py --verbose"
            )
    else:
        report["source"] = "local_estimate"

    # ── Build actionable advice ──
    if report["ok"]:
        report["advice"].append(f"Live API reachable via {report['winner']}.")
    else:
        if not report["firefox"]["present"] and not report["chrome"]["present"]:
            report["advice"].append("No supported browser profile found. Install Firefox or Chrome and log in to https://claude.ai.")
        if report["firefox"]["present"] and not report["firefox"]["hasSessionKey"]:
            snap_ff_dir = Path.home() / "snap" / "firefox" / "common" / ".mozilla" / "firefox"
            native_ff_dir = Path.home() / ".mozilla" / "firefox"
            if snap_ff_dir.exists() and not native_ff_dir.exists():
                report["advice"].append(
                    "Firefox Snap detected — open https://claude.ai and sign in. "
                    "If you're already logged in and this persists, the Snap sandbox may be blocking reads; "
                    "try the native package (e.g. Mozilla PPA on Ubuntu) or use Chrome."
                )
            else:
                report["advice"].append("Firefox: open https://claude.ai and sign in (no sessionKey cookie found).")
        if report["chrome"]["present"] and report["chrome"].get("keyStrategy") == "peanuts-fallback" and report["chrome"]["decrypted"] == 0:
            report["advice"].append("Chrome: stale KWallet entry blocked decryption. Try: kwallet-query -w 'Chrome Keys' -f 'Chrome Safe Storage' kdewallet  (then restart Chrome).")
        if report["chrome"]["present"] and report["chrome"]["decrypted"] == 0 and report["chrome"].get("reason") != "stale keyring entry — Chrome is using basic/peanuts encryption (common on KDE/Wayland when XDG portal fails)":
            report["advice"].append("Chrome: cookies exist but couldn't be decrypted. Make sure Chrome is fully closed during collection, or try logging in again.")
        if report["winner"] and report["source"] != "api" and not report.get("collectorError"):
            report["advice"].append("Got cookies but API rejected them — session may be expired. Re-login at https://claude.ai.")

    # Machine-readable (stdout) — installers parse this
    if "--json" in sys.argv:
        print(json.dumps(report, indent=2))
    else:
        # Human-readable summary
        # Disable ANSI on non-TTY or NO_COLOR per spec
        use_color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        if use_color:
            GREEN, RED, AMBER, DIM, NC = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
        else:
            GREEN = RED = AMBER = DIM = NC = ""
        mark = f"{GREEN}✓{NC}" if report["ok"] else f"{AMBER}!{NC}"
        print(f"{mark} Usage Buddies Collector — health check")
        print(f"  Source: {report['source']}  Winner: {report['winner'] or 'none'}")
        for browser in ("firefox", "chrome"):
            b = report[browser]
            if not b["present"]:
                print(f"  {DIM}{browser}: not installed{NC}")
                continue
            status = GREEN+"OK"+NC if (browser == report["winner"]) else AMBER+"skipped"+NC if report["ok"] else RED+"failed"+NC
            extra = []
            if browser == "chrome" and b.get("keyStrategy"):
                extra.append(f"key={b['keyStrategy']}")
            if b.get("cookies"):
                extra.append(f"cookies={b['cookies']}")
            if b.get("decrypted") is not None and browser == "chrome":
                extra.append(f"decrypted={b['decrypted']}")
            # Only show reason when it's actually blocking us (not when fallback succeeded)
            if b.get("reason") and browser != report["winner"]:
                extra.append(f"reason={b['reason']}")
            print(f"  {browser}: {status}  ({', '.join(extra)})" if extra else f"  {browser}: {status}")
        if report["advice"]:
            print()
            for a in report["advice"]:
                print(f"  {DIM}→{NC} {a}")

    sys.exit(0 if report["ok"] else 1)


def main():
    if "--health-check" in sys.argv:
        run_health_check()
        return  # unreachable (run_health_check exits), but explicit

    if "--test-sounds" in sys.argv:
        run_test_sounds(load_config())
        return

    try:
        data = build_widget_data()

        # --test-state override for HITL testing
        for arg in sys.argv:
            if arg.startswith("--test-state="):
                state = arg.split("=", 1)[1]
                if state in TEST_STATES:
                    data["dumbness"] = TEST_STATES[state]
                    if state in ("slow", "dumb", "braindead"):
                        if not data.get("serviceStatus"):
                            data["serviceStatus"] = {"indicator": "none", "description": "", "components": [], "active_incidents": []}
                        data["serviceStatus"]["indicator"] = "minor" if state == "slow" else "major"
                        if data.get("rateLimits", {}).get("session"):
                            data["rateLimits"]["session"]["percentUsed"] = 65 if state == "slow" else 84 if state == "dumb" else 95
                        if data.get("errorRate") is not None:
                            data["errorRate"]["total"] = 3 if state == "slow" else 5 if state == "dumb" else 12

        # Atomic write with restrictive permissions
        tmp_path = str(OUTPUT_FILE) + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, OUTPUT_FILE)
        try:
            os.chmod(OUTPUT_FILE, 0o600)
        except OSError:
            pass

        # Notificações + sons em transições de sessão/semanal
        try:
            process_usage_events(data, load_config())
        except Exception as e:
            print(f"warn: process_usage_events falhou: {e}", file=sys.stderr)

        if "--verbose" in sys.argv:
            print(json.dumps(data, indent=2))
        else:
            cost = data["today"]["costUSD"]
            tokens = data["today"]["totalTokens"]
            sessions = data["today"]["sessions"]
            state_str = ""
            for arg in sys.argv:
                if arg.startswith("--test-state="):
                    state_str = f" [SIM: {arg.split('=')[1]}]"
            print(f"OK: ${cost:.2f} | {tokens:,} tokens | {sessions} sessions{state_str}")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
