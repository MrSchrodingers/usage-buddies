#!/bin/bash
# GNOME Setup Helper — installs the AppIndicator extension so the Tauri tray
# icon becomes visible on Ubuntu GNOME, Fedora GNOME, and Arch+GNOME.
#
# Called automatically by install.sh when gnome-shell is detected and KDE is not.
# Safe to run standalone: idempotent, exits 0 if the extension is already enabled.
set -euo pipefail

GREEN='\033[0;32m'
AMBER='\033[0;33m'
RED='\033[0;31m'
DIM='\033[2m'
NC='\033[0m'

EXTENSION_UUID="appindicatorsupport@rgcjonas.gmail.com"

echo -e "${AMBER}  GNOME detected — tray icon requires the AppIndicator extension${NC}"

if command -v gnome-extensions &>/dev/null \
    && gnome-extensions list 2>/dev/null | grep -q "$EXTENSION_UUID"; then
    if gnome-extensions list --enabled 2>/dev/null | grep -q "$EXTENSION_UUID"; then
        echo -e "  ${GREEN}✓${NC} AppIndicator extension already installed and enabled"
        exit 0
    fi
    echo -e "  ${DIM}  Extension installed but disabled — enabling...${NC}"
    gnome-extensions enable "$EXTENSION_UUID" 2>/dev/null || true
    echo -e "  ${AMBER}!${NC} Log out and back in for the tray icon to appear"
    exit 0
fi

if ! command -v gnome-extensions-cli &>/dev/null; then
    echo -e "  ${DIM}  Installing gnome-extensions-cli via pip...${NC}"
    if ! { pip3 install --user --quiet gnome-extensions-cli 2>/dev/null \
        || python3 -m pip install --user --quiet gnome-extensions-cli 2>/dev/null; }; then
        echo -e "  ${RED}!${NC} Could not install gnome-extensions-cli"
        echo -e "  ${DIM}    Install the extension manually:${NC}"
        echo -e "  ${DIM}    https://extensions.gnome.org/extension/615/appindicator-support/${NC}"
        echo -e "  ${DIM}    Or use Super+Shift+C to open the popup without the tray icon${NC}"
        exit 1
    fi
fi

export PATH="$HOME/.local/bin:$PATH"

echo -e "  ${DIM}  Installing AppIndicator extension...${NC}"
if gnome-extensions-cli install "$EXTENSION_UUID" 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Extension installed"
    gnome-extensions-cli enable "$EXTENSION_UUID" 2>/dev/null || true
    echo -e "  ${AMBER}!${NC} ${AMBER}Log out and back in${NC} (or Alt+F2 → r on X11) to load the tray icon"
    echo -e "  ${DIM}    Afterwards: usage-buddies-tray${NC}"
else
    echo -e "  ${RED}!${NC} Extension install failed"
    echo -e "  ${DIM}    Install manually: https://extensions.gnome.org/extension/615/appindicator-support/${NC}"
    echo -e "  ${DIM}    Or use Super+Shift+C to open the popup without the tray icon${NC}"
    exit 1
fi
