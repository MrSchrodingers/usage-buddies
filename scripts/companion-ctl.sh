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
        first=$(basename -- "$(printf '%s\n' "$argv" | sed -n 1p)" 2>/dev/null)
        second=$(basename -- "$(printf '%s\n' "$argv" | sed -n 2p)" 2>/dev/null)
        # Who is running the script, not who mentions it. Matching the name
        # anywhere in the command line takes `vim scripts/usage-buddy-companion.py`
        # and `cp scripts/usage-buddy-companion.py ~/.local/bin/` — the second
        # of which is install.sh, so `stop` during an install truncates the file
        # it is installing. Position alone does not separate them either: vim
        # puts the name in the second slot exactly as the interpreter does.
        # buddy_peers.is_companion answers this correctly and this is the same
        # rule, in shell.
        # Digits and dots stripped, then compared whole, rather than a list of
        # globs per version shape. The list had a hole: `pypy3.10` matched
        # buddy_peers.is_companion and not this, so such a companion survived
        # `stop` and `start` left two of them running. Two implementations of
        # one rule that disagree are a contract nobody wrote.
        case "$(printf '%s' "$first" | tr -d '0-9.')" in
            python|pypy) [ "$second" = "$SCRIPT_NAME" ] && echo "$p" ;;
        esac
        [ "$first" = "$SCRIPT_NAME" ] && echo "$p"
    done
    # The scan succeeded whatever it found. Without this the function inherits
    # the status of its last iteration, and the last iteration is a `[ ... ] &&`
    # that fails for every interpreter running some other script — so `status`,
    # which pipes this into `wc -l` under `pipefail`, exited 1 or 0 depending on
    # which pid the glob happened to visit last. Measured: the same two
    # processes, a companion and a `python3 -m pytest`, renumbered so the
    # pytest one sorts last, printed the same correct count and exited 1
    # instead of 0.
    return 0
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
