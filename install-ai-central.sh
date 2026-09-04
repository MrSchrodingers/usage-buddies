#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="$HOME/.local/bin"
SHARE_DIR="$HOME/.local/share"
STATE_DIR="$HOME/.local/state/ai-central"
SYSTEMD_DIR="$HOME/.config/systemd/user"
APPLICATIONS_DIR="$SHARE_DIR/applications"
WEB_DIR="$SHARE_DIR/ai-central-web"
ICON_DIR="$SHARE_DIR/icons/hicolor/scalable/apps"

INSTALL_DEPS=false
ALWAYS_ON=false
ENABLE_TERMINAL=true
INSTALL_ANDROID=false
ANDROID_MANUAL=false
ANDROID_LAUNCH=true
CHECK_ONLY=false
DRY_RUN=false
ANDROID_SERIAL=""
ANDROID_HOST=""
ANDROID_USER="$USER"
MUTATION_STARTED=false
COMMITTED=false
STAGED_WEB=""
BACKUP=""

usage() {
    cat <<'EOF'
Uso: ./install-ai-central.sh [opções]

Instala ou atualiza a AI Central no PC de forma idempotente e transacional.

Opções:
  --auto              instala dependências, ativa disponibilidade pré-login e abre o Konsole
  --install-deps      instala dependências conhecidas pelo gerenciador do sistema
  --always-on         habilita linger, SSH e Tailscale para funcionar antes do login gráfico
  --login-only        não altera linger nem serviços de sistema
  --no-terminal       não abre o Konsole automaticamente ao iniciar a sessão gráfica
  --android           após o PC, instala diretamente no Android conectado por ADB
  --android-manual    transfere o Android, mas deixa a execução final para o Termux
  --serial ID         seleciona o aparelho ADB
  --host IP           usa este IPv4 Tailscale no Android
  --remote-user USER  usuário SSH configurado no Android; padrão: usuário atual
  --no-mobile-launch  instala no Android sem abrir PC-Hub ao final
  --check             apenas audita requisitos, fontes e instalação atual
  --dry-run           mostra o plano resolvido sem alterar nada
  -h, --help          mostra esta ajuda

Exemplos:
  ./install-ai-central.sh
  ./install-ai-central.sh --auto
  ./install-ai-central.sh --auto --android --serial 0123456789ABCDEF
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --auto) INSTALL_DEPS=true; ALWAYS_ON=true; ENABLE_TERMINAL=true; shift ;;
        --install-deps) INSTALL_DEPS=true; shift ;;
        --always-on) ALWAYS_ON=true; shift ;;
        --login-only) ALWAYS_ON=false; shift ;;
        --no-terminal) ENABLE_TERMINAL=false; shift ;;
        --android) INSTALL_ANDROID=true; shift ;;
        --android-manual) INSTALL_ANDROID=true; ANDROID_MANUAL=true; shift ;;
        --serial) ANDROID_SERIAL="${2:?valor ausente para --serial}"; shift 2 ;;
        --host) ANDROID_HOST="${2:?valor ausente para --host}"; shift 2 ;;
        --remote-user) ANDROID_USER="${2:?valor ausente para --remote-user}"; shift 2 ;;
        --no-mobile-launch) ANDROID_LAUNCH=false; shift ;;
        --check) CHECK_ONLY=true; shift ;;
        --dry-run) DRY_RUN=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Opção desconhecida: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
done

SCRIPT_NAMES=(
    claude-hub ch claude-hub-gui.py ai-central-open.py ai-central-web.py
    ai-central-enable-https.sh ai-hub-state.py ai-hub-restore.py ai_hub_registry.py
    ai-hub-registry.py
)
UNIT_NAMES=(
    claude-hub.service ai-hub-restore.service ai-hub-monitor.service
    ai-central-web.service ai-central-terminal.service
)
SOURCE_SHELLS=(
    "$REPO_DIR/install-ai-central.sh"
    "$REPO_DIR/install-ai-central-android.sh"
    "$REPO_DIR/uninstall-ai-central.sh"
    "$REPO_DIR/scripts/claude-hub"
    "$REPO_DIR/scripts/ch"
    "$REPO_DIR/scripts/ai-central-enable-https.sh"
    "$REPO_DIR/mobile/PC-Hub"
    "$REPO_DIR/mobile/PC-Shell"
    "$REPO_DIR/mobile/ai-central-boot"
    "$REPO_DIR/mobile/install-termux.sh"
)
SOURCE_PYTHONS=(
    "$REPO_DIR/scripts/claude-hub-gui.py"
    "$REPO_DIR/scripts/ai-central-open.py"
    "$REPO_DIR/scripts/ai-central-web.py"
    "$REPO_DIR/scripts/ai-hub-state.py"
    "$REPO_DIR/scripts/ai-hub-restore.py"
    "$REPO_DIR/scripts/ai_hub_registry.py"
)

validate_sources() {
    local source
    for source in "${SOURCE_SHELLS[@]}" "${SOURCE_PYTHONS[@]}" \
        "$REPO_DIR/ai-central-web/static/index.html" \
        "$REPO_DIR/ai-central-web/static/app.js" \
        "$REPO_DIR/ai-central-web/static/app.css"; do
        [ -f "$source" ] || { printf 'Fonte obrigatória ausente: %s\n' "$source" >&2; return 1; }
    done
    for source in "${SOURCE_SHELLS[@]}"; do
        bash -n "$source"
    done
    if command -v python3 >/dev/null 2>&1; then
        for source in "${SOURCE_PYTHONS[@]}"; do
            python3 -c 'import ast, pathlib, sys; ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))' "$source"
        done
    fi
    printf 'OK  fontes e sintaxe validadas.\n'
}

install_dependencies() {
    local need_tmux=false need_ssh=false need_sshd=false need_tailscale=false
    local need_python=false need_python_modules=false need_konsole=false need_adb=false
    local need_iproute=false need_node=false python_bin=""
    local -a packages=()

    command -v tmux >/dev/null 2>&1 || need_tmux=true
    command -v ssh >/dev/null 2>&1 || need_ssh=true
    if $ALWAYS_ON && ! command -v sshd >/dev/null 2>&1; then need_sshd=true; fi
    command -v tailscale >/dev/null 2>&1 || need_tailscale=true
    command -v python3 >/dev/null 2>&1 || need_python=true
    if [ -x /usr/bin/python3 ]; then python_bin=/usr/bin/python3; else python_bin="$(command -v python3 2>/dev/null || true)"; fi
    if [ -z "$python_bin" ] || ! "$python_bin" -c 'import fastapi, pydantic, uvicorn' 2>/dev/null; then
        need_python_modules=true
    fi
    if $ENABLE_TERMINAL && ! command -v konsole >/dev/null 2>&1; then need_konsole=true; fi
    if $INSTALL_ANDROID && ! command -v adb >/dev/null 2>&1; then need_adb=true; fi
    if $INSTALL_ANDROID && ! command -v ss >/dev/null 2>&1; then need_iproute=true; fi
    if [ ! -f "$REPO_DIR/ai-central-web/node_modules/@xterm/xterm/lib/xterm.js" ] && \
       ! command -v pnpm >/dev/null 2>&1 && ! command -v npm >/dev/null 2>&1; then
        need_node=true
    fi

    if command -v dnf >/dev/null 2>&1; then
        $need_tmux && packages+=(tmux)
        $need_ssh && packages+=(openssh-clients)
        $need_sshd && packages+=(openssh-server)
        $need_tailscale && packages+=(tailscale)
        $need_python && packages+=(python3)
        $need_python_modules && packages+=(python3-fastapi python3-pydantic python3-uvicorn)
        $need_konsole && packages+=(konsole)
        $need_adb && packages+=(android-tools)
        $need_iproute && packages+=(iproute)
        $need_node && packages+=(nodejs-npm)
        [ "${#packages[@]}" -eq 0 ] || sudo dnf install -y "${packages[@]}"
    elif command -v apt-get >/dev/null 2>&1; then
        $need_tmux && packages+=(tmux)
        $need_ssh && packages+=(openssh-client)
        $need_sshd && packages+=(openssh-server)
        $need_tailscale && packages+=(tailscale)
        $need_python && packages+=(python3)
        $need_python_modules && packages+=(python3-fastapi python3-pydantic python3-uvicorn)
        $need_konsole && packages+=(konsole)
        $need_adb && packages+=(adb)
        $need_iproute && packages+=(iproute2)
        $need_node && packages+=(nodejs npm)
        if [ "${#packages[@]}" -gt 0 ]; then
            sudo apt-get update
            sudo apt-get install -y "${packages[@]}"
        fi
    elif command -v pacman >/dev/null 2>&1; then
        if $need_tmux || $need_ssh || $need_sshd; then packages+=(tmux openssh); fi
        $need_tailscale && packages+=(tailscale)
        $need_python && packages+=(python)
        $need_python_modules && packages+=(python-fastapi python-pydantic python-uvicorn)
        $need_konsole && packages+=(konsole)
        $need_adb && packages+=(android-tools)
        $need_iproute && packages+=(iproute2)
        $need_node && packages+=(nodejs npm)
        [ "${#packages[@]}" -eq 0 ] || sudo pacman -S --needed --noconfirm "${packages[@]}"
    else
        printf 'Gerenciador não suportado automaticamente. Instale tmux, OpenSSH, Tailscale, Python/FastAPI/Pydantic/Uvicorn e Konsole.\n' >&2
        return 2
    fi
    if [ "${#packages[@]}" -eq 0 ]; then
        printf 'OK  todas as dependências necessárias já estavam instaladas.\n'
    else
        printf 'OK  dependências instaladas: %s\n' "${packages[*]}"
    fi
}

validate_runtime() {
    local command failures=0 python_bin
    for command in tmux ssh tailscale python3 systemctl; do
        if command -v "$command" >/dev/null 2>&1; then
            printf 'OK  %-12s %s\n' "$command" "$(command -v "$command")"
        else
            printf 'FALHA %-10s ausente\n' "$command" >&2
            failures=$((failures + 1))
        fi
    done
    if $ENABLE_TERMINAL && ! command -v konsole >/dev/null 2>&1; then
        printf 'FALHA konsole ausente; use --no-terminal ou instale o Konsole.\n' >&2
        failures=$((failures + 1))
    fi
    # The web unit deliberately uses the distro Python, so validate that exact
    # interpreter instead of a pyenv shim that systemd will never execute.
    if [ -x /usr/bin/python3 ]; then
        python_bin=/usr/bin/python3
    else
        python_bin="$(command -v python3 2>/dev/null || true)"
    fi
    if [ -n "$python_bin" ] && ! "$python_bin" -c 'import fastapi, pydantic, uvicorn' 2>/dev/null; then
        printf 'FALHA módulos Python ausentes: fastapi, pydantic e/ou uvicorn.\n' >&2
        failures=$((failures + 1))
    fi
    if command -v tailscale >/dev/null 2>&1 && ! tailscale ip -4 >/dev/null 2>&1; then
        printf 'FALHA Tailscale instalado, mas sem IPv4 autenticado. Execute: sudo tailscale up\n' >&2
        failures=$((failures + 1))
    fi
    if ! systemctl --user show-environment >/dev/null 2>&1; then
        printf 'FALHA o gerenciador systemd do usuário não está acessível nesta sessão.\n' >&2
        failures=$((failures + 1))
    fi
    [ "$failures" -eq 0 ]
}

print_plan() {
    printf '\nPlano AI Central\n'
    printf '  origem:             %s\n' "$REPO_DIR"
    printf '  destino:            %s\n' "$HOME/.local"
    printf '  Konsole no login:   %s\n' "$ENABLE_TERMINAL"
    printf '  disponibilidade:    %s\n' "$([ "$ALWAYS_ON" = true ] && printf 'antes do login' || printf 'após o login')"
    printf '  dependências auto:  %s\n' "$INSTALL_DEPS"
    printf '  Android por ADB:    %s\n' "$INSTALL_ANDROID"
    if $INSTALL_ANDROID; then
        printf '  aparelho:           %s\n' "${ANDROID_SERIAL:-detecção automática}"
        printf '  instalação móvel:   %s\n' "$([ "$ANDROID_MANUAL" = true ] && printf 'manual assistida' || printf 'direta')"
    fi
}

audit_current() {
    local unit state failures=0 linger="desconhecido"
    printf '\nInstalação atual\n'
    for unit in "${UNIT_NAMES[@]}"; do
        state="$(systemctl --user is-enabled "$unit" 2>/dev/null || true) / $(systemctl --user is-active "$unit" 2>/dev/null || true)"
        printf '  %-30s %s\n' "$unit" "$state"
    done
    if command -v loginctl >/dev/null 2>&1; then
        linger="$(loginctl show-user "$USER" -p Linger --value 2>/dev/null || true)"
    fi
    printf '  %-30s %s\n' 'linger' "${linger:-indisponível}"
    if [ -x "$BIN_DIR/claude-hub" ]; then
        "$BIN_DIR/claude-hub" doctor || failures=$((failures + 1))
    else
        printf '  AI Central ainda não instalada em %s.\n' "$BIN_DIR"
    fi
    return "$failures"
}

configure_always_on() {
    local ssh_unit=""
    command -v loginctl >/dev/null 2>&1 || { printf 'loginctl ausente; não é possível ativar linger.\n' >&2; return 1; }
    if [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null || true)" != "yes" ]; then
        loginctl enable-linger "$USER" 2>/dev/null || sudo loginctl enable-linger "$USER"
    fi
    for candidate in sshd ssh; do
        if systemctl list-unit-files "$candidate.service" --no-legend 2>/dev/null | grep -q "^$candidate.service"; then
            ssh_unit="$candidate.service"
            break
        fi
    done
    [ -n "$ssh_unit" ] || { printf 'Unidade OpenSSH Server não encontrada.\n' >&2; return 1; }
    if [ "$(systemctl is-enabled "$ssh_unit" 2>/dev/null || true)" != "enabled" ] || \
       [ "$(systemctl is-active "$ssh_unit" 2>/dev/null || true)" != "active" ]; then
        sudo systemctl enable --now "$ssh_unit"
    fi
    if [ "$(systemctl is-enabled tailscaled.service 2>/dev/null || true)" != "enabled" ] || \
       [ "$(systemctl is-active tailscaled.service 2>/dev/null || true)" != "active" ]; then
        sudo systemctl enable --now tailscaled.service
    fi
    printf 'OK  linger, %s e tailscaled disponíveis no boot.\n' "$ssh_unit"
}

TARGETS=()
for name in "${SCRIPT_NAMES[@]}"; do TARGETS+=("$BIN_DIR/$name"); done
TARGETS+=("$WEB_DIR")
TARGETS+=("$ICON_DIR/ai-central.svg")
TARGETS+=("$APPLICATIONS_DIR/ai-central-web.desktop" "$APPLICATIONS_DIR/ai-central-enable-https.desktop")
for name in "${UNIT_NAMES[@]}"; do TARGETS+=("$SYSTEMD_DIR/$name"); done

backup_current() {
    local stamp target relative enabled active
    stamp="$(date +%Y%m%d-%H%M%S)"
    BACKUP="$STATE_DIR/backups/$stamp"
    mkdir -p "$BACKUP/files"
    : > "$BACKUP/missing.txt"
    for target in "${TARGETS[@]}"; do
        relative="${target#"$HOME"/}"
        if [ -e "$target" ] || [ -L "$target" ]; then
            mkdir -p "$BACKUP/files/$(dirname "$relative")"
            cp -a "$target" "$BACKUP/files/$relative"
        else
            printf '%s\n' "$relative" >> "$BACKUP/missing.txt"
        fi
    done
    : > "$BACKUP/unit-state.tsv"
    for name in "${UNIT_NAMES[@]}"; do
        enabled="$(systemctl --user is-enabled "$name" 2>/dev/null || true)"
        active="$(systemctl --user is-active "$name" 2>/dev/null || true)"
        printf '%s\t%s\t%s\n' "$name" "${enabled:-not-found}" "${active:-inactive}" >> "$BACKUP/unit-state.tsv"
    done
    printf '%s\n' "$REPO_DIR" > "$BACKUP/source"
    MUTATION_STARTED=true
}

remove_target() {
    local target="$1"
    case "$target" in
        "$BIN_DIR"/*|"$WEB_DIR"|"$ICON_DIR/ai-central.svg"|"$APPLICATIONS_DIR"/ai-central-*.desktop|"$SYSTEMD_DIR"/ai-*.service|"$SYSTEMD_DIR/claude-hub.service")
            rm -rf -- "$target"
            ;;
        *) printf 'Rollback recusou alvo inesperado: %s\n' "$target" >&2; return 1 ;;
    esac
}

rollback() {
    local status=$? target relative saved unit enabled active
    trap - ERR
    set +e
    if $MUTATION_STARTED && ! $COMMITTED; then
        printf '\nFalha durante a instalação; restaurando %s...\n' "$BACKUP" >&2
        for target in "${TARGETS[@]}"; do
            relative="${target#"$HOME"/}"
            saved="$BACKUP/files/$relative"
            remove_target "$target"
            if [ -e "$saved" ] || [ -L "$saved" ]; then
                mkdir -p "$(dirname "$target")"
                cp -a "$saved" "$target"
            fi
        done
        systemctl --user daemon-reload >/dev/null 2>&1
        while IFS=$'\t' read -r unit enabled active; do
            case "$enabled" in enabled|enabled-runtime|linked|linked-runtime) systemctl --user enable "$unit" >/dev/null 2>&1 ;; *) systemctl --user disable "$unit" >/dev/null 2>&1 ;; esac
            if [ "$active" = "active" ]; then
                systemctl --user restart "$unit" >/dev/null 2>&1
            else
                systemctl --user stop "$unit" >/dev/null 2>&1
            fi
        done < "$BACKUP/unit-state.tsv"
        printf 'Rollback concluído; agentes no tmux não foram encerrados.\n' >&2
    fi
    [ -z "$STAGED_WEB" ] || rm -rf -- "$STAGED_WEB"
    exit "$status"
}
trap rollback ERR

install_managed_file() {
    local source="$1" destination="$2" mode="$3"
    remove_target "$destination"
    install -m "$mode" "$source" "$destination"
}

install_pc() {
    local script unit
    mkdir -p "$BIN_DIR" "$SYSTEMD_DIR" "$APPLICATIONS_DIR" "$ICON_DIR" "$STATE_DIR/backups"
    backup_current

    for script in "${SCRIPT_NAMES[@]}"; do
        if [ "$script" = "ai-hub-registry.py" ]; then
            install_managed_file "$REPO_DIR/scripts/ai_hub_registry.py" "$BIN_DIR/$script" 755
        else
            install_managed_file "$REPO_DIR/scripts/$script" "$BIN_DIR/$script" 755
        fi
    done

    STAGED_WEB="$(mktemp -d "${TMPDIR:-/tmp}/ai-central-web.XXXXXX")"
    cp -a "$REPO_DIR/ai-central-web/." "$STAGED_WEB/"
    if [ ! -f "$STAGED_WEB/node_modules/@xterm/xterm/lib/xterm.js" ]; then
        if command -v pnpm >/dev/null 2>&1; then
            pnpm --dir "$STAGED_WEB" install --prod --frozen-lockfile
        elif command -v npm >/dev/null 2>&1; then
            npm --prefix "$STAGED_WEB" install --omit=dev
        else
            printf 'pnpm ou npm é necessário para instalar os assets do terminal web.\n' >&2
            return 2
        fi
    fi
    remove_target "$WEB_DIR"
    mkdir -p "$(dirname "$WEB_DIR")"
    mv "$STAGED_WEB" "$WEB_DIR"
    STAGED_WEB=""

    install_managed_file "$REPO_DIR/ai-central-web/static/icon.svg" "$ICON_DIR/ai-central.svg" 644
    install_managed_file "$REPO_DIR/desktop/ai-central-web.desktop" "$APPLICATIONS_DIR/ai-central-web.desktop" 644
    install_managed_file "$REPO_DIR/desktop/ai-central-enable-https.desktop" "$APPLICATIONS_DIR/ai-central-enable-https.desktop" 644
    for unit in "${UNIT_NAMES[@]}"; do
        install_managed_file "$REPO_DIR/systemd/$unit" "$SYSTEMD_DIR/$unit" 644
    done

    systemctl --user daemon-reload
    systemctl --user enable --now claude-hub.service ai-hub-restore.service ai-hub-monitor.service ai-central-web.service
    if $ENABLE_TERMINAL; then
        systemctl --user enable --now ai-central-terminal.service
    else
        systemctl --user disable --now ai-central-terminal.service >/dev/null 2>&1 || true
    fi

    for _ in {1..20}; do
        if systemctl --user is-active --quiet ai-central-web.service && \
           systemctl --user is-active --quiet ai-hub-monitor.service; then
            break
        fi
        sleep 1
    done
    systemctl --user is-active --quiet claude-hub.service
    systemctl --user is-active --quiet ai-central-web.service
    systemctl --user is-active --quiet ai-hub-monitor.service
    "$BIN_DIR/claude-hub" doctor

    COMMITTED=true
    printf '\nAI Central instalada e validada.\n'
    printf '  Backup anterior: %s\n' "$BACKUP"
    printf '  Estado:          ch status\n'
    printf '  Diagnóstico:     ch doctor\n'
    printf '  Sessão bilateral: ch open NOME\n'
    printf '  Interface web:   ch web\n'
    if $ENABLE_TERMINAL; then
        printf '  Konsole:         abre automaticamente no login gráfico\n'
    fi
}

install_android() {
    local args=() status
    [ -z "$ANDROID_SERIAL" ] || args+=(--serial "$ANDROID_SERIAL")
    [ -z "$ANDROID_HOST" ] || args+=(--host "$ANDROID_HOST")
    args+=(--user "$ANDROID_USER")
    $ALWAYS_ON && args+=(--require-boot)
    $ANDROID_MANUAL && args+=(--manual)
    $ANDROID_LAUNCH || args+=(--no-launch)
    set +e
    "$REPO_DIR/install-ai-central-android.sh" "${args[@]}"
    status=$?
    set -e
    if [ "$status" -ne 0 ]; then
        printf 'A parte PC permanece instalada, mas a etapa Android falhou (código %s).\n' "$status" >&2
        return "$status"
    fi
}

validate_sources
print_plan
if $DRY_RUN; then
    printf '\nDry-run concluído: nenhuma alteração realizada.\n'
    exit 0
fi
if $INSTALL_DEPS; then
    install_dependencies
fi
validate_runtime
if $CHECK_ONLY; then
    audit_current
    if $INSTALL_ANDROID; then
        android_args=(--check --user "$ANDROID_USER")
        $ALWAYS_ON && android_args+=(--require-boot)
        [ -z "$ANDROID_SERIAL" ] || android_args+=(--serial "$ANDROID_SERIAL")
        [ -z "$ANDROID_HOST" ] || android_args+=(--host "$ANDROID_HOST")
        "$REPO_DIR/install-ai-central-android.sh" "${android_args[@]}"
    fi
    printf '\nAuditoria concluída sem alterações.\n'
    exit 0
fi
if $ALWAYS_ON; then
    configure_always_on
fi
install_pc
if $INSTALL_ANDROID; then
    install_android
fi
