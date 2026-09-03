#!/usr/bin/env bash
set -euo pipefail

printf '\033[1;36mAI Central · ativar HTTPS privado\033[0m\n\n'
printf 'O sudo é usado uma única vez para tornar %s operador do Tailscale.\n' "$USER"
printf 'Funnel público NÃO será habilitado.\n\n'
sudo tailscale set --operator="$USER"
tailscale serve --bg --yes "http://$(tailscale ip -4):8765"
printf '\n\033[1;32mHTTPS ativado.\033[0m\n'
"$HOME/.local/bin/ai-central-web.py" --print-url
printf '\nPressione Enter para fechar...'
read -r
