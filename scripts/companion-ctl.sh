#!/bin/bash
# Start, stop or count the desktop companion.
#
# `pkill -f usage-buddy-companion` is the obvious way and it is wrong twice
# over. The shell running that command has the string in its own command line
# and kills itself — which happened. And a shebang script is exec'd as
# `/usr/bin/python3 /path/script.py`, so argv[0] is the interpreter and the
# script name is argv[1]; matching only argv[0] finds nothing.
#
# This walks /proc and matches the script in either position, skipping its own
# process. Processes that exit mid-scan are a normal race, not an error.
set -uo pipefail

SELF=$$
SCRIPT_NAME="usage-buddy-companion.py"
BIN="${USAGE_BUDDY_COMPANION:-$HOME/.local/bin/$SCRIPT_NAME}"
# Where to look for running companions. Overridable so the tests can exercise
# the scan and the kill against a directory they built, instead of against
# whatever the machine happens to be running. They used to call `stop` for
# real: the assertion passed and the user's companion died, which is a test
# that measures the right thing by doing the wrong one.
PROC="${USAGE_BUDDY_PROC:-/proc}"

# Echoes the pid of every running companion.
companion_pids() {
    local pid p argv
    for pid in "$PROC"/[0-9]*; do
        p="${pid#"$PROC"/}"
        [ "$p" = "$SELF" ] && continue
        argv=$( { tr '\0' '\n' < "$pid/cmdline"; } 2>/dev/null | head -2) || continue
        case "$argv" in
            *"$SCRIPT_NAME"*) echo "$p" ;;
        esac
    done
}

stop_companion() {
    local p
    for p in $(companion_pids); do
        kill "$p" 2>/dev/null || true
    done
}

case "${1:-}" in
    stop)
        stop_companion
        ;;
    start)
        shift
        stop_companion
        sleep 0.3
        [ -x "$BIN" ] || { echo "companion not installed: $BIN" >&2; exit 1; }
        setsid "$BIN" "$@" >/dev/null 2>&1 < /dev/null &
        ;;
    status)
        companion_pids | wc -l
        ;;
    *)
        echo "usage: companion-ctl.sh start|stop|status [args...]" >&2
        exit 2
        ;;
esac
