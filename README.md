<div align="center">

# Usage Buddies

### KDE Plasmoid · Cross-Platform Tauri Tray · Windows Widget

**Real-time Claude AI usage limits, service health, intelligence score, and spending tracker directly in your taskbar.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![KDE Plasma 6](https://img.shields.io/badge/KDE_Plasma-6.0+-blue.svg)](https://kde.org/plasma-desktop/)
[![Tauri v2](https://img.shields.io/badge/Tauri-v2-orange.svg)](https://v2.tauri.app)
[![Windows 10/11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6.svg)](https://www.microsoft.com/windows)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-green.svg)](https://python.org)
[![Claude API](https://img.shields.io/badge/Claude-API-D97757.svg)](https://claude.ai)

<br>

<img src="screenshots/widget.gif" alt="Usage Buddies" width="427"/>

<br>

<img src="screenshots/panel.png" alt="Panel compact view"/>

</div>

---

## Three Interfaces, One Collector

| | KDE Plasmoid | Tauri Tray App | Windows Widget |
|---|---|---|---|
| **Platform** | KDE Plasma 6 (Fedora, Kubuntu, Arch) | macOS, Ubuntu GNOME, Fedora, other non-KDE Linux | Windows 10 22H2 / Windows 11 |
| **Interface** | Native QML panel widget | System tray popup (frameless) | Tray icon + frameless popup docked bottom-right |
| **Stack** | QML + Kirigami | Rust + Vite + vanilla JS | Tauri v2 (Rust + Vite + vanilla JS) |
| **Install** | `./install.sh` | `./install.sh` | Build + install (see below) |
| **Trigger** | Click panel widget | Click tray icon or `Super+Shift+C` | Click tray icon |
| **Data source** | `~/.claude/widget-data.json` | `~/.claude/widget-data.json` | `~/.claude/widget-data.json` |

All three read the same file written by the shared Python collector at `scripts/usage-buddies-collector.py`.

> **Windows Widget** (`win-widget/`) is a fresh, Windows-first build in Tauri v2 — not a port of the Linux UI. It docks a frameless popup at the bottom-right corner, opened from a tray icon, with an animated **Clawd** pixel-art mascot, a per-second session countdown, weekly limits (including the API-scoped model, e.g. **Fable**), service health, activity tiles, model distribution, a JSON-derived 7-day chart, and peak hours. It installs as a self-contained `.exe` that auto-starts on login — no vite/dev server, no admin rights.

---

## Highlights

<table>
<tr>
<td width="50%">

### Usage Monitoring
- Circular progress ring with live countdown (seconds)
- Session, weekly all-models, and per-model weekly limits (API-scoped, e.g. Fable)
- Prepaid credits balance with auto-reload status
- Extra Usage: enabled/disabled, monthly limit, used/remaining

</td>
<td width="50%">

### Intelligence Score
- Composite 0-100 "Dumbness Score" detects degradation
- 5 animated pixel art mascot states
- Factors: service health, rate limits, API errors, config
- Predictive alert: "limit in ~Xh at current rate"

</td>
</tr>
<tr>
<td>

### Service Health
- Real-time from status.claude.com (Statuspage API)
- Component status: claude.ai, Platform, API, Claude Code
- Active incident details with latest update text
- Pulsing status dot + DownDetector link

</td>
<td>

### Performance Metrics
- Token burn rate (output tokens/hour)
- API error tracking (429/529/overloaded in 2h window)
- Average response quality (tokens per response)
- Average latency (user-to-assistant response time)
- Model distribution bar (Opus/Sonnet/Haiku split)

</td>
</tr>
</table>

---

## Mascot States

The Clawd mascot changes based on Claude's performance score:

| Score | Level | Mascot | Trigger |
|:-----:|:-----:|:------:|:--------|
| 0-4 | **Genius** | Crown + sparkles | Fully idle, all services green |
| 5-19 | **Smart** | Coffee cup + steam | Normal session, light pressure |
| 20-44 | **Slow** | Rain cloud + drops | Service degraded or weekly limits ≥50% |
| 45-69 | **Dumb** | Fire flames | Major outage or rate-limit pressure |
| 70-100 | **Braindead** | Tombstone + ghost Clawd | Critical outage / session near cap / errors flooding |

### Dumbness Score Factors (multi-parameter, continuous-curve)

| Factor | Points | Source |
|--------|:------:|--------|
| Service health | 0-30 | status.claude.com indicator + active incidents |
| Session utilization | 0-20 | `(pct/100)^1.2 × 20` — smooth ramp |
| Weekly all-models | 0-12 | `(pct/100)^1.1 × 12` |
| Per-model weekly (Sonnet + Opus + Design, combined) | 0-8 | each model's `(pct − 30) / 8.75`, clamped |
| API errors in 2h window | 0-15 | Local JSONL; rate-limit errors weighted 2× |
| Response latency | 0-10 | Local JSONL; kicks in above 8s avg with ≥5 samples |
| Burn-rate panic | 0-7 | Output tokens/hour × session pressure |
| Adaptive Thinking ON | 5 | `~/.claude/settings.json` |
| 1M Context OFF | 2 | `~/.claude/settings.json` |

Genius band is deliberately tight (0-4): any realistic working session lands in **Smart** or **Slow**, not **Genius**. Levels cap at 100.

> **Why is Adaptive Thinking ON a penalty?** With Adaptive Thinking enabled, Claude sometimes allocates zero reasoning tokens on complex tasks, causing lazy/shallow responses. [Learn more](https://dev.to/shuicici/claude-codes-feb-mar-2026-updates-quietly-broke-complex-engineering-heres-the-technical-5b4h)

---

## Requirements

### KDE Plasmoid
- **KDE Plasma 6** (Fedora 40+, Kubuntu 24.04+, Arch, etc.)
- **Python 3.8+** with Pillow (`pip install pillow`)
- **Firefox, Chrome, or Chromium** logged in to [claude.ai](https://claude.ai)
- **Claude Code** installed (for local activity data)

### Tauri Tray App
- **macOS 12+** or **Linux** (Ubuntu 22.04+, Fedora 38+)
- **Rust** toolchain + **Node.js 18+**
- **Python 3.8+** for the data collector (3.11+ recommended for accurate reset timers; 3.10 supported)
- **Firefox, Chrome, or Chromium** logged in to [claude.ai](https://claude.ai)

### Windows Widget
- **Windows 10 22H2** or **Windows 11**
- **WebView2 Runtime** — preinstalled on Windows 11 and most Windows 10; the tiny Evergreen bootstrapper covers machines without it
- **Rust** toolchain + **Node.js 18+** to build; **Python 3.10+** for the collector
- **Firefox** logged in to [claude.ai](https://claude.ai) — on Windows, Chrome/Edge cookies are locked by App-Bound Encryption, so Firefox (plaintext cookies) is the reliable source. A manual cookie file at `~/.claude/widget-cookies.txt` also works.

---

## Installation

> **Upgrading from `claude-usage-widget`?** The project was renamed, so every
> artifact changed name: `usage-buddies-collector.py`, the
> `usage-buddies-collector` systemd units, the `org.kde.plasma.usagebuddies`
> plasmoid. `install.sh` detects the old install and offers to clear it — leaving
> both in place means two collectors on two timers writing the same
> `~/.claude/widget-data.json`. To do it by hand: `bash legacy/uninstall.sh`.
> Your data in `~/.claude/` is not touched by the rename.
>
> On KDE the panel references the plasmoid by ID, so the old widget disappears
> from the panel when the ID changes. Re-add it: right-click panel → Add Widgets
> → "Usage Buddies".

### Ubuntu / Debian (any desktop)

```bash
git clone https://github.com/MrSchrodingers/usage-buddies.git
cd usage-buddies
chmod +x install.sh
./install.sh
```

The installer detects your desktop environment (`XDG_CURRENT_DESKTOP`) and adapts accordingly:

| DE detected | What the installer does |
|---|---|
| **KDE** | Builds plasmoid + tray app |
| **GNOME** | Builds tray app, installs AppIndicator extension via `gnome-extensions-cli`. **Requires logout/login** afterwards. |
| **MATE / XFCE / Cinnamon** | Builds tray app (native tray, no extra setup) |
| **Hyprland / Sway** | Builds tray app (requires `waybar` tray module or equivalent) |

If the tray icon doesn't appear on GNOME after relogin:
```bash
gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com
```
Or use `Super+Shift+C` as an always-available fallback.

Every installer step prints an explicit `✓ OK`, `⚠ warning`, or `✗ failure` status — and a consolidated report at the end summarizes what worked, what was skipped with a hint, and what aborted the install. No more silent failures.

### KDE Plasmoid (Fedora, Kubuntu, Arch)

```bash
git clone https://github.com/MrSchrodingers/usage-buddies.git
cd usage-buddies
chmod +x install.sh
./install.sh
```

**Arch Linux notes:**
- The installer detects `paru` or `yay` and prefers them over `sudo pacman` when available.
- For Arch + GNOME, follow the **Ubuntu / Debian** section above — the same installer handles both.
- For Hyprland/Sway, ensure your bar has a tray module (`waybar`'s `tray` or `eww`).

The installer will:
1. Check Plasma 6 and Python 3
2. Install the data collector to `~/.local/bin/`
3. Install the Plasma widget to `~/.local/share/plasma/plasmoids/`
4. Set up a systemd timer (refreshes every 30s)
5. Auto-detect your claude.ai organization from browser cookies
6. Generate initial data
7. Run sanity checks (binaries present, timer active, `~/.claude/` writable)

#### Add to Panel

1. Right-click your KDE panel
2. Click **"Add Widgets..."**
3. Search for **"Usage Buddies"**
4. Drag it to your panel

#### Codex (OpenAI) mode

The same applet also tracks **Codex CLI / ChatGPT** usage. Right-click the
widget → **Configure…** → **Usage source** → *Codex*. Nothing else changes:
same layout, same panel bars, same popup sections.

| | Claude mode (default) | Codex mode |
|---|---|---|
| Collector | `~/.local/bin/usage-buddies-collector.py` | `~/.local/bin/codex-usage-collector.py` |
| Cache file | `~/.claude/widget-data.json` | `~/.codex/widget-data.json` |
| Local log | `~/.claude/**.jsonl` | `~/.codex/sessions/**.jsonl` |
| Remote API | claude.ai | `chatgpt.com/backend-api/wham/*` |
| systemd timer | `usage-buddies-collector.timer` | `codex-usage-collector.timer` (enabled only when `~/.codex` exists) |

`install.sh` installs both collectors; each applet instance picks one, so a
panel can hold one widget per provider side by side.

Codex reports two rate-limit windows (a short rolling one and a 7-day one), and
the collector picks them **by duration** rather than by position in the
response, which survives the endpoint adding or reordering windows. Sections
Codex does not report — per-model weekly rows, cost projection, tool use,
latency — stay hidden instead of rendering empty bars. Bars appear once Codex
has written one `token_count` event, i.e. after one completed interaction.

### Tauri Tray App (Windows, macOS, Ubuntu GNOME)

On Linux, `install.sh` handles Tauri automatically. To build manually:

```bash
git clone https://github.com/MrSchrodingers/usage-buddies.git
cd usage-buddies/tauri-app
npm install
cargo tauri build
```

The built binary is at `src-tauri/target/release/usage-buddies-tray`. Bundled packages (.deb, .rpm, .dmg) are generated in `src-tauri/target/release/bundle/`.

#### Running the collector manually

The collector runs automatically under every installer path above. To run it yourself:

```bash
~/.local/bin/usage-buddies-collector.py
```

On platforms not covered by an installer, schedule it with cron or launchd.

### Windows Widget (Windows 10 / 11)

Build the standalone widget (no admin required):

```powershell
cd usage-buddies\win-widget
npm install
npx tauri build --no-bundle
```

This produces a self-contained `usage-buddies-win.exe` at `win-widget\src-tauri\target\release\`. To install it so it refreshes and auto-starts on login:

1. Copy `usage-buddies-win.exe` and `scripts\usage-buddies-collector.py` into `%LOCALAPPDATA%\UsageBuddiesWin\`.
2. Register a per-user **Scheduled Task** that runs the collector every 60 s (no admin):
   `pythonw.exe -X utf8 "%LOCALAPPDATA%\UsageBuddiesWin\usage-buddies-collector.py"`
3. Add a **Startup** shortcut pointing to `usage-buddies-win.exe`.

The widget then lives as a **tray icon** — left-click to toggle the popup (docked at the bottom-right corner), right-click for **Quit**. If the icon hides in the notification-area overflow, pin it via *Taskbar settings → Select which icons appear on the taskbar*.

---

## The buddy talks

Off by default. The header button cycles **silent → alerts only → chatty**;
"alerts only" is the mode worth leaving on — it speaks solely when a session
needs you.

What ruined Clippy was speaking without having anything to say. Every line here
is bound to a measured trigger and carries a real number, and when nothing
crosses a threshold the buddy is quiet.

### Live sessions

Several Claude Code sessions run at once across different repositories, and
nothing on the desktop says which finished, which is blocked on an answer, and
which has been idle for an hour. `scripts/sessions-probe.py` crosses two
sources:

- `pgrep -x claude` plus `/proc/<pid>/cwd` — which sessions are actually alive
  and in which repository. A transcript on disk proves a session existed, not
  that it is running.
- the newest transcript under `~/.claude/projects/<slugged-cwd>/` — its last
  records say what the session is doing, its mtime says for how long.

States, most urgent first: **asking** (blocked on `AskUserQuestion`), **done**
(turn ended and settled), **idle** (no writes for ten minutes), **working**.

Classification reads the last ~25 records, not the last one: a finished turn is
followed by bookkeeping — `attachment`, then `stop_hook_summary`,
`turn_duration`, `away_summary` — none of which carries a stop reason, so
reading only the final line makes every settled session look busy.

Only record types, stop reasons, tool names and timestamps are inspected. No
message text is read.

### The desktop companion

With chatter on, a companion appears at the bottom of the screen and wanders —
it walks, pauses, turns around, and speaks in a bubble when it has something to
say. Left-click a line about a session to jump to that session; right-click to
quit it.

It is a **separate process**, not part of the widget: a Plasma applet lives
inside the panel's window and cannot leave it. The header button owns its
lifecycle, so there is one control rather than two.

It roams **every monitor** and shows on **every virtual desktop**. Confined to
the primary screen it never appears on the other display at all, which is most
of the time someone spends looking somewhere; pinned to one desktop it has to
be hunted for. Targets are picked inside a chosen screen rather than across
their union, because the union of two monitors contains regions belonging to no
display — standing in one is invisible while looking perfectly fine to the code.

It runs under **XWayland** (`QT_QPA_PLATFORM=xcb`), because Wayland has no call
for a client to position its own window — by design. The alternative is asking
KWin to move the window over D-Bus on every frame, which is neither smooth nor
kind to the compositor.

Two traps worth recording, both hit here:

- `pkill -f usage-buddy-companion` kills the shell running it, because that
  string is in its own command line. `companion-ctl.sh` walks `/proc` and skips
  its own pid.
- A shebang script is exec'd as `/usr/bin/python3 /path/script.py`, so argv[0]
  is the interpreter. Matching only argv[0] finds nothing, and `status`
  reported zero while the companion was running.

### Notification and focus

With chatter enabled, a session entering **asking** or **done** raises a
desktop notification carrying a *Go there* action, deduped per session and
state so an hour of waiting does not re-announce every cycle. Clicking it — or
clicking the session in the popup — raises the terminal that session runs in.

`scripts/focus-session.sh` walks the process tree up from the Claude pid
(claude → shell → terminal emulator; only the last owns a window) and asks KWin
to activate the matching window. KWin scripting is the only route that works
under Wayland: `xdotool` and `wmctrl` talk X11 and silently do nothing.

---

## Harness page (Tollens)

If [Tollens](https://github.com/MrSchrodingers/tollens) governs this machine's
Claude Code configuration, a second page appears behind the gear button in the
popup header. Without it the button does not exist — a dead tab for an absent
integration is worse than no tab.

Tollens' own thesis is **INSTALLED ≠ ENFORCED ≠ ACTIVATED**, so the page shows
those as three separate lights rather than one: a policy can be deployed and
not enforced, and enforced while the installed tree has drifted from the
manifest it claims to enforce.

`scripts/tollens-probe.py` collects it in two layers, because they cost
different amounts:

| Layer | What | Cost | Cadence |
|---|---|---|---|
| A | presence, enforcement, hook map, manifest inventory — pure file reads | ~35 ms | every run |
| B | `install/verify.sh` + `apply-managed.sh --verify` | ~750 ms | every 5 min |

Both verifiers are read-only and need no root; that was established by
snapshotting mtime and size across 6443 entries before and after running them.

**The SessionStart heartbeat is history, not state.** Tollens writes
`session-integrity.jsonl` once per session start; it was measured two hours
stale with a verdict inverted against a live run (`drift` recorded,
`49/49 ok` live). The page renders it with its own timestamp attached and
never as current conformance — the live number comes from layer B.

**Not collected, deliberately.** `~/.claude/logs/subagent-probe.jsonl` carries
`last_assistant_message` and `cwd`, and its own header states the payload must
not leave the machine. `/var/log/tollens-activation.jsonl` carries project file
paths that name clients. Neither belongs in a JSON a desktop widget reads.

**Usage metrics** come from `/var/log/tollens-activation.jsonl`, aggregated:
which agents get invoked and their share, which skills and tools, distinct
session count, and the split of loaded instructions across the precedence chain
(Managed / Project / User). That last one is the closest thing Tollens records
to evidence of **ACTIVATED**, the third of its three states and the one its own
README calls hard to establish.

The verify-gate ledgers under `~/.claude/evidence/` give a pass rate — ~3500
files and 15 MB, measured at 0.41 s, so it rides along with layer B rather than
running every cycle.

These are **running totals, not a window**. The activation log carries no
timestamps, and deriving a start from the file's `ctime` would be wrong: on
Linux that is the inode change time and moves on every append.

The log's `f` field holds project file paths that name clients. The probe
declares an allowlist of safe fields (`ev`, `a`, `k`, `t`) and never indexes
`f`; session ids are counted for the distinct total and never emitted. Tests
assert both, and fail against a mutant that adds `f` to the list.

**Not available.** Tollens records no hook execution timings anywhere, so the
page says so rather than showing an empty chart.

Output goes to `~/.cache/usage-buddies/tollens.json` (0600), outside `~/.claude`
— that tree is what Tollens audits, and a widget file inside it is a candidate
orphan the moment their scan widens.

---

## Browser Support

| Browser | Linux path | macOS |
|---------|-----------|-------|
| **Firefox** (native) | `~/.mozilla/firefox/` | Native |
| **Firefox** (Snap, Ubuntu default) | `~/snap/firefox/common/.mozilla/firefox/` | — |
| **Firefox** (Flatpak) | `~/.var/app/org.mozilla.firefox/.mozilla/firefox/` | — |
| **Chrome** | `~/.config/google-chrome/` (encrypted via GNOME Keyring / KWallet) | Plaintext only |
| **Chromium** | `~/.config/chromium/`, Snap, Flatpak (encrypted via GNOME Keyring / KWallet) | Plaintext only |

Priority: Firefox first (plaintext cookies, fastest), then Chrome/Chromium as fallback. On KDE/Wayland, if the XDG portal fails to unlock the KWallet entry, Chrome falls back to its "peanuts" (v10) encryption — the collector handles both paths automatically.

---

## How It Works

```
Browser cookies (Firefox/Chrome/Chromium)
        |
        v
usage-buddies-collector.py (every 30s)
        |
        |--- claude.ai/api/.../usage
        |       Session %, weekly limits, reset timers
        |
        |--- claude.ai/api/.../prepaid/credits
        |       Balance, currency, auto-reload
        |
        |--- claude.ai/api/.../overage_spend_limit
        |       Extra usage: enabled, limit, used
        |
        |--- claude.ai/api/.../overage_credit_grant
        |       Credit grant status
        |
        |--- status.claude.com/api/v2/summary.json
        |       Service health, components, incidents
        |
        |--- ~/.claude/settings.json
        |       Adaptive thinking, effort level
        |
        |--- ~/.claude/projects/**/*.jsonl
        |       Errors, tokens, latency, sessions
        |
        v
~/.claude/widget-data.json
        |
        +---> KDE Plasmoid (QML)
        +---> Tauri Tray App (HTML/CSS/JS)
        +---> Windows Widget (Tauri v2)
```

### Authentication

The widget reads session cookies from your browser. No API keys or passwords stored.

- **Firefox**: `~/.mozilla/firefox/*/cookies.sqlite` (plaintext)
- **Chrome**: `~/.config/google-chrome/Default/Cookies` (AES-128-CBC, key from GNOME Keyring or KWallet)
- **Chromium**: `~/.config/chromium/Default/Cookies` (AES-128-CBC, key from GNOME Keyring or KWallet)

### Data Sources

| Data | Source | Scope |
|------|--------|-------|
| Session (5h) usage | claude.ai API (`five_hour`) | All devices |
| Weekly all-models | claude.ai API (`seven_day`) | All devices |
| Weekly Sonnet / Opus / Design | claude.ai API (`seven_day_sonnet` / `_opus` / `_omelette`) | All devices |
| Reset timers | claude.ai API | All devices |
| Prepaid credits | claude.ai API (`prepaid/credits`) | Organization |
| Extra usage limits | claude.ai API (`overage_spend_limit` + inline in `usage`) | Organization |
| Service health | status.claude.com | Anthropic infra |
| Error rate | Local JSONL | This machine |
| Burn rate | Local JSONL | This machine |
| Avg response/latency | Local JSONL | This machine |
| Adaptive Thinking | Local settings | This machine |
| Dumbness score | Composite | Combined |
| 7-day chart | Local JSONL | This machine |
| Peak hours | Local stats-cache | This machine |

Codex mode (see [Codex (OpenAI) mode](#codex-openai-mode)):

| Data | Source | Scope |
|------|--------|-------|
| Session (rolling window) | `chatgpt.com/backend-api/wham/usage` (`rate_limit`) | All devices |
| Weekly (7-day window) | `chatgpt.com/backend-api/wham/usage` (`rate_limit`) | All devices |
| Plan tier / credits | `chatgpt.com/backend-api/wham/usage`, `rate-limit-reset-credits` | Account |
| Session / weekly fallback | `~/.codex/sessions/**.jsonl` (`token_count.rate_limits`) | This machine |
| 7-day chart, sessions, turns | `~/.codex/sessions/**.jsonl` | This machine |

---

## Features

### 13 UI Sections

All three interfaces (plasmoid, Tauri tray, Windows widget) render the same sections:

1. **Header** - "Claude" title + level pill badge + animated Clawd mascot
2. **Session Card** - Circular progress ring with colored border + live countdown
3. **Weekly Limits** - All models + per-model (API-scoped, e.g. Fable) progress bars
4. **Credits & Spending** - Balance, auto-reload, extra usage with progress bar
5. **Service Health** - Pulsing dot, status pill, component grid, DownDetector link
6. **Intelligence Score** - Emoji label, score pill badge, color-coded background
7. **Activity** - Burn rate, errors, adaptive thinking, avg response, latency
8. **Model Distribution** - Stacked bar chart (Opus/Sonnet/Haiku) + legend
9. **Quick Actions** - claude.ai, Status, Copy Stats buttons
10. **7-Day Activity** - Bar chart with rounded tops, today highlighted
11. **Peak Hours** - 24-column chart (amber work hours, blue night)
12. **Footer** - Sessions count, since date, streak badge, version
13. **Easter Egg** - Tap Clawd 5x to cycle mascot states

### Tray App Platform Notes

| Platform / DE | Tray Click | Keyboard Shortcut | Setup |
|---|---|---|---|
| **macOS** | Left-click toggles popup | `Super+Shift+C` | — |
| **KDE Plasma** (Kubuntu, Arch, Fedora KDE) | Use the plasmoid | `Super+Shift+C` | — |
| **Ubuntu GNOME / Arch GNOME** | Left-click toggles popup | `Super+Shift+C` | Installer auto-installs AppIndicator extension; relogin required |
| **Ubuntu MATE / XFCE / Cinnamon** | Left-click toggles popup | `Super+Shift+C` | Native via StatusNotifierItem |
| **Hyprland / Sway** | Depends on bar | `Super+Shift+C` | `waybar` tray module or `eww` equivalent |

---

## Adaptive Thinking Workaround

If Claude feels "lazy" or gives shallow answers:

```json
// ~/.claude/settings.json
{
  "effortLevel": "high",
  "env": {
    "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING": "1"
  }
}
```

This forces full reasoning on every turn. Trade-off: consumes rate limit faster, but significantly better output quality.

---

## Collector CLI

The collector supports several flags useful for diagnostics and testing:

```bash
# Verbose log of cookie discovery, decryption, and API calls
~/.local/bin/usage-buddies-collector.py --verbose

# Structured health report (human-readable)
~/.local/bin/usage-buddies-collector.py --health-check

# Same report as JSON for programmatic consumption
~/.local/bin/usage-buddies-collector.py --health-check --json

# Preview each mascot state without touching the live data
~/.local/bin/usage-buddies-collector.py --test-state=genius
~/.local/bin/usage-buddies-collector.py --test-state=smart
~/.local/bin/usage-buddies-collector.py --test-state=slow
~/.local/bin/usage-buddies-collector.py --test-state=dumb
~/.local/bin/usage-buddies-collector.py --test-state=braindead
```

`--health-check` distinguishes three failure modes: no browser profile, got cookies but API rejected them (session expired), and got cookies + API response but the collector itself crashed parsing it (bug — please report). Installers use it to decide between Live and Offline modes.

---

## Uninstall

### Linux (KDE plasmoid + Tauri tray, any DE)

```bash
cd usage-buddies
./uninstall.sh
```

Removes: collector binary, plasmoid, systemd timer, tray binary, autostart entry, and only the widget-owned files in `~/.claude/` (`widget-data.json`, `widget-config.json`, `widget-status-prev.json`). `stats-cache.json` belongs to Claude Code itself and is never touched.

Installs made **before** the rename are removed by the frozen scripts in
`legacy/` (`bash legacy/uninstall.sh`), which still know the old artifact names.
See `legacy/README.md`.

### Windows Widget

```powershell
Get-Process usage-buddies-win -ErrorAction SilentlyContinue | Stop-Process -Force
Unregister-ScheduledTask -TaskName UsageBuddiesCollector -Confirm:$false
Remove-Item "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Usage Buddies.lnk" -Force -ErrorAction SilentlyContinue
Remove-Item "$env:LOCALAPPDATA\UsageBuddiesWin" -Recurse -Force
```

Removes the widget, its scheduled collector task, the Startup shortcut, and the install folder. Delete the widget-owned files in `~/.claude/` too if you want a full cleanup.

---

## Troubleshooting

### First step: run the health check

```bash
~/.local/bin/usage-buddies-collector.py --health-check
```

The report pinpoints the failing layer (browser profile missing, cookies not decryptable, session expired, or collector bug) and prints the exact next action. Installers use the same check and include its output in the post-install summary.

### Widget shows `--` or no data
- Run `--health-check` first (above) to pinpoint the cause
- Run `~/.local/bin/usage-buddies-collector.py --verbose` for a detailed log
- Make sure you're logged in to [claude.ai](https://claude.ai) in Firefox/Chrome

### Widget shows `Offline` instead of `Live`
- Your browser session may have expired — log in to claude.ai again
- Visit claude.ai to refresh the `cf_clearance` cookie
- If `--health-check` reports a collector bug (not an auth failure), please file an issue with the `--verbose` output

### Chrome cookies not working (Linux)
- **GNOME**: Ensure `secret-tool` is installed (`sudo apt install libsecret-tools`)
- **KDE / Wayland**: ensure `kwallet-query` is available (`sudo dnf install kwallet` or `sudo apt install kwalletmanager-5`). If it is installed and cookies still don't decrypt, the KWallet entry may be stale — reset it with `kwallet-query -w 'Chrome Keys' -f 'Chrome Safe Storage' kdewallet` and restart Chrome. The collector also falls back to the "peanuts" (v10) scheme automatically when the XDG portal can't unlock the keyring.
- The collector tries GNOME Keyring first, then KWallet, then the peanuts fallback

### Firefox on Ubuntu Snap
- If you see `cookies=0` for Firefox, you're likely using the default Snap build whose sandbox blocks cookie reads. Install the native Firefox (Mozilla PPA) or use Chrome, then re-run `--health-check`.

### Claude feels "dumb" or lazy
1. Check the Dumbness Score in the widget
2. Disable Adaptive Thinking (see workaround above)
3. Check status.claude.com for incidents
4. If session > 80%, wait for the 5h window to reset

### Timer not running
```bash
systemctl --user status usage-buddies-collector.timer
systemctl --user enable --now usage-buddies-collector.timer
```

### Tauri app: tray icon not visible (Linux)
- On GNOME, install the AppIndicator extension: `gnome-extensions install appindicatorsupport@rgcjonas.gmail.com`
- Use `Super+Shift+C` as alternative

---

## Supported Plans

| Plan | Features |
|------|----------|
| Max (20x) | All features, full limits tracking |
| Max (5x) | All features, full limits tracking |
| Pro | Session %, weekly %, dumbness score |
| Free | Session %, dumbness score |

---

## Tech Stack

- **KDE Plasmoid**: QML (Qt 6) + Kirigami + PlasmaComponents3
- **Tauri Tray App**: Tauri v2 (Rust) + Vanilla JS + Vite + Canvas
- **Windows Widget**: Tauri v2 (Rust) + Vite + vanilla JS — frameless corner popup, animated pixel-art mascot, hover-reactive cards & charts
- **Data collector**: Python 3.8+ (stdlib + `cryptography` for Chrome AES/peanuts decryption)
- **Sprite generator**: Python 3 + Pillow
- **Scheduling**: systemd user timer (Linux, 30s) or Scheduled Task (Windows, 60s)
- **Tests**: `tests/test_collector_paths.py` (pytest, stdlib only)
- **APIs**: claude.ai (authenticated), status.claude.com (public)

---

## Security

- All DOM rendering uses `textContent`/`createElement` (zero `innerHTML`)
- CSP: `default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' asset: tauri:`
- Tauri `shell:default` scope (open limited to `http(s)`, `mailto:`, `tel:`) is the only runtime capability requested
- JSON validation + 1MB size cap on `widget-data.json` before rendering
- No API keys, tokens, or passwords stored on disk by the app
- Browser cookies are read locally, decrypted in memory, and used **only** to call `claude.ai` and `status.claude.com` — never logged (verbose mode prints cookie *names* only) and never written back to disk
- `widget-data.json` is written at mode `0600`; credentials never leak into it

---

<div align="center">

**MIT License** | Made by [MrSchrodingers](https://github.com/MrSchrodingers), [guizzi-glitch](https://github.com/guizzi-glitch) & [asm444](https://github.com/asm444)

</div>
