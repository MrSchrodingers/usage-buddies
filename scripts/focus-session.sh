#!/bin/bash
# Bring the terminal window running a given Claude session to the front.
#
# The chain is claude -> shell -> terminal emulator, and only the last of those
# owns a window. So we walk up the process tree from the Claude pid collecting
# ancestors, then ask KWin which of its windows belongs to one of them.
#
# KWin scripting is the only route that works under Wayland: xdotool and wmctrl
# talk X11 and silently do nothing here.
set -uo pipefail

PID="${1:-}"
[ -n "$PID" ] || { echo "usage: focus-session.sh <pid>" >&2; exit 2; }

# Raising the window is only half the job when the sessions are tabs.
#
# Measured on the machine this was written for: three of five Claude sessions
# lived in tabs of one konsole process, so their ancestor chains converge on a
# single pid and no amount of window matching can tell them apart. A fourth ran
# in cool-retro-term and a fifth in a second konsole.
#
# Konsole publishes one D-Bus service per process, org.kde.konsole-<pid>, and
# every tab under it answers foregroundProcessId() — which is the Claude pid
# itself. That is an exact map from session to tab. There is no
# setCurrentSession, so the tab is reached by cycling nextSession() and
# checking currentSession(), bounded by sessionCount().
#
# Best-effort: a terminal that is not konsole, or a konsole too old to publish
# the service, just falls through to raising the window.
select_konsole_tab() {
    local target="$1" svc="$2" win session current i count
    for win in $(qdbus-qt6 "$svc" 2>/dev/null | tr -d ' ' \
                 | grep -E '^/Windows/[0-9]+$'); do
        count=$(qdbus-qt6 "$svc" "$win" org.kde.konsole.Window.sessionCount 2>/dev/null)
        [ -n "$count" ] || continue
        for session in $(qdbus-qt6 "$svc" 2>/dev/null | tr -d ' ' \
                         | grep -E '^/Sessions/[0-9]+$'); do
            if [ "$(qdbus-qt6 "$svc" "$session" \
                    org.kde.konsole.Session.foregroundProcessId 2>/dev/null)" != "$target" ]; then
                continue
            fi
            local want="${session##*/}"
            i=0
            while [ "$i" -lt "$count" ]; do
                current=$(qdbus-qt6 "$svc" "$win" \
                          org.kde.konsole.Window.currentSession 2>/dev/null)
                [ "$current" = "$want" ] && return 0
                qdbus-qt6 "$svc" "$win" org.kde.konsole.Window.nextSession >/dev/null 2>&1
                i=$((i + 1))
            done
            return 0
        done
    done
    return 1
}

# Ancestors, closest first. Eight levels is far more than the two this needs.
ancestors=""
cur="$PID"
for _ in $(seq 1 8); do
    [ -n "$cur" ] && [ "$cur" != "1" ] || break
    ancestors="${ancestors}${ancestors:+,}$cur"
    cur=$(ps -o ppid= -p "$cur" 2>/dev/null | tr -d ' ')
done
[ -n "$ancestors" ] || exit 1

# Before raising anything: if one of those ancestors is a konsole that
# publishes its sessions, switch to the right tab first. Raising then brings
# the window up already showing the session that was asked for.
for anc in $(echo "$ancestors" | tr ',' ' '); do
    if qdbus-qt6 "org.kde.konsole-$anc" >/dev/null 2>&1; then
        select_konsole_tab "$PID" "org.kde.konsole-$anc" && break
    fi
done

script=$(mktemp --suffix=.js) || exit 1
trap 'rm -f "$script"' EXIT

cat > "$script" <<JS
var wanted = [${ancestors}];
var list = workspace.windowList ? workspace.windowList() : workspace.clientList();
for (var i = 0; i < list.length; i++) {
    var w = list[i];
    if (!w || w.skipTaskbar) continue;
    if (wanted.indexOf(w.pid) === -1) continue;
    // Both are needed: the window may be on another virtual desktop, and
    // activating without raising leaves it behind whatever is on top.
    if (typeof workspace.currentDesktop !== "undefined" && w.desktops && w.desktops.length) {
        workspace.currentDesktop = w.desktops[0];
    }
    w.minimized = false;
    workspace.activeWindow = w;
    workspace.raiseWindow ? workspace.raiseWindow(w) : null;
    break;
}
JS

name="usage-buddies-focus-$$"
qdbus-qt6 org.kde.KWin /Scripting org.kde.kwin.Scripting.loadScript "$script" "$name" >/dev/null 2>&1 || exit 1
qdbus-qt6 org.kde.KWin /Scripting org.kde.kwin.Scripting.start >/dev/null 2>&1
sleep 0.3
# Unload, or every call leaves a registered script behind.
qdbus-qt6 org.kde.KWin /Scripting org.kde.kwin.Scripting.unloadScript "$name" >/dev/null 2>&1 || true
