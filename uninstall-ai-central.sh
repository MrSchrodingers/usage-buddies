#!/usr/bin/env bash
set -u

BIN_DIR="$HOME/.local/bin"
SHARE_DIR="$HOME/.local/share"
SYSTEMD_DIR="$HOME/.config/systemd/user"

for unit in ai-central-terminal.service ai-central-web.service ai-hub-monitor.service \
            ai-hub-restore.service claude-hub.service; do
    systemctl --user disable --now "$unit" >/dev/null 2>&1 || true
    rm -f "$SYSTEMD_DIR/$unit"
done
systemctl --user daemon-reload >/dev/null 2>&1 || true

for script in claude-hub ch claude-hub-gui.py ai-central-open.py ai-central-web.py \
              ai-central-enable-https.sh ai-hub-state.py ai-hub-restore.py ai_hub_registry.py \
              ai-hub-registry.py; do
    rm -f "$BIN_DIR/$script"
done
rm -f "$SHARE_DIR/applications/ai-central-web.desktop" \
      "$SHARE_DIR/applications/ai-central-enable-https.desktop" \
      "$SHARE_DIR/icons/hicolor/scalable/apps/ai-central.svg"
rm -rf "$SHARE_DIR/ai-central-web"

printf 'AI Central removida. As sessões tmux e o registro foram preservados.\n'
printf 'Para encerrar sessões: tmux kill-session -t claude-hub\n'
printf 'Para apagar o registro: rm -rf ~/.config/ai-central\n'
