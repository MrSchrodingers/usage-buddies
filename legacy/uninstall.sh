#!/bin/bash
set -uo pipefail
# Note: no -e — uninstall must continue even if individual steps fail

RED='\033[0;31m'
GREEN='\033[0;32m'
AMBER='\033[0;33m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "${BOLD}═══════════════════════════════════════════${NC}"
echo -e "${BOLD}  Claude Usage Monitor - Uninstaller       ${NC}"
echo -e "${BOLD}═══════════════════════════════════════════${NC}"
echo ""

REMOVED=0

# ── Kill running tray app (only our specific binary) ──
if command -v pgrep &>/dev/null && pgrep -x "claude-usage-tray" &>/dev/null; then
    pkill -x "claude-usage-tray" 2>/dev/null
    echo -e "  ${GREEN}✓${NC} Stopped running tray app"
    ((REMOVED++))
fi

# ── Remove systemd timer (only if systemd available) ──
if command -v systemctl &>/dev/null && systemctl --user status &>/dev/null 2>&1; then
    if systemctl --user is-enabled claude-usage-collector.timer &>/dev/null 2>&1; then
        systemctl --user disable --now claude-usage-collector.timer 2>/dev/null
        echo -e "  ${GREEN}✓${NC} Disabled systemd timer"
        ((REMOVED++))
    fi
    # Only remove our specific service files
    for f in claude-usage-collector.service claude-usage-collector.timer; do
        if [ -f "$HOME/.config/systemd/user/$f" ]; then
            rm -f "$HOME/.config/systemd/user/$f"
        fi
    done
    systemctl --user daemon-reload 2>/dev/null
fi

# ── Remove plasmoid (only our specific widget ID) ──
PLASMOID_DIR="$HOME/.local/share/plasma/plasmoids/org.kde.plasma.claudeusage"
if [ -d "$PLASMOID_DIR" ]; then
    # Verify it's actually our widget before deleting
    if [ -f "$PLASMOID_DIR/metadata.json" ] && grep -q "claudeusage" "$PLASMOID_DIR/metadata.json" 2>/dev/null; then
        rm -rf "$PLASMOID_DIR"
        echo -e "  ${GREEN}✓${NC} Removed KDE Plasmoid"
        ((REMOVED++))
    fi
fi

# ── Remove icon (only our specific icon) ──
ICON_PATH="$HOME/.local/share/icons/hicolor/48x48/apps/claude-logo.png"
if [ -f "$ICON_PATH" ]; then
    rm -f "$ICON_PATH"
fi

# ── Remove our binaries (exact paths only) ──
for f in "$HOME/.local/bin/claude-usage-collector.py" "$HOME/.local/bin/claude-usage-tray"; do
    if [ -f "$f" ]; then
        rm -f "$f"
        echo -e "  ${GREEN}✓${NC} Removed $(basename "$f")"
        ((REMOVED++))
    fi
done

# ── Remove autostart (only our specific desktop file) ──
AUTOSTART="$HOME/.config/autostart/claude-usage-tray.desktop"
if [ -f "$AUTOSTART" ]; then
    # Verify it's ours before deleting
    if grep -q "claude-usage-tray" "$AUTOSTART" 2>/dev/null; then
        rm -f "$AUTOSTART"
        echo -e "  ${GREEN}✓${NC} Removed autostart entry"
        ((REMOVED++))
    fi
fi

# ── Remove only our widget data files (never touch other .claude files) ──
# NOTE: stats-cache.json belongs to Claude Code itself — never delete it.
for f in widget-data.json widget-config.json widget-status-prev.json; do
    if [ -f "$HOME/.claude/$f" ]; then
        rm -f "$HOME/.claude/$f"
    fi
done
echo -e "  ${GREEN}✓${NC} Removed widget data files"

# ── Remove temp cookie files (only our specific pattern) ──
rm -f /tmp/claude_chrome_*.sqlite* 2>/dev/null
rm -f /tmp/claude_ff_*.sqlite* 2>/dev/null
rm -f "$(python3 -c 'import tempfile; print(tempfile.gettempdir())' 2>/dev/null)/claude_chrome_"*.sqlite* 2>/dev/null
rm -f "$(python3 -c 'import tempfile; print(tempfile.gettempdir())' 2>/dev/null)/claude_ff_"*.sqlite* 2>/dev/null

echo ""
echo -e "${GREEN}  Uninstall complete. ($REMOVED components removed)${NC}"
echo ""
if command -v plasmashell &>/dev/null; then
    echo "  If the plasmoid is still visible, right-click it → Remove."
    echo ""
fi
