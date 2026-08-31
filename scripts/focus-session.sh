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

# Ancestors, closest first. Eight levels is far more than the two this needs.
ancestors=""
cur="$PID"
for _ in $(seq 1 8); do
    [ -n "$cur" ] && [ "$cur" != "1" ] || break
    ancestors="${ancestors}${ancestors:+,}$cur"
    cur=$(ps -o ppid= -p "$cur" 2>/dev/null | tr -d ' ')
done
[ -n "$ancestors" ] || exit 1

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
