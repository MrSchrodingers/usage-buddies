# AI Central

AI Central é a superfície única para acompanhar e controlar Claude Code, Codex e
shells no PC e no celular. O tmux no PC é a fonte da verdade: Konsole, Termux e a
PWA são clientes do mesmo processo, não cópias da conversa.

## Início rápido

| Objetivo | Comando no PC |
|---|---|
| Auditar sem alterar nada | `./install-ai-central.sh --check` |
| Instalar para o login atual e futuros | `./install-ai-central.sh` |
| Instalar dependências e subir antes do login | `./install-ai-central.sh --auto` |
| PC + Android conectado por ADB | `./install-ai-central.sh --auto --android` |
| Apenas instalar/atualizar o Android | `./install-ai-central-android.sh` |
| Transferir ao Android e concluir manualmente | `./install-ai-central-android.sh --manual` |

Antes da primeira execução, use `--dry-run` com as mesmas opções. Ele valida as
fontes e mostra todos os destinos sem escrever no PC ou no aparelho.

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

## Instalação no PC

### 1. Clonar e auditar

```bash
git clone https://github.com/MrSchrodingers/usage-buddies.git
cd usage-buddies
./install-ai-central.sh --dry-run --auto
./install-ai-central.sh --check
```

`--check` exige que as dependências já existam; `--dry-run` serve para revisar o
plano mesmo antes de instalá-las.

### 2. Escolher o modo

Instalação padrão:

```bash
./install-ai-central.sh
```

Ela não instala pacotes nem modifica serviços de sistema. Habilita o hub, a
restauração, o monitor, a PWA e, por padrão, uma única janela Konsole anexada ao
tmux no login gráfico. Para não abrir a janela automaticamente:

```bash
./install-ai-central.sh --no-terminal
```

Instalação automática para uma máquina dedicada/remota:

```bash
./install-ai-central.sh --auto
```

`--auto` instala pacotes conhecidos em Fedora, Debian/Ubuntu ou Arch, habilita
OpenSSH e Tailscale no boot e ativa o `linger` do usuário. Com isso, os serviços
de usuário e o tmux restaurado sobem mesmo sem login gráfico. O instalador pode
pedir `sudo` exclusivamente para pacotes, serviços de sistema e `linger`; a
central em si continua instalada no diretório do usuário.

Tailscale ainda precisa de autenticação humana uma vez (`sudo tailscale up`). O
instalador aborta se não houver IPv4 da tailnet, em vez de expor a interface por
uma rede pública.

### 3. O que é alterado e como o rollback funciona

- comandos: `~/.local/bin/claude-hub`, `~/.local/bin/ch` e auxiliares;
- frontend: `~/.local/share/ai-central-web/`;
- atalhos: `~/.local/share/applications/`;
- unidades: `~/.config/systemd/user/`;
- backups: `~/.local/state/ai-central/backups/AAAAmmdd-HHMMSS/`.

Antes da primeira escrita, o instalador valida Bash e Python. Depois copia cada
destino anterior, registra os estados das unidades e faz a atualização. Se
assets, systemd, health ou `ch doctor` falharem, restaura arquivos e estados das
unidades sem encerrar o tmux ou os agentes existentes. Reexecutar o instalador é
seguro e cria um novo snapshot, inclusive ao atualizar versões.

### 4. Validar

```bash
ch doctor
ch status
systemctl --user status claude-hub ai-hub-restore ai-hub-monitor ai-central-web
systemctl --user is-enabled ai-central-terminal
loginctl show-user "$USER" -p Linger
```

O comando curto `ch` é um executável instalado, não um alias dependente do
`.zshrc`. Se `ch` não for encontrado em uma shell antiga, execute uma vez
`hash -r` ou abra uma nova shell; `~/.local/bin` precisa estar no `PATH`.

## Instalação no Android

### Pré-requisitos

1. Instale e autentique o Tailscale no Android na mesma tailnet do PC.
2. Instale Termux e Termux:Widget pela mesma origem.
3. Para o preflight automático após reinício, instale também Termux:Boot pela
   mesma origem e abra o aplicativo Termux:Boot uma vez.
4. Abra Termux ao menos uma vez e autorize a depuração USB do computador.
5. Confirme no PC: `adb devices -l` deve mostrar o aparelho como `device`.

O instalador não baixa APKs nem tenta automatizar o login do Tailscale. Isso
evita misturar assinaturas/fontes de Termux e não guarda credenciais. Ele instala
o pacote `openssh` dentro do Termux automaticamente quando necessário.

### Opção A — instalação direta via ADB

Com um único aparelho conectado:

```bash
./install-ai-central-android.sh --check
./install-ai-central-android.sh
```

Com vários aparelhos ou parâmetros explícitos:

```bash
./install-ai-central-android.sh \
  --serial 0123456789ABCDEF \
  --host 100.64.0.1 \
  --user meu-usuario
```

Ou faça PC e celular em uma única execução:

```bash
./install-ai-central.sh --auto --android --serial 0123456789ABCDEF
```

Nesse modo combinado, Termux:Boot é requisito: `--auto` promete retomada após
reinícios e, portanto, não aceita silenciosamente uma instalação móvel incapaz
de executar o preflight. No instalador Android isolado ele continua opcional;
use `--require-boot` para aplicar o mesmo portão.

A automação direta:

1. valida ADB, Termux, Tailscale, porta SSH do PC e parâmetros;
2. transfere somente o payload móvel para
   `/sdcard/Download/ai-central-mobile/`;
3. compara o SHA-256 de cada arquivo no PC e no Android;
4. desanexa apenas a tela móvel antiga — agentes e workflows seguem vivos;
5. abre uma nova sessão local do Termux, sem digitar sobre um Claude ativo;
6. cria backup, mescla o bloco gerenciado de `termux.properties` e instala os
   atalhos;
7. gera uma chave Ed25519 no Android se necessário e autoriza a chave pelo
   conteúdo, sem duplicá-la por causa do comentário;
8. exige um arquivo de resultado `status=ok` e um novo cliente `claude-mobile`
   no tmux antes de declarar sucesso.

Se a tela estiver bloqueada, a automação para e entrega o comando manual; ela
não tenta contornar o bloqueio do Android.

### Opção B — ADB com conclusão manual

No PC:

```bash
./install-ai-central-android.sh --manual
```

O comando exato aparecerá na tela. Execute-o em uma shell comum do Termux. A
forma totalmente manual equivalente é:

```bash
adb shell mkdir -p /sdcard/Download/ai-central-mobile
adb push mobile/. /sdcard/Download/ai-central-mobile/
bash /sdcard/Download/ai-central-mobile/install-termux.sh \
  100.64.0.1 meu-usuario
```

O último `bash` é executado dentro do Termux, não no `adb shell`.

O instalador móvel:

- mantém o SSH da central isolado em `~/.config/ai-central/ssh-config`;
- não sobrescreve `~/.ssh/config`;
- guarda versões anteriores em `~/.config/ai-central/backups/`;
- instala `PC-Hub` e `PC-Shell` em `~/.shortcuts/`;
- instala um preflight não visual em `~/.termux/boot/ai-central`;
- instala a barra móvel com `TECLA`, `MENU`, `+SH`, `ANT`, `PROX`, `OK`, `TELA`
  e `SAIR`.

Atualize o widget do Termux ou remova e adicione-o novamente à tela inicial caso
os atalhos não apareçam de imediato.

### Validar o Android

No PC:

```bash
adb shell cat /sdcard/Download/ai-central-mobile/install-result.txt
tmux list-clients -F '#{client_session} #{client_width}x#{client_height} #{client_tty}'
ch doctor
```

Após reiniciar o celular e desbloqueá-lo, o Termux:Boot grava o último preflight
em `~/.cache/ai-central/boot-status`. Ele não anexa um cliente invisível, pois
isso reduziria a grade compartilhada e poderia recriar os pontos no Konsole.

## Disponibilidade e reinícios

| Evento | O que retorna automaticamente |
|---|---|
| Login/relogin no PC | hub, restore, monitor, PWA e um Konsole central |
| Reinício do PC com `--auto`/`--always-on` | hub, restore, monitor e PWA antes do login; Konsole ao entrar na sessão gráfica |
| Queda de SSH/Tailscale no celular | `PC-Hub` mostra offline e tenta reconectar; o tmux permanece no PC |
| Reinício do Android com Termux:Boot | preflight inicializa/confirma o hub após o primeiro desbloqueio |
| Abrir `PC-Hub` ou a PWA depois | reconecta à mesma sessão tmux e ao mesmo processo vivo |

Nenhum sistema Android confiável pode prometer abrir uma Activity interativa
antes do primeiro desbloqueio, e fabricantes podem suspender apps em segundo
plano. Retire Tailscale, Termux e Termux:Boot da otimização agressiva de bateria
se o aparelho a aplicar. Mesmo nesse caso, os processos de desenvolvimento
continuam no PC; o celular é um cliente descartável e reconectável.

## Fluxo diário

### No PC

```bash
ch status
ch gui
ch open amaral-hub
ch here
```

Ao ligar o PC, a unidade `ai-central-terminal.service` executa a mesma operação
de `ch attach`: o Konsole já nasce conectado ao hub compartilhado. Para abrir
outra janela organizada na sessão correta, use `ch open NOME`; não execute um
segundo `claude --resume` para uma sessão que ainda está viva.

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

Exemplo de uma central organizada com dois repositórios e dois agentes isolados:

```bash
ch start-claude adb-main /var/www/adb_tools
ch start-codex hub-review /var/www/amaral-intern-hub
ch worktree-claude adb-ui /var/www/adb_tools ai/mobile-ui
ch list
ch open adb-main
```

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

A remoção não desativa `linger`, `sshd`, `tailscaled`, Termux, Tailscale nem
Termux:Boot: esses componentes podem ser compartilhados por outros serviços e
exigem uma decisão explícita do administrador.

## Referências oficiais do Android

- [Termux app: instalação e fontes compatíveis](https://github.com/termux/termux-app)
- [Atalhos de teclado do Termux](https://github.com/termux/termux-tools/blob/master/doc/termux.1.md.in)
- [Permissão oficial RUN_COMMAND](https://github.com/termux/termux-app/wiki/RUN_COMMAND-Intent)

A instalação ADB deliberadamente não usa `RUN_COMMAND`: essa API é destinada a
outro aplicativo Android que declare a permissão correspondente e requer
habilitar aplicativos externos no Termux. O ADB shell não possui essa permissão.
Por isso a automação usa o atalho oficial de nova sessão e mantém o modo manual
como fallback verificável.
