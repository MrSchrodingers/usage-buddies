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
LOG="${XDG_CACHE_HOME:-$HOME/.cache}/usage-buddies/companion.log"

# Echoes the pid of every running companion.
companion_pids() {
    local pid p fd argv0 argv1 first second interpreter
    for pid in "$PROC"/[0-9]*; do
        p="${pid#"$PROC"/}"
        [ "$p" = "$SELF" ] && continue
        argv0=
        argv1=
        { exec {fd}<"$pid/cmdline"; } 2>/dev/null || continue
        IFS= read -r -d '' argv0 <&"$fd" || true
        IFS= read -r -d '' argv1 <&"$fd" || true
        exec {fd}<&-
        first="${argv0##*/}"
        second="${argv1##*/}"
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
        interpreter="${first//[0-9.]/}"
        case "$interpreter" in
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
        # Output goes to a file, not to /dev/null. It went to /dev/null, and
        # the cost was a mascot that would occasionally vanish with no trace
        # anywhere: not in the journal, since nothing here is a systemd unit,
        # and not on a terminal, since the widget starts it. A crash and a
        # deliberate stop looked identical from outside.
        #
        # One rotation, because the interesting log is almost always the
        # previous run's — something restarts the companion, and by the time
        # anyone asks why it went, the fresh log is from the process that
        # replaced it. Truncated to the tail so a crash loop cannot fill the
        # disk, and 0600 like the rest of this cache.
        mkdir -p "$(dirname "$LOG")" 2>/dev/null
        if [ -f "$LOG" ]; then
            tail -c 262144 "$LOG" > "$LOG.1" 2>/dev/null
            chmod 600 "$LOG.1" 2>/dev/null
        fi
        : > "$LOG" 2>/dev/null && chmod 600 "$LOG" 2>/dev/null
        setsid "$BIN" "$@" >>"$LOG" 2>&1 < /dev/null &
        ;;
    status)
        companion_pids | wc -l
        ;;
    log)
        # Both runs, oldest first: the one that died and the one that replaced it.
        for f in "$LOG.1" "$LOG"; do
            [ -s "$f" ] && { echo "── $f"; cat "$f"; }
        done
        ;;
    *)
        echo "usage: companion-ctl.sh start|stop|status|log [args...]" >&2
        exit 2
        ;;
esac
