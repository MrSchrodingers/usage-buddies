#!/data/data/com.termux/files/usr/bin/bash
set -eu

SOURCE_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
HOST="${1:-}"
REMOTE_USER="${2:-ti}"
RESULT_FILE="${3:-}"
LAUNCH_MODE="${4:-}"
RESULT_STATUS="error"
RESULT_MESSAGE="instalacao interrompida"
PUBLIC_KEY_EXPORT=""
BACKUP=""
MUTATED=false

write_result() {
    [ -n "$RESULT_FILE" ] || return 0
    result_dir="$(dirname -- "$RESULT_FILE")"
    mkdir -p "$result_dir"
    temporary="$RESULT_FILE.tmp.$$"
    {
        printf 'status=%s\n' "$RESULT_STATUS"
        printf 'message=%s\n' "$RESULT_MESSAGE"
        printf 'host=%s\n' "$HOST"
        printf 'user=%s\n' "$REMOTE_USER"
        printf 'backup=%s\n' "$BACKUP"
        printf 'public_key=%s\n' "$PUBLIC_KEY_EXPORT"
    } > "$temporary"
    chmod 600 "$temporary" 2>/dev/null || true
    mv -f "$temporary" "$RESULT_FILE"
}

on_exit() {
    status=$?
    trap - EXIT
    if [ "$status" -ne 0 ] && [ "$RESULT_MESSAGE" = "instalacao interrompida" ]; then
        RESULT_MESSAGE="falha inesperada, codigo $status"
    fi
    if [ "$status" -ne 0 ] && $MUTATED && [ -n "$BACKUP" ]; then
        restore_backup || true
        RESULT_MESSAGE="$RESULT_MESSAGE; configuracao anterior restaurada"
    fi
    write_result
    exit "$status"
}
trap on_exit EXIT

fail() {
    RESULT_MESSAGE="$1"
    printf 'Erro: %s\n' "$1" >&2
    exit 1
}

if [ -z "$HOST" ]; then
    printf 'Uso: bash %s <IP-Tailscale-do-PC> [usuario] [arquivo-resultado] [--launch]\n' "$0" >&2
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

for required in ssh-config.template termux.properties PC-Hub PC-Shell ai-central-boot; do
    [ -f "$SOURCE_DIR/$required" ] || fail "payload incompleto: $required ausente"
done

if ! command -v ssh >/dev/null 2>&1 || ! command -v ssh-keygen >/dev/null 2>&1; then
    printf 'Instalando OpenSSH no Termux...\n'
    pkg install -y openssh || fail "nao foi possivel instalar openssh"
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$HOME/.config/ai-central/backups/$STAMP"
mkdir -p "$BACKUP" "$HOME/.config/ai-central" "$HOME/.termux" "$HOME/.termux/boot" \
    "$HOME/.shortcuts" "$HOME/.ssh"
chmod 700 "$HOME/.ssh"

for path in "$HOME/.config/ai-central/ssh-config" "$HOME/.termux/termux.properties" \
            "$HOME/.shortcuts/PC-Hub" "$HOME/.shortcuts/PC-Shell" \
            "$HOME/.termux/boot/ai-central"; do
    if [ -f "$path" ]; then
        cp -p "$path" "$BACKUP/$(basename "$path")"
    else
        printf '%s\n' "$path" >> "$BACKUP/missing.txt"
    fi
done

restore_one() {
    destination="$1"
    saved="$BACKUP/$(basename "$destination")"
    if [ -f "$saved" ]; then
        cp -p "$saved" "$destination"
    elif [ -f "$BACKUP/missing.txt" ] && grep -Fxq "$destination" "$BACKUP/missing.txt"; then
        rm -f "$destination"
    fi
}

restore_backup() {
    restore_one "$HOME/.config/ai-central/ssh-config"
    restore_one "$HOME/.termux/termux.properties"
    restore_one "$HOME/.shortcuts/PC-Hub"
    restore_one "$HOME/.shortcuts/PC-Shell"
    restore_one "$HOME/.termux/boot/ai-central"
    termux-reload-settings >/dev/null 2>&1 || true
}

MUTATED=true

ssh_temporary="$HOME/.config/ai-central/ssh-config.tmp.$$"
sed -e "s/__AI_CENTRAL_HOST__/$HOST/g" -e "s/__AI_CENTRAL_USER__/$REMOTE_USER/g" \
    "$SOURCE_DIR/ssh-config.template" > "$ssh_temporary"
chmod 600 "$ssh_temporary"
mv -f "$ssh_temporary" "$HOME/.config/ai-central/ssh-config"

properties="$HOME/.termux/termux.properties"
properties_temporary="$properties.tmp.$$"
if [ -f "$properties" ] && grep -Fq '# BEGIN AI CENTRAL MANAGED SETTINGS' "$properties"; then
    awk '
        $0 == "# BEGIN AI CENTRAL MANAGED SETTINGS" { managed=1; next }
        $0 == "# END AI CENTRAL MANAGED SETTINGS" { managed=0; next }
        !managed { print }
    ' "$properties" > "$properties_temporary"
    printf '\n' >> "$properties_temporary"
    cat "$SOURCE_DIR/termux.properties" >> "$properties_temporary"
elif [ -f "$properties" ] && grep -Fq '# AI Central: barra de controle móvel para Termux.' "$properties"; then
    # Releases antigas eram donas do arquivo inteiro, sem marcadores. A cópia
    # integral já foi guardada e é substituída pelo formato mesclável atual.
    cp "$SOURCE_DIR/termux.properties" "$properties_temporary"
elif [ -f "$properties" ]; then
    cp "$properties" "$properties_temporary"
    printf '\n' >> "$properties_temporary"
    cat "$SOURCE_DIR/termux.properties" >> "$properties_temporary"
else
    cp "$SOURCE_DIR/termux.properties" "$properties_temporary"
fi
mv -f "$properties_temporary" "$properties"

install -m 700 "$SOURCE_DIR/PC-Hub" "$HOME/.shortcuts/PC-Hub"
install -m 700 "$SOURCE_DIR/PC-Shell" "$HOME/.shortcuts/PC-Shell"
install -m 700 "$SOURCE_DIR/ai-central-boot" "$HOME/.termux/boot/ai-central"
chmod 700 "$HOME/.shortcuts/PC-Hub" "$HOME/.shortcuts/PC-Shell"

if [ ! -f "$HOME/.ssh/id_ed25519" ]; then
    ssh-keygen -q -t ed25519 -N '' -C ai-central-android -f "$HOME/.ssh/id_ed25519" \
        || fail "nao foi possivel gerar a chave SSH"
fi
chmod 600 "$HOME/.ssh/id_ed25519"
chmod 644 "$HOME/.ssh/id_ed25519.pub"

if [ -n "$RESULT_FILE" ]; then
    PUBLIC_KEY_EXPORT="$(dirname -- "$RESULT_FILE")/id_ed25519.pub"
    cp "$HOME/.ssh/id_ed25519.pub" "$PUBLIC_KEY_EXPORT"
    chmod 644 "$PUBLIC_KEY_EXPORT" 2>/dev/null || true
fi
termux-reload-settings >/dev/null 2>&1 || true

RESULT_STATUS="ok"
RESULT_MESSAGE="AI Central instalada no Termux"
write_result

printf '\nAI Central instalada no Termux.\n'
printf 'Host: %s@%s\n' "$REMOTE_USER" "$HOST"
printf 'Backup: %s\n' "$BACKUP"
printf 'Abra o widget Termux:Widget e toque em PC-Hub.\n'
printf 'Com Termux:Boot, o preflight do hub roda após desbloquear o aparelho.\n'

trap - EXIT
if [ "$LAUNCH_MODE" = "--launch" ]; then
    exec "$HOME/.shortcuts/PC-Hub"
fi
