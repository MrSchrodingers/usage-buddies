#!/bin/bash
set -euo pipefail

# ═══════════════════════════════════════════════════
# Usage Buddies - Universal Linux Installer
# Supports: KDE Plasma 6 (plasmoid) + any DE (tray app)
# ═══════════════════════════════════════════════════

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
COLLECTOR="$HOME/.local/bin/usage-buddies-collector.py"
SYSTEMD_DIR="$HOME/.config/systemd/user"
TAURI_DIR="$REPO_DIR/tauri-app"
BUILD_LOG="$REPO_DIR/tauri-build.log"

RED='\033[0;31m'
GREEN='\033[0;32m'
AMBER='\033[0;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ── Tracking for final report ──────────────────────
declare -a STEPS_OK=()
declare -a STEPS_WARN=()
declare -a STEPS_FAIL=()

ok() {
    local msg="$1"
    echo -e "  ${GREEN}✓${NC} $msg"
    STEPS_OK+=("$msg")
}

warn() {
    local msg="$1"
    local hint="${2:-}"
    echo -e "  ${AMBER}⚠${NC} $msg"
    [[ -n "$hint" ]] && echo -e "    ${DIM}→ $hint${NC}"
    STEPS_WARN+=("$msg${hint:+ — $hint}")
}

fail() {
    local msg="$1"
    local hint="${2:-}"
    echo -e "  ${RED}✗${NC} $msg"
    [[ -n "$hint" ]] && echo -e "    ${DIM}→ $hint${NC}"
    STEPS_FAIL+=("$msg${hint:+ — $hint}")
    print_final_report
    exit 1
}

step_desc() {
    echo -e "  ${DIM}$1${NC}"
}

header() {
    echo ""
    echo -e "${BOLD}═══════════════════════════════════════════${NC}"
    echo -e "${BOLD}  Usage Buddies - Linux Installer   ${NC}"
    echo -e "${BOLD}═══════════════════════════════════════════${NC}"
    echo ""
}

# Detect an install made under the old project name (usage-buddies-*) and offer
# to clear it. Leaving it in place means two collectors on two systemd timers
# writing the same ~/.claude/widget-data.json, and a stale plasmoid in the panel.
migrate_legacy_install() {
    local found=()
    [ -f "$HOME/.local/bin/usage-buddies-collector.py" ] && found+=("~/.local/bin/usage-buddies-collector.py")
    [ -f "$HOME/.local/bin/usage-buddies-tray" ] && found+=("~/.local/bin/usage-buddies-tray")
    [ -f "$HOME/.config/systemd/user/usage-buddies-collector.timer" ] && found+=("systemd timer usage-buddies-collector.timer")
    [ -d "$HOME/.local/share/plasma/plasmoids/org.kde.plasma.usagebuddies" ] && found+=("plasmoid org.kde.plasma.usagebuddies")
    [ -f "$HOME/.config/autostart/usage-buddies-tray.desktop" ] && found+=("autostart usage-buddies-tray.desktop")

    [ ${#found[@]} -eq 0 ] && return 0

    echo ""
    echo -e "${AMBER}Previous install found under the old name:${NC}"
    for f in "${found[@]}"; do echo -e "  ${DIM}- $f${NC}"; done
    echo ""
    echo -e "  This project was renamed ${BOLD}usage-buddies${NC} -> ${BOLD}usage-buddies${NC}."
    echo -e "  Keeping both means two collectors on two timers writing the same"
    echo -e "  ~/.claude/widget-data.json. Your data files are not touched either way."
    echo ""

    if [ ! -t 0 ]; then
        warn "Old install left in place (non-interactive shell)" \
             "Run: bash \"$REPO_DIR/legacy/uninstall.sh\""
        return 0
    fi

    read -r -p "  Remove the old install now? [Y/n] " reply
    case "$reply" in
        [Nn]*)
            warn "Old install left in place" \
                 "Run later: bash \"$REPO_DIR/legacy/uninstall.sh\""
            ;;
        *)
            if [ -x "$REPO_DIR/legacy/uninstall.sh" ]; then
                bash "$REPO_DIR/legacy/uninstall.sh"
                ok "Old install removed"
            else
                warn "legacy/uninstall.sh not found" "Remove the paths above by hand"
            fi
            ;;
    esac
}

# Choose Arch package manager: prefer AUR helper if user installed one,
# fall back to sudo pacman. Side effect: echoes the command to stdout.
arch_install_cmd() {
    if [[ -n "$AUR_HELPER" ]]; then
        echo "$AUR_HELPER -S --noconfirm"
    else
        echo "sudo pacman -S --noconfirm"
    fi
}

detect_env() {
    HAS_KDE=false
    HAS_GNOME=false
    HAS_RUST=false
    HAS_NODE=false
    HAS_PYTHON=false
    HAS_SYSTEMD=false
    DISTRO="unknown"
    DE_NAME="unknown"
    AUR_HELPER=""

    command -v python3 &>/dev/null && HAS_PYTHON=true
    command -v plasmashell &>/dev/null && HAS_KDE=true
    command -v gnome-shell &>/dev/null && HAS_GNOME=true
    command -v cargo &>/dev/null && command -v rustc &>/dev/null && HAS_RUST=true
    command -v node &>/dev/null && command -v npm &>/dev/null && HAS_NODE=true
    systemctl --user status &>/dev/null 2>&1 && HAS_SYSTEMD=true

    case "${XDG_CURRENT_DESKTOP:-}" in
        *KDE*)         DE_NAME="kde" ;;
        *GNOME*)       DE_NAME="gnome" ;;
        *MATE*)        DE_NAME="mate" ;;
        *XFCE*)        DE_NAME="xfce" ;;
        *Cinnamon*)    DE_NAME="cinnamon" ;;
        *Hyprland*)    DE_NAME="hyprland" ;;
        *sway*|*Sway*) DE_NAME="sway" ;;
        *)             DE_NAME="${XDG_CURRENT_DESKTOP:-unknown}" ;;
    esac

    if [ -f /etc/os-release ]; then
        . /etc/os-release
        if [[ "$ID" == "fedora" ]] || [[ "${ID_LIKE:-}" == *"fedora"* ]]; then
            DISTRO="fedora"
        elif [[ "$ID" == "ubuntu" ]] || [[ "$ID" == "debian" ]] || [[ "${ID_LIKE:-}" == *"ubuntu"* ]] || [[ "${ID_LIKE:-}" == *"debian"* ]]; then
            DISTRO="debian"
        elif [[ "$ID" == "arch" ]] || [[ "${ID_LIKE:-}" == *"arch"* ]]; then
            DISTRO="arch"
        elif [[ "$ID" == *"opensuse"* ]] || [[ "${ID_LIKE:-}" == *"suse"* ]]; then
            DISTRO="opensuse"
        fi
    fi

    # Arch users often prefer AUR helpers — respect their tooling
    if [[ "$DISTRO" == "arch" ]]; then
        if command -v paru &>/dev/null; then
            AUR_HELPER="paru"
        elif command -v yay &>/dev/null; then
            AUR_HELPER="yay"
        fi
    fi
}

install_deps() {
    echo -e "${AMBER}[1/7]${NC} Checking dependencies..."

    step_desc "Checking Python 3 (required for the collector)..."
    if ! $HAS_PYTHON; then
        step_desc "Python 3 not found — installing..."
        case $DISTRO in
            fedora)   sudo dnf install -y python3 || fail "Python 3 install failed (dnf)" "Check network and repos" ;;
            debian)   sudo apt-get install -y python3 || fail "Python 3 install failed (apt)" "Try: sudo apt update && sudo apt install python3" ;;
            arch)     $(arch_install_cmd) python || fail "Python 3 install failed (${AUR_HELPER:-pacman})" "" ;;
            opensuse) sudo zypper install -y python3 || fail "Python 3 install failed (zypper)" "" ;;
            *)        fail "Unknown distro ($DISTRO)" "Install Python 3 manually: https://python.org" ;;
        esac
        HAS_PYTHON=true
    fi
    ok "Python $(python3 --version 2>/dev/null | grep -oP '[\d.]+') detected"

    step_desc "Checking cryptography module (Chrome cookie decryption)..."
    if python3 -c "import cryptography" 2>/dev/null; then
        ok "cryptography module available"
    elif pip3 install --user --quiet cryptography 2>/dev/null \
        || python3 -m pip install --user --quiet cryptography 2>/dev/null; then
        ok "cryptography installed"
    else
        warn "cryptography install failed" "Chrome cookie decryption disabled — Firefox fallback still works"
    fi

    if $HAS_KDE; then
        step_desc "Checking kwallet-query (KDE Chrome cookie decryption)..."
        if command -v kwallet-query &>/dev/null; then
            ok "kwallet-query available"
        else
            local installed=false
            case $DISTRO in
                fedora)   sudo dnf install -y kwalletmanager 2>/dev/null && installed=true ;;
                debian)   sudo apt-get install -y kwalletmanager 2>/dev/null && installed=true ;;
                opensuse) sudo zypper install -y kwalletmanager 2>/dev/null && installed=true ;;
                arch)     $(arch_install_cmd) kwallet 2>/dev/null && installed=true ;;
            esac
            if $installed; then
                ok "kwallet installed"
            else
                warn "kwallet install failed" "Chrome cookies may not decrypt — Firefox fallback still works"
            fi
        fi
    else
        step_desc "Checking secret-tool (GNOME Keyring Chrome cookie decryption)..."
        if command -v secret-tool &>/dev/null; then
            ok "secret-tool available"
        else
            local installed=false
            case $DISTRO in
                fedora)   sudo dnf install -y libsecret 2>/dev/null && installed=true ;;
                debian)   sudo apt-get install -y libsecret-tools 2>/dev/null && installed=true ;;
                opensuse) sudo zypper install -y libsecret-tools 2>/dev/null && installed=true ;;
                arch)     $(arch_install_cmd) libsecret 2>/dev/null && installed=true ;;
            esac
            if $installed; then
                ok "libsecret installed"
            else
                warn "libsecret install failed" "Chrome cookies may not decrypt — Firefox fallback still works"
            fi
        fi
    fi
}

install_collector() {
    echo ""
    echo -e "${AMBER}[2/7]${NC} Installing data collector..."
    step_desc "Copying usage-buddies-collector.py to ~/.local/bin/"
    mkdir -p "$HOME/.local/bin"
    if cp "$REPO_DIR/scripts/usage-buddies-collector.py" "$COLLECTOR" && chmod +x "$COLLECTOR"; then
        ok "Collector installed: $COLLECTOR"
    else
        fail "Failed to copy collector to $COLLECTOR" "Check write permissions on ~/.local/bin/"
    fi
}

install_timer() {
    echo ""
    echo -e "${AMBER}[3/7]${NC} Setting up auto-refresh..."

    if ! $HAS_SYSTEMD; then
        warn "systemd user session unavailable (WSL/container?)" "Add cron entry: * * * * * python3 $COLLECTOR"
        return
    fi

    step_desc "Installing systemd user timer (refresh every 30s)..."
    mkdir -p "$SYSTEMD_DIR"
    cp "$REPO_DIR/scripts/usage-buddies-collector.service" "$SYSTEMD_DIR/"
    cp "$REPO_DIR/scripts/usage-buddies-collector.timer" "$SYSTEMD_DIR/"

    local PYTHON_BIN
    PYTHON_BIN=$(command -v python3 || command -v python || echo "/usr/bin/python3")
    sed -i "s|/usr/bin/python3|$PYTHON_BIN|g" "$SYSTEMD_DIR/usage-buddies-collector.service"

    if systemctl --user daemon-reload && systemctl --user enable --now usage-buddies-collector.timer; then
        ok "systemd timer enabled (refreshes every 30s)"
    else
        warn "systemd timer failed to enable" "Run: systemctl --user status usage-buddies-collector.timer"
    fi
}

install_plasmoid() {
    local PLASMOID_DIR="$HOME/.local/share/plasma/plasmoids/org.kde.plasma.usagebuddies"

    echo ""
    echo -e "${AMBER}[4/7]${NC} Installing KDE Plasmoid..."

    local PLASMA_VER
    PLASMA_VER=$(plasmashell --version 2>/dev/null | grep -oP '\d+' | head -1 || true)
    PLASMA_VER=${PLASMA_VER:-0}
    if [ "$PLASMA_VER" -lt 6 ] 2>/dev/null; then
        warn "Plasma 6+ required (found Plasma $PLASMA_VER)" "Plasmoid skipped; tray app will be used instead"
        return
    fi

    step_desc "Copying plasmoid files to ~/.local/share/plasma/..."
    rm -rf "$PLASMOID_DIR"
    mkdir -p "$PLASMOID_DIR/contents/"{ui,icons,config}
    cp "$REPO_DIR/plasmoid/metadata.json" "$PLASMOID_DIR/"
    cp "$REPO_DIR/plasmoid/contents/ui/main.qml" "$PLASMOID_DIR/contents/ui/"
    cp "$REPO_DIR/plasmoid/contents/config/"* "$PLASMOID_DIR/contents/config/"
    if compgen -G "$REPO_DIR/plasmoid/contents/icons/*" > /dev/null 2>&1; then
        cp "$REPO_DIR/plasmoid/contents/icons/"* "$PLASMOID_DIR/contents/icons/"
    fi
    mkdir -p "$HOME/.local/share/icons/hicolor/48x48/apps/"
    if [ -f "$REPO_DIR/plasmoid/contents/icons/claude-logo.png" ]; then
        cp "$REPO_DIR/plasmoid/contents/icons/claude-logo.png" "$HOME/.local/share/icons/hicolor/48x48/apps/claude-logo.png"
    fi

    ok "Plasmoid installed — right-click panel → Add Widgets → 'Usage Buddies'"
}

install_tauri() {
    echo ""
    echo -e "${AMBER}[5/7]${NC} Building tray app..."

    if [ ! -d "$TAURI_DIR" ]; then
        warn "tauri-app directory not found" "Skipping tray app build"
        return
    fi

    if ! $HAS_RUST; then
        step_desc "Rust not found — installing via rustup..."
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --quiet 2>/dev/null || true
        # shellcheck disable=SC1091
        source "$HOME/.cargo/env" 2>/dev/null || true
        if command -v cargo &>/dev/null; then
            ok "Rust installed via rustup"
            HAS_RUST=true
        else
            warn "Rust install failed" "Install manually: https://rustup.rs — then re-run ./install.sh"
            return
        fi
    fi

    if ! $HAS_NODE; then
        local hint=""
        case $DISTRO in
            fedora)   hint="sudo dnf install nodejs npm" ;;
            debian)   hint="sudo apt install nodejs npm" ;;
            arch)     hint="${AUR_HELPER:-sudo pacman} -S nodejs npm" ;;
            opensuse) hint="sudo zypper install nodejs npm" ;;
            *)        hint="Install Node.js from https://nodejs.org" ;;
        esac
        warn "Node.js + npm required for tray app" "$hint"
        return
    fi

    step_desc "Installing Tauri system dependencies (webkit2gtk, gtk3, libappindicator)..."
    local deps_ok=true
    case $DISTRO in
        fedora)
            sudo dnf install -y webkit2gtk4.1-devel gtk3-devel libappindicator-gtk3-devel \
                librsvg2-devel pango-devel 2>/dev/null || deps_ok=false ;;
        debian)
            sudo apt-get install -y libwebkit2gtk-4.1-dev libgtk-3-dev libayatana-appindicator3-dev \
                librsvg2-dev libpango1.0-dev 2>/dev/null || deps_ok=false ;;
        opensuse)
            sudo zypper install -y webkit2gtk3-soup2-devel gtk3-devel libappindicator3-devel \
                librsvg-devel pango-devel 2>/dev/null || deps_ok=false ;;
        arch)
            $(arch_install_cmd) webkit2gtk-4.1 gtk3 libappindicator-gtk3 \
                librsvg pango 2>/dev/null || deps_ok=false ;;
    esac
    if $deps_ok; then
        ok "Tauri system dependencies installed"
    else
        warn "Some Tauri system dependencies failed to install" "Build may fail — see $BUILD_LOG"
    fi

    cd "$TAURI_DIR"
    step_desc "Installing npm dependencies..."
    if npm install --silent 2>&1 | tee -a "$BUILD_LOG" > /dev/null; then
        ok "npm dependencies installed"
    else
        warn "npm install had warnings" "Continuing — see $BUILD_LOG"
    fi

    step_desc "Compiling Tauri app (this takes 2–5 minutes)..."
    npx tauri build 2>&1 | tee -a "$BUILD_LOG" > /dev/null || true

    local BIN="$TAURI_DIR/src-tauri/target/release/usage-buddies-tray"
    if [ -f "$BIN" ]; then
        if cp "$BIN" "$HOME/.local/bin/usage-buddies-tray" && chmod +x "$HOME/.local/bin/usage-buddies-tray"; then
            ok "Tray app built and installed: ~/.local/bin/usage-buddies-tray"
        else
            fail "Tray binary copy failed" "Check write permissions on ~/.local/bin/"
        fi

        if $HAS_GNOME && ! $HAS_KDE; then
            echo ""
            if [ -x "$REPO_DIR/scripts/gnome-setup.sh" ]; then
                "$REPO_DIR/scripts/gnome-setup.sh" \
                    && ok "GNOME AppIndicator setup completed" \
                    || warn "GNOME AppIndicator setup incomplete" "Use Super+Shift+C as fallback, or install the extension manually"
            else
                warn "scripts/gnome-setup.sh missing or not executable" "Tray icon may be invisible on GNOME — use Super+Shift+C"
            fi
        fi

        case "$DE_NAME" in
            mate|xfce|cinnamon)
                echo -e "  ${DIM}  $DE_NAME detected — tray works natively via StatusNotifierItem${NC}" ;;
            hyprland|sway)
                echo -e "  ${DIM}  $DE_NAME — ensure your bar (waybar/eww) has a tray module enabled${NC}" ;;
        esac
    else
        warn "Tauri build did not produce a binary" "See $BUILD_LOG; plasmoid (if installed) still works"
    fi

    cd "$REPO_DIR"
}

setup_auth() {
    echo ""
    echo -e "${AMBER}[6/7]${NC} Testing data collection..."

    step_desc "Running --health-check to validate browser authentication..."
    local hc_exit=0
    python3 "$COLLECTOR" --health-check || hc_exit=$?

    if [ $hc_exit -eq 0 ]; then
        ok "Browser authentication OK — live data available"
    else
        warn "Browser authentication failed" "Widget will run in Offline mode (local estimates only); follow advice above and re-run: usage-buddies-collector.py --health-check"
    fi

    step_desc "Generating initial widget-data.json..."
    if python3 "$COLLECTOR" 2>/dev/null; then
        ok "Initial data generated"
    else
        warn "Initial data generation returned a non-zero status" "Check: python3 $COLLECTOR --verbose"
    fi
}

run_sanity_checks() {
    echo ""
    echo -e "${AMBER}[7/7]${NC} Sanity checks..."

    step_desc "Checking collector binary..."
    if [ -x "$COLLECTOR" ]; then
        ok "Collector present and executable"
    else
        fail "Collector missing or not executable: $COLLECTOR" "Re-run ./install.sh"
    fi

    if [ -f "$HOME/.local/bin/usage-buddies-tray" ]; then
        step_desc "Checking tray app binary..."
        if [ -x "$HOME/.local/bin/usage-buddies-tray" ]; then
            ok "Tray app present and executable"
        else
            warn "Tray binary exists but is not executable" "Run: chmod +x ~/.local/bin/usage-buddies-tray"
        fi
    fi

    if $HAS_SYSTEMD; then
        step_desc "Checking systemd timer status..."
        if systemctl --user is-active --quiet usage-buddies-collector.timer 2>/dev/null; then
            ok "systemd timer is active"
        else
            warn "systemd timer is not active" "Run: systemctl --user enable --now usage-buddies-collector.timer"
        fi
    fi

    step_desc "Checking ~/.claude/ write permission..."
    mkdir -p "$HOME/.claude"
    local test_file="$HOME/.claude/.install-test-$$"
    if touch "$test_file" 2>/dev/null && rm -f "$test_file"; then
        ok "~/.claude/ is writable"
    else
        fail "~/.claude/ is not writable" "Run: sudo chown -R \$USER:\$USER ~/.claude"
    fi
}

print_final_report() {
    echo ""
    echo -e "${BOLD}═══════════════════════════════════════════${NC}"
    echo -e "${BOLD}  Installation Report                      ${NC}"
    echo -e "${BOLD}═══════════════════════════════════════════${NC}"
    echo ""

    if [ ${#STEPS_OK[@]} -gt 0 ]; then
        echo -e "${GREEN}  Successful (${#STEPS_OK[@]}):${NC}"
        for s in "${STEPS_OK[@]}"; do
            echo -e "    ${GREEN}✓${NC} $s"
        done
        echo ""
    fi

    if [ ${#STEPS_WARN[@]} -gt 0 ]; then
        echo -e "${AMBER}  Warnings (${#STEPS_WARN[@]}) — non-critical, install continued:${NC}"
        for s in "${STEPS_WARN[@]}"; do
            echo -e "    ${AMBER}⚠${NC} $s"
        done
        echo ""
    fi

    if [ ${#STEPS_FAIL[@]} -gt 0 ]; then
        echo -e "${RED}  Failures (${#STEPS_FAIL[@]}) — install aborted:${NC}"
        for s in "${STEPS_FAIL[@]}"; do
            echo -e "    ${RED}✗${NC} $s"
        done
        echo ""
    fi
}

finish() {
    echo ""
    echo -e "${BOLD}═══════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Installation Complete!${NC}"
    echo -e "${BOLD}═══════════════════════════════════════════${NC}"
    echo ""

    if $HAS_KDE; then
        echo -e "  ${BOLD}KDE Plasmoid:${NC}"
        echo "    Right-click panel → Add Widgets → 'Usage Buddies'"
        echo ""
    fi

    if [ -f "$HOME/.local/bin/usage-buddies-tray" ]; then
        echo -e "  ${BOLD}Tray App:${NC}"
        echo "    Run: usage-buddies-tray"
        echo "    Or:  Super+Shift+C to toggle"
        if $HAS_GNOME; then
            echo -e "    ${AMBER}Note:${NC} GNOME needs AppIndicator extension (installed above)."
            echo -e "    ${DIM}    If tray icon is invisible, log out and back in.${NC}"
        fi
        echo ""

        mkdir -p "$HOME/.config/autostart"
        cat > "$HOME/.config/autostart/usage-buddies-tray.desktop" << DESKTOP
[Desktop Entry]
Type=Application
Name=Usage Buddies
Exec=$HOME/.local/bin/usage-buddies-tray
Icon=claude-logo
StartupNotify=false
Terminal=false
X-GNOME-Autostart-enabled=true
DESKTOP
        ok "Autostart entry created"
    fi

    echo "  Data refreshes every 30 seconds from claude.ai."
    echo "  Reads browser cookies automatically — no API keys needed."
    echo ""
}

# ── Main ────────────────────────────────────────────
header
detect_env

echo -e "  ${BLUE}Detected:${NC} $DISTRO | DE=$DE_NAME | KDE=$HAS_KDE | GNOME=$HAS_GNOME | Rust=$HAS_RUST | Node=$HAS_NODE | systemd=$HAS_SYSTEMD${AUR_HELPER:+ | AUR=$AUR_HELPER}"
echo ""

migrate_legacy_install
install_deps
install_collector
install_timer

if $HAS_KDE; then
    install_plasmoid
else
    echo ""
    echo -e "${AMBER}[4/7]${NC} Skipping plasmoid (KDE not detected)"
fi

if ! $HAS_KDE || ($HAS_RUST && $HAS_NODE); then
    install_tauri
else
    echo ""
    echo -e "${AMBER}[5/7]${NC} Skipping tray app (KDE detected — use plasmoid)"
    echo -e "  ${DIM}  To also build the tray app: install Rust + Node.js and re-run${NC}"
fi

setup_auth
run_sanity_checks
finish
print_final_report
