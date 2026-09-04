# Changelog

## Unreleased

### AI Central

Installation is now end-to-end and reproducible from a fresh PC through an
authorized Android device. The PC installer has check and dry-run modes,
distro-aware dependency installation, an always-on profile, timestamped
backups, atomic web staging, post-install health gates, and automatic rollback
that leaves live tmux agents untouched. It installs the `ch` executable and
opens one synchronized Konsole by default at graphical login.

The ADB installer verifies every transferred payload with SHA-256, types only
into a newly-created local Termux session, exchanges an Ed25519 public key, and
requires a fresh mobile tmux client before reporting success. Termux config is
merged through a delimited managed block and restored on failure. An optional
Termux:Boot preflight restores reachability after Android unlock without
attaching a hidden 80x24 client that could resize the shared TUI.

The shared Claude Code/Codex hub is now reproducible instead of being a set of
machine-local shortcuts. It has dedicated PC and Termux installers, portable
systemd and desktop entries, an operational `claude-hub doctor`, a documented
recovery model, and paired uninstall behavior that deliberately preserves live
tmux sessions and their resume registry.

The terminal grid follows the most recently active client. This removes the
desktop-sized field of dots caused by forcing every pane down to the phone's
width, while still reflowing Claude for mobile input. Termux detects a dead SSH
transport within about ten seconds, says explicitly that the old menu is no
longer live, reconnects, and wakes the Tailscale app after repeated failures.

The monitor publishes one private atomic state cache. The PWA reads that cache
directly, prevents overlapping status requests and backs off while hidden, so
opening more browser clients no longer multiplies Git and process scans. Its
service worker also removes stale AI Central caches during upgrades.

### The widget

Every field of `widget-data.json` was already on screen — measured, not
assumed — so the additions are what it was not doing with it. A weekly
forecast, because `limitEta` projects the five-hour window and the weekly
ceiling is the one that hurts. Cost by project. Today against the median of
your own recent days, scaled to the hour.

The alert thresholds are configurable, which took some care: they lived as
literals in two files, and a test pinned them together because when they drift
the bar turns red and no notification comes. They resolve in one place now and
are published alongside the numbers they were applied to, so the bar is painted
with the pair the run would have announced on. Both sides own the config file
and it holds the org id the whole collection depends on, so every write goes
through one mutator holding a lock, reading, merging and renaming.

A compact mode that ranks what is on screen rather than showing one fixed
thing: a major incident above a spent quota, a degraded service below it.
Rising is immediate and falling is held, because a panel that changes face
every refresh is worse than one that never does.

And the QML is rendered in tests now instead of being read as text. A sixth
header button had shipped a popup with every row cut off at the same x, and
qmllint plus twenty-three assertions over the file all passed — the only thing
that caught it was someone opening the popup and looking. The harness
reproduces that defect against the pre-fix file, so the reproduction cannot rot.

### The companion

It talks to you now, and the lines were rewritten: 31 categories, eight lines
each, in both languages. The two-clause shape that every one of the previous
139 had is capped at three per category, because repeated that many times it
stops being a voice and becomes a tic. The philosophy had been fortune
cookies; the rule now is that if it fits on a mug it is out.

It also stopped inventing figures. The live voice is handed session names,
their states and two quotas rounded to tens — and nothing else — while the
companion let its line replace whatever the Brain had rendered. Every sentence
quoting efficiency, compaction, latency or runway made the number up. The model
writes the character and the table writes the facts now.

Focus blocks, an escort that holds one session, and an insistence ladder that
climbs while a session waits. Quiet hours from this account's own peak hours.
Twelve clips, five expressions, a contact shadow, a mood band, six props and
fifteen particles. Two mascots on one desktop notice each other. A temper that
remembers being thrown, a basket, a target, a distance record and juggling.

### Defects worth recording

- Running the test suite stopped whatever companion was running: one test
  called the real `companion-ctl.sh stop`.
- `companion-ctl.sh stop` matched the script name anywhere in a command line,
  so it killed `vim` on the file and the `cp` inside `install.sh` — truncating
  the file being installed.
- Both overlay windows swallowed every click aimed at the mascot.
  `WA_TransparentForMouseEvents` governs Qt's own hit testing and leaves a
  separate top level's X input region alone; `Qt.WindowTransparentForInput` is
  what empties it. The test had asserted the attribute and stated the wrong
  mechanism as fact in its own docstring.
- One lasting condition owned every line the mascot said. The ladder ranks by
  urgency and the first allowed signal is spoken, so an open incident produced
  twenty incident lines in twenty polls while the quota, the compaction count
  and the read ratio were all firing and never reached.
- The Codex collector exited 1 on every run for over an hour:
  `item.get("info", {})` does not defend against a present key holding null,
  and 3 of 941 records carry `"info": null`.
- A companion that died said nothing at all, because `start` sent its output
  to /dev/null and nothing here is a systemd unit.
- The uninstaller left seven library modules behind.

### Measurement mistakes, since they cost more than the defects

Three of the same shape, and the third was caught by the second. A `uinput`
write returning True proves the write, not that the pointer moved. A pointer
read reported a working carry as inert — measured against KWin's own
`cursorPos`, the XWayland shadow is 225 px from the truth at the median and
frozen for 55 of 90 seconds. And an attribute set without effect passed a test
that asserted the attribute. An instrument that cannot see the positive case
cannot report its absence.

## Unreleased

The desktop companion stops being a character that walks and comments, and
becomes one that can be configured, interrupted and worked with.

### The mascot of a quota widget now reads the quota

`Brain.line()` decided what to say from efficiency, compaction, tool use and
the clock, and never opened `rateLimits`. The proof that this was an oversight
rather than a choice was already in the table: the `twoRed` category shipped
with four English lines and four Portuguese ones about two red quotas at once,
and no code path could select them.

Detection moved to `scripts/buddy_signals.py`, a pure function over the two
payloads. Sixteen signals are new — both quota windows, the limit ETA, credits
and extra usage, service incidents, MCP servers waiting on auth, Opus quietly
answering as Sonnet, error and latency drift, cost runway, the session eating
the day's budget, the branch, the streak, and off-peak hours derived from this
account's own history. The five existing diagnostics carry over unchanged, so
moving the decision cannot change what a given desktop says. The phrase table
moved to `scripts/buddy_lines.py`: 14 categories became 30, and a test now
holds both directions so a category nothing can reach fails the suite.

### Focus, escort, and an insistence that escalates

`scripts/buddy_focus.py` is a pure engine — no Qt, no I/O, time as an argument.
A focus block silences everything except a session actually asking. An escort
locks onto one session rather than rotating. Insistence climbs while a session
waits — speak, approach, wave, and at the top carry the pointer — and never
regresses while the condition holds.

The pointer step is opt-in. `off` is the only level that also stops the drag
getaway, and the permission check lives inside the one function that moves a
cursor rather than at one of its two call sites, which is how `--insistence
off` used to take the mouse anyway.

### Throwing, dropping, perching, and the other mascot

`scripts/buddy_actions.py` and `scripts/buddy_peers.py`. Releasing mid-drag
throws instead of discarding the gesture; releasing without motion still snaps
to the corner it was put in. A folder dropped on the companion starts the
reading the menu already offered, with dropped URIs treated as untrusted input
and every refusal named. Two mascots on one desktop notice each other, greet
once and walk on, discovered through a presence file rather than the window
tree — measured at 0.26 ms against 23.9 ms, which is 72% of a frame.

### Twelve clips, five expressions, and a shadow

The character had ten clips and stood upright forever, including in the corner
it was put in. It can now sit, yawn, wave, point, nod, shake, read, panic,
celebrate, peek, turn and type, with rolling, dizzy, sparkling and sleepy eyes
and a genuine side-glance — the eye spec may be a pair now, where before both
pupils could only point away from each other. No new bodies: every pose is an
exact operation on a grid that exists, so the 76 pre-existing frames are
byte-identical and the header mascots did not drift.

A creature with no arms gestures with its body. The first attempt extended a
limb sideways along the floor row, which on two-pixel stubs reads as a skid
mark rather than a gesture; a raised leg must have visible empty space beneath
it. Found by rendering at 12x and looking, as was Rex being decapitated —
`celebrate` and `panic` pushed the ear tufts past the top of the grid, which is
a shift, so nothing raised and the symptom was an owl with two loose marks
above it.

### Six settings, and a channel to a running process

Focus duration, how far insistence may climb, quiet hours, the gag layer, the
contact shadow, and whether it escorts one session at a time. Starting a focus
block reaches the running companion through
`~/.cache/usage-buddies/companion-command.json`, written through a temporary
file in the same directory and renamed, each command carrying `issuedAt` so a
restarting companion ignores yesterday's request.

### Defects fixed along the way

- The bubble opened past the right edge of the screen when the companion was
  docked there; it picks its side from the space available now.
- Running the test suite stopped whatever companion the user had running.
  `test_ctl_does_not_kill_its_own_shell` called the real `companion-ctl.sh
  stop`. The scan root is injectable now and the tests build their own.
- `companion-ctl.sh stop` matched the script name anywhere in a command line,
  so it killed `vim` on the file and the `cp` inside `install.sh` — truncating
  the file being installed.
- Seven library modules were installed into `~/.local/bin` and never removed by
  the uninstaller.
- A dropped `file:///work/src/#scratch` came back as `/work/src`: `urlsplit`
  answers by discarding, and the truncation was accepted rather than reported.
- `or {}` over a payload is only a guard against the falsy; `"lifetime": 1` is
  valid JSON, truthy, and raised every poll — leaving the companion walking
  around and never speaking again.
- The drop limit counted accepted entries rather than entries looked at, so a
  large selection made tens of thousands of filesystem calls on the Qt thread.
- Two public, documented, tested functions had no caller at all.

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
