# AI Central

AI Central é a superfície única para acompanhar e controlar Claude Code, Codex e
shells no PC e no celular. O tmux no PC é a fonte da verdade: Konsole, Termux e a
PWA são clientes do mesmo processo, não cópias da conversa.

## O que ela garante

- Entrada e saída ao vivo nas duas telas.
- Criação e retomada de Claude Code e Codex com controle pleno.
- Várias sessões organizadas por nome e repositório.
- Proteção contra dois agentes escritores no mesmo worktree.
- Worktrees isolados quando o paralelismo no mesmo repositório é desejado.
- Restauração por ID após reiniciar o PC, sem duplicar um agente ainda vivo.
- Estados `TRABALHANDO`, `WORKFLOW ATIVO`, `PRECISA DE VOCÊ`, `FINALIZADO`,
  `PARADO` e `ENCERRADO`.
- Métricas de sessão, semana, erros e tokens do Usage Buddies.
- Notificações no desktop e, usando HTTPS privado, no celular.
- Reconexão móvel rápida, com mensagem offline explícita e despertar do
  Tailscale após falhas repetidas.

## Arquitetura

```text
Claude Code / Codex / zsh
          │
     tmux claude-hub              estado e métricas locais
       ├── Konsole no PC   ────── ai-hub-state.py
       ├── SSH + Termux            ├── Usage Buddies
       └── PWA + WebSocket         └── notificações
                │
         Tailscale privado
```

Uma TUI possui uma única grade de caracteres. A central usa `window-size latest`:
o Claude reflui para a tela usada mais recentemente. Ao operar pelo celular, a
grade fica estreita; ao voltar ao Konsole, ela expande. Isso evita tanto o corte
no celular quanto a tela pequena cercada de pontos no PC. Duas geometrias
independentes simultâneas não são possíveis para o mesmo processo TUI.

## Requisitos do PC

- Linux com systemd de usuário.
- `tmux`, `openssh`, `tailscale` e Python 3.
- Claude Code e/ou Codex CLI.
- `fastapi`, `pydantic` e `uvicorn` para a PWA.
- Konsole e PySide6 são opcionais; o terminal e a PWA continuam funcionando sem
  a central gráfica Qt.

O PC e o celular devem estar na mesma tailnet. Não exponha a porta da PWA na
internet e não ative Tailscale Funnel.

## Instalar no PC

```bash
cd ~/claude-usage-widget
./install-ai-central.sh
```

O instalador copia comandos para `~/.local/bin`, a PWA para
`~/.local/share/ai-central-web`, atalhos de desktop e unidades systemd portáveis.
Ele habilita o hub, a restauração, o monitor e a PWA. Abrir automaticamente um
Konsole no login é opcional:

```bash
systemctl --user enable --now ai-central-terminal.service
```

Diagnóstico não destrutivo:

```bash
claude-hub doctor
claude-hub status
systemctl --user status claude-hub ai-hub-restore ai-hub-monitor ai-central-web
```

## Instalar no celular com ADB

Instale Termux e Termux:Widget pela mesma origem, instale `openssh` no Termux e
cadastre a chave pública do celular em `~/.ssh/authorized_keys` no PC. Descubra o
IPv4 Tailscale do PC:

```bash
tailscale ip -4
```

Com o aparelho autorizado no ADB, no PC:

```bash
adb shell mkdir -p /sdcard/Download/ai-central-mobile
adb push mobile/. /sdcard/Download/ai-central-mobile/
```

No Termux, substitua o IP e o usuário:

```bash
bash /sdcard/Download/ai-central-mobile/install-termux.sh 100.64.0.1 meu-usuario
```

O instalador móvel:

- mantém o SSH da central isolado em `~/.config/ai-central/ssh-config`;
- não sobrescreve `~/.ssh/config`;
- guarda versões anteriores em `~/.config/ai-central/backups/`;
- instala `PC-Hub` e `PC-Shell` em `~/.shortcuts/`;
- instala a barra móvel com `TECLA`, `MENU`, `+SH`, `ANT`, `PROX`, `OK`, `TELA`
  e `SAIR`.

Atualize o widget do Termux ou remova e adicione-o novamente à tela inicial caso
os atalhos não apareçam de imediato.

## Fluxo diário

### No PC

```bash
ch status
ch gui
ch open amaral-hub
ch here
```

### Dentro de qualquer cliente tmux

| Ação | Atalho |
|---|---|
| Menu central | `Ctrl-b w` ou `MENU` |
| Nova shell | `Ctrl-b c` ou `+SH` |
| Sessão anterior/próxima | `ANT` / `PROX` |
| Zoom do pane | `Ctrl-b z` ou `TELA` |
| Desanexar sem parar nada | `Ctrl-b d` ou `SAIR` |
| Abrir teclado Android | `TECLA` |

No menu, use as setas e Enter ou as teclas mostradas à direita. Os números abrem
diretamente as janelas; `a` e `x` criam Claude/Codex; `r` e `e` retomam; `t` cria
worktree; `s` abre o estado geral.

### Criar e retomar

```bash
ch start-claude auditoria /var/www/projeto
ch resume-claude auditoria /var/www/projeto SESSION_ID
ch start-codex api /var/www/projeto
ch resume-codex api /var/www/projeto SESSION_ID
```

Os comandos de Claude usam `--permission-mode bypassPermissions`; os de Codex
usam `--dangerously-bypass-approvals-and-sandbox`. Isso concede controle amplo ao
agente. Use somente em máquinas e repositórios em que esse risco é aceitável.

### Várias sessões no mesmo repositório

Duas sessões de leitura podem coexistir, mas dois agentes escrevendo no mesmo
worktree criam corridas em arquivos, índice Git e hooks. A central recusa essa
duplicação. Para paralelismo seguro:

```bash
ch worktree-claude auditor-b /var/www/projeto ai/auditor-b
ch worktree-codex revisor-c /var/www/projeto ai/revisor-c
```

Cada agente recebe pasta e branch próprias em `~/wt/<nome>`.

## Retomar no PC versus continuar no celular

O sincronismo ao vivo existe quando as duas telas estão anexadas ao mesmo pane do
tmux. `claude --resume ID` em outro terminal inicia outro processo sobre o mesmo
histórico; ele não espelha ao vivo o processo já aberto e pode divergir. Para
continuar a sessão realmente viva, use `ch open <nome>` ou `ch here`.

Após reiniciar o PC, `ai-hub-restore.service` usa o registro em
`~/.config/ai-central/sessions.json` para recriar panes e executar `--resume`. Ele
não inicia uma cópia quando encontra um Claude/Codex vivo no mesmo diretório.

## PWA e notificações no celular

Obtenha o endereço autenticado:

```bash
ch web
```

Para recursos que exigem contexto seguro do navegador, ative HTTPS privado uma
vez pelo atalho “AI Central · Ativar HTTPS privado” ou:

```bash
~/.local/bin/ai-central-enable-https.sh
```

O script configura somente Tailscale Serve; Funnel público permanece desligado.
O token de acesso fica em `~/.config/ai-central/web-token` com permissão restrita
e é armazenado localmente no navegador depois do primeiro pareamento.

## Solução de problemas

### Tela do PC pequena e cercada de pontos

Ative o Konsole e pressione uma tecla que não altere o comando, como `Ctrl-b` e
depois `Esc`, ou selecione a janela pelo menu. Confirme:

```bash
tmux show-options -g window-size   # deve responder: latest
```

### Texto cortado no celular

Toque no terminal ou troque de janela pelo menu. A grade deve refluír para a
tela móvel. Use `TELA` para zoom e diminua a fonte no gesto de pinça do Termux se
quiser mais colunas.

### Menu ou setas parecem travados

Leia o cabeçalho. Se aparecer `AI CENTRAL · OFFLINE`, o menu antigo já não está
ativo e o atalho está reconectando. Se a tela ficou muda por mais de 15 segundos,
abra o Tailscale e confirme que o PC está online. O SSH gerenciado usa keepalive
de 5 segundos e encerra após duas respostas perdidas.

### Código 255 / broken pipe

É falha de transporte SSH, não perda da sessão Claude. O tmux continua no PC e o
atalho reconecta. Rode `ch doctor` no PC e verifique no celular:

```bash
ssh -F ~/.config/ai-central/ssh-config -vv pc-hub
```

### Teclado não abre

Toque `TECLA` no Termux. Na PWA, use o botão de teclado no cabeçalho do terminal
ou no dock inferior. Em Android, tocar uma vez dentro do terminal antes do botão
pode ser necessário após sair da tela cheia.

### Carga alta no PC

A central não encerra workflows para se manter responsiva. Confira primeiro
`ch status` e os processos do repositório. Testes paralelos, subagentes e builds
podem saturar CPU e atrasar captura de tela/ADB sem significar perda do SSH.

## Remover

```bash
./uninstall-ai-central.sh
```

Por segurança, a remoção preserva o tmux vivo e
`~/.config/ai-central/sessions.json`. O script imprime comandos separados caso
você também queira encerrar as sessões ou apagar o registro.
