#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
DEVICE_DIR="/sdcard/Download/ai-central-mobile"
SERIAL=""
HOST=""
REMOTE_USER="$USER"
MODE="direct"
LAUNCH=true
WAIT_SECONDS=120
REQUIRE_BOOT=false

usage() {
    cat <<'EOF'
Uso: ./install-ai-central-android.sh [opções]

Instala a parte Android pelo PC, usando um aparelho conectado e autorizado no ADB.

Opções:
  --serial ID       seleciona o aparelho quando há mais de um
  --host IP         IPv4 Tailscale do PC; detectado automaticamente por padrão
  --user USUARIO    usuário SSH do PC; padrão: usuário atual
  --manual          transfere e verifica, mas imprime o comando para executar no Termux
  --no-launch       instala sem abrir PC-Hub ao terminar
  --require-boot    falha se Termux:Boot não estiver instalado
  --timeout SEG     espera máxima pelo instalador móvel; padrão: 120
  --check           apenas valida PC, ADB, aparelho e aplicativos
  -h, --help        mostra esta ajuda

Exemplo totalmente automático:
  ./install-ai-central-android.sh --serial 0123456789ABCDEF
EOF
}

CHECK_ONLY=false
while [ "$#" -gt 0 ]; do
    case "$1" in
        --serial) SERIAL="${2:?valor ausente para --serial}"; shift 2 ;;
        --host) HOST="${2:?valor ausente para --host}"; shift 2 ;;
        --user) REMOTE_USER="${2:?valor ausente para --user}"; shift 2 ;;
        --manual) MODE="manual"; shift ;;
        --no-launch) LAUNCH=false; shift ;;
        --require-boot) REQUIRE_BOOT=true; shift ;;
        --timeout) WAIT_SECONDS="${2:?valor ausente para --timeout}"; shift 2 ;;
        --check) CHECK_ONLY=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Opção desconhecida: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
done

command -v adb >/dev/null 2>&1 || { printf 'adb não encontrado. Instale Android Platform Tools.\n' >&2; exit 2; }
command -v tailscale >/dev/null 2>&1 || { printf 'tailscale não encontrado no PC.\n' >&2; exit 2; }
command -v sha256sum >/dev/null 2>&1 || { printf 'sha256sum não encontrado no PC.\n' >&2; exit 2; }
command -v ss >/dev/null 2>&1 || { printf 'ss não encontrado no PC (pacote iproute2).\n' >&2; exit 2; }

case "$REMOTE_USER" in
    ''|*[!A-Za-z0-9._-]*) printf 'Usuário SSH inválido: %s\n' "$REMOTE_USER" >&2; exit 2 ;;
esac
case "$WAIT_SECONDS" in
    ''|*[!0-9]*) printf 'Timeout inválido: %s\n' "$WAIT_SECONDS" >&2; exit 2 ;;
esac

mapfile -t DEVICES < <(adb devices | awk '$2 == "device" { print $1 }')
if [ -z "$SERIAL" ]; then
    if [ "${#DEVICES[@]}" -ne 1 ]; then
        printf 'Esperado exatamente um aparelho ADB; encontrados: %s. Use --serial.\n' "${#DEVICES[@]}" >&2
        adb devices -l >&2
        exit 3
    fi
    SERIAL="${DEVICES[0]}"
elif ! printf '%s\n' "${DEVICES[@]}" | grep -Fxq -- "$SERIAL"; then
    printf 'Aparelho %s não está autorizado no ADB.\n' "$SERIAL" >&2
    adb devices -l >&2
    exit 3
fi
ADB=(adb -s "$SERIAL")

if [ -z "$HOST" ]; then
    HOST="$(tailscale ip -4 2>/dev/null | head -n 1 || true)"
fi
if [[ ! "$HOST" =~ ^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$ ]] ||
   (( 10#${BASH_REMATCH[1]:-999} != 100 ||
      10#${BASH_REMATCH[2]:-999} < 64 || 10#${BASH_REMATCH[2]:-999} > 127 ||
      10#${BASH_REMATCH[3]:-999} > 255 || 10#${BASH_REMATCH[4]:-999} > 255 )); then
    printf 'Use um IPv4 Tailscale CGNAT válido (100.64.0.0/10) para --host; recebido: %s\n' "$HOST" >&2
    exit 2
fi

for package in com.termux com.tailscale.ipn; do
    if ! "${ADB[@]}" shell pm path "$package" 2>/dev/null | grep -q '^package:'; then
        printf 'Aplicativo obrigatório ausente no Android: %s\n' "$package" >&2
        exit 4
    fi
done
if ! "${ADB[@]}" shell pm path com.termux.widget 2>/dev/null | grep -q '^package:'; then
    printf 'Aviso: Termux:Widget não está instalado; PC-Hub funcionará pelo Termux, mas não como ícone.\n' >&2
fi
if ! "${ADB[@]}" shell pm path com.termux.boot 2>/dev/null | grep -q '^package:'; then
    if $REQUIRE_BOOT; then
        printf 'Termux:Boot é obrigatório neste modo. Instale-o pela mesma origem do Termux e abra-o uma vez.\n' >&2
        exit 4
    fi
    printf 'Aviso: Termux:Boot não está instalado; o preflight automático após reiniciar o Android ficará inativo.\n' >&2
fi

if ! ss -ltn 2>/dev/null | awk '$4 ~ /:22$/ { found=1 } END { exit !found }'; then
    printf 'O PC não está ouvindo SSH na porta 22. Ative openssh-server antes da instalação Android.\n' >&2
    exit 4
fi

printf 'Pré-validação concluída.\n'
printf '  aparelho: %s\n  PC: %s@%s\n  modo: %s\n' "$SERIAL" "$REMOTE_USER" "$HOST" "$MODE"
if $CHECK_ONLY; then
    exit 0
fi

FILES=(PC-Hub PC-Shell ai-central-boot install-termux.sh ssh-config.template termux.properties)
"${ADB[@]}" shell mkdir -p "$DEVICE_DIR"
for file in "${FILES[@]}"; do
    [ -f "$REPO_DIR/mobile/$file" ] || { printf 'Payload ausente: mobile/%s\n' "$file" >&2; exit 5; }
    "${ADB[@]}" push "$REPO_DIR/mobile/$file" "$DEVICE_DIR/$file" >/dev/null
    local_hash="$(sha256sum "$REPO_DIR/mobile/$file" | awk '{print $1}')"
    remote_hash="$("${ADB[@]}" shell sha256sum "$DEVICE_DIR/$file" | tr -d '\r' | awk '{print $1}')"
    if [ "$local_hash" != "$remote_hash" ]; then
        printf 'Hash divergente após ADB push: %s\n' "$file" >&2
        exit 5
    fi
done
printf 'Payload transferido e verificado: %s arquivos.\n' "${#FILES[@]}"

RESULT_FILE="$DEVICE_DIR/install-result.txt"
PUBLIC_KEY_FILE="$DEVICE_DIR/id_ed25519.pub"
"${ADB[@]}" shell rm -f "$RESULT_FILE" "$PUBLIC_KEY_FILE"

manual_command="bash $DEVICE_DIR/install-termux.sh $HOST $REMOTE_USER $RESULT_FILE"
if $LAUNCH; then
    manual_command="$manual_command --launch"
fi
if [ "$MODE" = "manual" ]; then
    printf '\nAbra o Termux e execute:\n  %s\n' "$manual_command"
    exit 0
fi

# RUN_COMMAND intentionally is not used: adb shell does not hold Termux's
# dangerous com.termux.permission.RUN_COMMAND permission. A new local session
# prevents command injection into an attached Claude or another foreground job.
mapfile -t OLD_MOBILE_CLIENTS < <(tmux list-clients -F '#{client_tty}|#{client_session}' 2>/dev/null | awk -F '|' '$2 == "claude-mobile" { print $1 }')
for client in "${OLD_MOBILE_CLIENTS[@]}"; do
    tmux detach-client -t "$client" 2>/dev/null || true
done
[ "${#OLD_MOBILE_CLIENTS[@]}" -eq 0 ] || printf 'Cliente móvel anterior apenas desanexado; processos e workflows continuam vivos.\n'

"${ADB[@]}" shell input keyevent KEYCODE_WAKEUP >/dev/null
"${ADB[@]}" shell am start -n com.termux/.app.TermuxActivity >/dev/null
sleep 2
"${ADB[@]}" shell input keycombination KEYCODE_CTRL_LEFT KEYCODE_ALT_LEFT KEYCODE_C
sleep 2
foreground="$("${ADB[@]}" shell dumpsys activity activities | grep -m1 'mResumedActivity' || true)"
if [[ "$foreground" != *com.termux* ]]; then
    printf 'O Termux não ficou em primeiro plano. Desbloqueie o aparelho e tente novamente.\n' >&2
    exit 6
fi

encoded_command="${manual_command// /%s}"
"${ADB[@]}" shell input text "$encoded_command"
"${ADB[@]}" shell input keyevent KEYCODE_ENTER

result=""
for ((second = 0; second < WAIT_SECONDS; second++)); do
    if result="$("${ADB[@]}" shell cat "$RESULT_FILE" 2>/dev/null)" && [[ "$result" == status=* ]]; then
        break
    fi
    sleep 1
done
result="${result//$'\r'/}"
if ! grep -Fxq 'status=ok' <<< "$result"; then
    printf 'O instalador Termux não confirmou sucesso em %ss.\n' "$WAIT_SECONDS" >&2
    [ -z "$result" ] || printf '%s\n' "$result" >&2
    printf 'Fallback manual seguro:\n  %s\n' "$manual_command" >&2
    exit 7
fi

public_key="$("${ADB[@]}" shell cat "$PUBLIC_KEY_FILE" 2>/dev/null | tr -d '\r\n')"
read -r key_type key_blob _ <<< "$public_key"
if [ "$key_type" != "ssh-ed25519" ] || [[ ! "$key_blob" =~ ^[A-Za-z0-9+/=]+$ ]]; then
    printf 'A chave pública devolvida pelo Android é inválida.\n' >&2
    exit 8
fi
authorised_line="$key_type $key_blob ai-central-android"
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
touch "$HOME/.ssh/authorized_keys"
chmod 600 "$HOME/.ssh/authorized_keys"
if ! awk -v type="$key_type" -v blob="$key_blob" \
    '$1 == type && $2 == blob { found=1 } END { exit !found }' "$HOME/.ssh/authorized_keys"; then
    printf '%s\n' "$authorised_line" >> "$HOME/.ssh/authorized_keys"
    printf 'Chave SSH do Android autorizada no PC.\n'
else
    printf 'Chave SSH do Android já estava autorizada.\n'
fi

if $LAUNCH; then
    connected=false
    for _ in {1..30}; do
        if tmux list-clients -F '#{client_session}' 2>/dev/null | grep -Fxq claude-mobile; then
            connected=true
            break
        fi
        sleep 1
    done
    if ! $connected; then
        printf 'Instalação concluída, mas PC-Hub ainda não apareceu no tmux. Confira o Tailscale no celular.\n' >&2
        exit 9
    fi
fi

printf '\nAI Central Android instalada e validada via ADB.\n'
printf '%s\n' "$result"
