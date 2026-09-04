#!/data/data/com.termux/files/usr/bin/bash
set -eu

SOURCE_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
HOST="${1:-}"
REMOTE_USER="${2:-ti}"

if [ -z "$HOST" ]; then
    printf 'Uso: bash %s <IP-Tailscale-do-PC> [usuario]\n' "$0" >&2
    exit 2
fi
case "$HOST" in
    *[!A-Za-z0-9._:-]*)
        printf 'Host invalido: %s\n' "$HOST" >&2
        exit 2
        ;;
esac
case "$REMOTE_USER" in
    *[!A-Za-z0-9._-]*)
        printf 'Usuario invalido: %s\n' "$REMOTE_USER" >&2
        exit 2
        ;;
esac

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$HOME/.config/ai-central/backups/$STAMP"
mkdir -p "$BACKUP" "$HOME/.config/ai-central" "$HOME/.termux" "$HOME/.shortcuts"

for path in "$HOME/.config/ai-central/ssh-config" "$HOME/.termux/termux.properties" \
            "$HOME/.shortcuts/PC-Hub" "$HOME/.shortcuts/PC-Shell"; do
    if [ -f "$path" ]; then
        cp -p "$path" "$BACKUP/$(basename "$path")"
    fi
done

sed -e "s/__AI_CENTRAL_HOST__/$HOST/g" -e "s/__AI_CENTRAL_USER__/$REMOTE_USER/g" \
    "$SOURCE_DIR/ssh-config.template" > "$HOME/.config/ai-central/ssh-config"
cp "$SOURCE_DIR/termux.properties" "$HOME/.termux/termux.properties"
cp "$SOURCE_DIR/PC-Hub" "$HOME/.shortcuts/PC-Hub"
cp "$SOURCE_DIR/PC-Shell" "$HOME/.shortcuts/PC-Shell"
chmod 600 "$HOME/.config/ai-central/ssh-config"
chmod 700 "$HOME/.shortcuts/PC-Hub" "$HOME/.shortcuts/PC-Shell"
termux-reload-settings >/dev/null 2>&1 || true

printf '\nAI Central instalada no Termux.\n'
printf 'Host: %s@%s\n' "$REMOTE_USER" "$HOST"
printf 'Backup: %s\n' "$BACKUP"
printf 'Abra o widget Termux:Widget e toque em PC-Hub.\n'
