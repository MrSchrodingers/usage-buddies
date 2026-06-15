#!/bin/bash
# Persists the panel display mode to ~/.claude/widget-config.json.
# Invoked by the plasmoid popup's mode-switcher button with the new mode as $1.
MODE="$1"
CONFIG="$HOME/.claude/widget-config.json"

if [ -z "$MODE" ]; then
    echo "usage: $0 <displayMode>" >&2
    exit 1
fi

# Path and mode both passed via argv to avoid embedding either in the Python
# source (robust against special characters in $HOME and shell injection).
python3 -c "
import json, os, sys
path, mode = sys.argv[1], sys.argv[2]
d = {}
if os.path.exists(path):
    try:
        with open(path) as f:
            d = json.load(f)
    except Exception:
        d = {}
d['displayMode'] = mode
with open(path, 'w') as f:
    json.dump(d, f, indent=2)
" "$CONFIG" "$MODE"
