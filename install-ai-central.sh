#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="$HOME/.local/bin"
SHARE_DIR="$HOME/.local/share"
SYSTEMD_DIR="$HOME/.config/systemd/user"
APPLICATIONS_DIR="$SHARE_DIR/applications"
WEB_DIR="$SHARE_DIR/ai-central-web"
ICON_DIR="$SHARE_DIR/icons/hicolor/scalable/apps"

require() {
    command -v "$1" >/dev/null 2>&1 || {
        printf 'Dependência ausente: %s\n' "$1" >&2
        exit 2
    }
}

for command in tmux ssh tailscale python3; do require "$command"; done
python3 -c 'import fastapi, pydantic, uvicorn' 2>/dev/null || {
    printf 'Dependências Python ausentes. Instale: python3 -m pip install --user fastapi pydantic uvicorn\n' >&2
    exit 2
}

mkdir -p "$BIN_DIR" "$SYSTEMD_DIR" "$APPLICATIONS_DIR" "$WEB_DIR" "$ICON_DIR"

for script in claude-hub claude-hub-gui.py ai-central-open.py ai-central-web.py \
              ai-central-enable-https.sh ai-hub-state.py ai-hub-restore.py ai_hub_registry.py; do
    install -m 755 "$REPO_DIR/scripts/$script" "$BIN_DIR/$script"
done

cp -a "$REPO_DIR/ai-central-web/." "$WEB_DIR/"
if [ ! -f "$WEB_DIR/node_modules/@xterm/xterm/lib/xterm.js" ]; then
    if command -v pnpm >/dev/null 2>&1; then
        pnpm --dir "$WEB_DIR" install --prod --frozen-lockfile
    elif command -v npm >/dev/null 2>&1; then
        npm --prefix "$WEB_DIR" install --omit=dev
    else
        printf 'pnpm ou npm é necessário para instalar o terminal web.\n' >&2
        exit 2
    fi
fi

install -m 644 "$REPO_DIR/ai-central-web/static/icon.svg" "$ICON_DIR/ai-central.svg"
install -m 644 "$REPO_DIR/desktop/ai-central-web.desktop" "$APPLICATIONS_DIR/ai-central-web.desktop"
install -m 644 "$REPO_DIR/desktop/ai-central-enable-https.desktop" "$APPLICATIONS_DIR/ai-central-enable-https.desktop"
for unit in claude-hub.service ai-hub-restore.service ai-hub-monitor.service ai-central-web.service ai-central-terminal.service; do
    install -m 644 "$REPO_DIR/systemd/$unit" "$SYSTEMD_DIR/$unit"
done

systemctl --user daemon-reload
systemctl --user enable --now claude-hub.service ai-hub-restore.service ai-hub-monitor.service ai-central-web.service

printf '\nAI Central instalada.\n'
printf '  Estado:      claude-hub status\n'
printf '  Diagnóstico: claude-hub doctor\n'
printf '  Interface:   claude-hub gui\n'
printf '  URL móvel:   claude-hub web\n'
printf 'A abertura automática do Konsole é opcional:\n'
printf '  systemctl --user enable --now ai-central-terminal.service\n'
