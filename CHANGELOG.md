# Changelog

## 2.0.0

The project is renamed **claude-usage-widget → usage-buddies**, it watches a
second provider, and a batch of defects found along the way are fixed.

### Breaking

Every artifact on disk changed name, so an existing install does not upgrade in
place:

| before | after |
|---|---|
| `~/.local/bin/claude-usage-collector.py` | `~/.local/bin/usage-buddies-collector.py` |
| `claude-usage-collector.{service,timer}` | `usage-buddies-collector.{service,timer}` |
| `org.kde.plasma.claudeusage` | `org.kde.plasma.usagebuddies` |
| `~/.local/bin/claude-usage-tray` | `~/.local/bin/usage-buddies-tray` |

`install.sh` detects the old install and offers to clear it, carrying
`widget-config.json` and `widget-status-prev.json` across. `legacy/` holds the
old uninstallers frozen at the old names — that is what makes them work.

Data files under `~/.claude/` keep their names. `widget-data.json` is the
contract between collector and UI, and nothing forced a migration.

On KDE the panel references the plasmoid by ID, so the widget disappears from
the panel when the ID changes. Re-add it: right-click panel → Add Widgets →
"Usage Buddies".

### Added

- **A second provider.** One applet instance follows Claude, another follows
  OpenAI Codex, selected per instance under Configure → Usage source. Same
  layout, separate collector and cache. (PR #9)
- **Rex**, a pixel-art buddy for Codex, and a drawn terminal-prompt mark for
  its provider row. Codex previously had no mascot at all, which collapsed the
  header column.
- **Pace.** Every gauge shows where even burn through the window would have
  reached by now, so 60% spent in the first hour of a 5h window reads
  differently from the same 60% in the fifth.
- **Alert zones**, drawn on the empty track at 75% and 90%, so the danger is
  visible before the bar reaches it.
- **Threshold alerts** at those same two points, for the session and for each
  weekly quota individually. They fire once per window and name the quota.
- **Windows widget rebuilt in Tauri v2** as a collapsible corner pill. (PR #8)
- **Panel display modes** and per-model weekly quotas. (PR #7)
- Burn rate and projected time-to-limit, permanently under the session ring.

### Fixed

- **The 7-day chart was flat.** It read `stats-cache.json`, which can lag by
  weeks; it now reads the JSONL logs directly. Observed here: the cache was 61
  days stale while the chart showed eight days of zeros.
- **A false "weekly limit exhausted".** When the API call failed, the collector
  fell back to a local estimate that divides tokens by a hardcoded limit and
  clamps at 100% — so any heavy account read as exhausted. Alerts now fire only
  on measured data.
- **`resetsAt` is not stable across polls.** The endpoint returns the same
  instant with a fresh sub-second fraction every call, which made every 30s
  poll look like a new window and would have turned one alert into a stream.
- **The calm gauge rendered red** on themes whose accent is red, because the
  quiet state borrowed `Kirigami.Theme.highlightColor`. Calm is now a
  desaturated neutral.
- **A dead "Sonnet only 0%" row.** The API deprecated the legacy per-model
  fields to null; the collector kept emitting the scope and the QML row was the
  only weekly row without a visibility guard.
- **`NameError` on a machine with no `~/.claude/projects`** — the first-run
  case. (from PR #7)
- Windows cookie, toast and sound paths, removed by the Tauri rebuild without a
  replacement. The collector is shared; only the UI was replaced.
- `@tauri-apps/cli` was never declared, so `npx tauri build` failed and
  `install.sh` reported it as a missing binary.
- `pgrep -x` can never match a name over 15 characters, so both uninstallers
  silently left the tray running.

### Security

- **Redirects carried credentials off-origin.** urllib re-sends every header on
  a 302 and permits an https→http downgrade, so a redirect handed the session
  cookie — and, for Codex, the bearer token — to an arbitrary host in clear
  text. Both collectors now refuse cross-origin redirects.
- **The session cookie could reach the journal.** `http.client` quotes an
  invalid header value in its `ValueError`, and that is not an `OSError`, so it
  escaped the typed handlers and printed a traceback every 30s. Header values
  are filtered and failures report only the exception class. Checked: no
  occurrences in this machine's journal across 113k lines.
- **PowerShell injection** through `notifications.sounds.<event>Win` in
  `widget-config.json`, which was interpolated into a command unescaped.
- **The Codex cookie query matched lookalike hosts.** `LIKE '%chatgpt.com%'`
  also matches `evil-chatgpt.com.attacker.io`, and it paired two different
  registrable domains.
- Both systemd units gained a least-privilege sandbox. `systemd-analyze` drops
  from 9.4 UNSAFE to 5.1 MEDIUM.

### Performance

The collector runs on a 30s timer and was taking ~25s per run, at 315k
`json.loads` calls. Per-file scan results are cached under `(mtime, size)`:

| | before | after (warm) |
|---|---|---|
| `compute_daily_trend` | 15.16s | 0.07s |
| `detect_opus_fallbacks` | 2.78s | 0.03s |

### Notes

- Nothing was executed on Windows. Those branches are exercised by simulating
  `platform.system()` on Linux, which proves the decision flow and not the
  behaviour there.
- The offline estimate's limits (`WEEKLY_ALL_LIMIT = 40M`, `WEEKLY_OPUS_LIMIT
  = 20M`) have no source in the repository. They no longer drive alerts, but
  they still fill the bars when offline, and remain unverified.

## 1.0.0

Initial KDE plasmoid, Tauri tray and PySide6 Windows widget, with the shared
Python collector reading claude.ai.
