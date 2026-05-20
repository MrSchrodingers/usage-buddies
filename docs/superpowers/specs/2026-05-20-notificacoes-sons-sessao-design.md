# Notificações + sons para eventos de sessão e janela semanal

**Data:** 2026-05-20
**Autor:** Arthur (via Claude Code)
**Status:** Aprovado para implementação

## Objetivo

Quando a sessão atual (janela 5h) ou a janela semanal (7d) **acabarem** (uso atinge 100%) ou **resetarem** (janela vira e contador zera), o widget deve:

1. Disparar uma notificação visual de desktop (`notify-send`).
2. Tocar um som distinto por evento (4 sons diferentes).

A notificação visual é obrigatória mesmo quando o sistema está mutado — porque ela aparece na tela. O som é complemento.

## Escopo

### Eventos cobertos (4 no total)

| ID interno | Disparo | Som padrão (freedesktop) | Urgência |
|---|---|---|---|
| `sessionEnded` | Sessão 5h atinge 100% | `dialog-warning` | normal |
| `sessionReset` | Sessão 5h zera (`resetsAt` vira para o futuro) | `complete` | low |
| `weeklyEnded` | Semanal geral atinge 100% | `suspend-error` | critical |
| `weeklyReset` | Semanal geral zera (`resetsAt` vira para o futuro) | `service-login` | normal |

### Explicitamente fora de escopo

- **Limites do Opus** (`weeklyOpus`). Decisão do usuário.
- **Threshold intermediário** (ex: alertar em 80%, 90%). Só 100% e reset.
- **Repetição/lembrete**. Cada transição dispara uma única vez.

## Arquitetura

### Local

Tudo dentro de `scripts/claude-usage-collector.py`, espelhando o padrão de `notify_status_change()` (linhas ~903-955 do arquivo atual). Sem módulo novo — a feature é pequena o suficiente para conviver com a função existente.

O collector já roda via systemd timer (`scripts/claude-usage-collector.timer`) periodicamente, então a detecção é por polling: cada execução compara estado atual com o snapshot da execução anterior.

### Funções novas

```
detect_usage_transitions(curr_data) -> list[Event]
    Função pura (testável). Lê snapshot de ~/.claude/widget-events-state.json,
    compara com curr_data, retorna lista de eventos detectados,
    grava snapshot novo.

notify_usage_event(event_id, title, body, urgency, sound)
    Irmã de notify_status_change. Envia notify-send (com --app-name
    "Claude Usage", --icon claude-logo) e dispara play_event_sound em background.

play_event_sound(sound_spec)
    subprocess.Popen fire-and-forget. Se sound_spec não tem "/", trata como
    nome freedesktop e usa "canberra-gtk-play -i <nome>". Se contém "/",
    trata como caminho e usa "paplay <path>".
```

### Estado persistido

Arquivo separado: `~/.claude/widget-events-state.json`.

```json
{
  "session": {
    "percentUsed": 67,
    "resetsAt": "2026-05-20T18:00:00Z"
  },
  "weeklyAll": {
    "percentUsed": 42,
    "resetsAt": "2026-05-25T12:00:00Z"
  },
  "lastRun": "2026-05-20T15:42:11Z"
}
```

Separado de `widget-data.json` para não poluir o contrato com as UIs e permitir gravação independente.

### Configuração

Adicionar seção em `~/.claude/widget-config.json`:

```json
"notifications": {
  "enabled": true,
  "sounds": {
    "sessionEnded": "dialog-warning",
    "sessionReset": "complete",
    "weeklyEnded":  "suspend-error",
    "weeklyReset":  "service-login"
  }
}
```

Valores aceitos para sons:
- Nome freedesktop (sem extensão): ex. `complete`, `bell`, `alarm-clock-elapsed`. Lista em `/usr/share/sounds/freedesktop/stereo/`.
- Caminho absoluto para arquivo `.wav` / `.oga` / `.ogg`: ex. `/home/user/sounds/meu.wav`.

Se a chave `notifications` não existir no config, os defaults da tabela acima são usados. Se `enabled: false`, nada dispara.

## Regras de detecção

### `acabou` (sessionEnded / weeklyEnded)

```
prev_pct = snapshot anterior do percentUsed (None se 1ª execução)
curr_pct = curr_data.rateLimits.<escopo>.percentUsed

dispara se:
  (prev_pct is None and curr_pct >= 100)   # 1ª execução já estourada
  OR
  (prev_pct is not None and prev_pct < 100 and curr_pct >= 100)  # transição
```

### `resetou` (sessionReset / weeklyReset)

```
prev_reset = snapshot.resetsAt
curr_reset = curr_data.rateLimits.<escopo>.resetsAt
prev_pct   = snapshot.percentUsed

dispara se:
  prev_reset existe AND curr_reset existe
  AND curr_reset > prev_reset + 1 hora    # janela claramente virou
  AND prev_pct > 5                         # havia uso significativo
```

O threshold de 5% evita disparar reset em estado idle (quando o widget rodou várias vezes com uso zero e o `resetsAt` rola normalmente).

### Anti-spam

Como o snapshot é gravado a cada execução, uma transição só pode ser detectada uma vez: na execução seguinte, `prev_pct` já reflete o estado pós-transição.

## Robustez e tratamento de erros

- **Binários ausentes** (`canberra-gtk-play`, `paplay`, `notify-send`): log no stderr, segue silencioso. Nunca quebra o collector.
- **Snapshot corrompido**: `json.loads` em try/except; em erro, trata como 1ª execução e regrava limpo.
- **Sem display server** (`DISPLAY` / `WAYLAND_DISPLAY` ausentes): pula notificação e som (idêntico ao guard existente em `notify_status_change`).
- **Plataforma não-Linux**: pula tudo (idêntico ao guard existente).
- **Subprocess de som**: `subprocess.Popen(..., start_new_session=True, stdout=DEVNULL, stderr=DEVNULL)`. Fire-and-forget — o collector nunca trava esperando.

## CLI

Nova flag em `claude-usage-collector.py`:

```
python claude-usage-collector.py --test-sounds
```

Comportamento:
1. Lê config (ou usa defaults).
2. Para cada um dos 4 eventos, imprime no stdout `▶ <evento> → <sound>` e toca o som.
3. Aguarda ~1.5s entre sons.
4. Não dispara notificações. Não toca em `widget-events-state.json`. Não atualiza `widget-data.json`.

## Testes

### Unitários (`tests/test_notifier.py`)

Cobertura de `detect_usage_transitions`:

- **1ª execução com tudo OK**: snapshot vazio, curr em 50% → 0 eventos, snapshot gravado.
- **1ª execução já estourada**: snapshot vazio, curr em 100% → `sessionEnded` (e/ou `weeklyEnded`).
- **Transição acabou**: prev 95%, curr 100% → 1 evento.
- **Sem transição (estável em 100%)**: prev 100%, curr 100% → 0 eventos.
- **Sem transição (estável em <100%)**: prev 60%, curr 70% → 0 eventos.
- **Reset detectado**: prev `resetsAt = T`, prev_pct 80%, curr `resetsAt = T + 5h`, curr_pct 0% → 1 evento.
- **Reset idle ignorado**: prev_pct 2%, mesma mudança de `resetsAt` → 0 eventos.
- **Reset + acabou no mesmo ciclo**: prev em 100%, curr resetou mas já voltou a estar em 100% (cenário raro, mas possível) → 2 eventos.

### Manual

- Rodar `--test-sounds` e ouvir os 4 sons.
- Editar `widget-events-state.json` manualmente para forçar transição artificial e confirmar `notify-send` + som disparam.

## Arquivos afetados

| Arquivo | Mudança |
|---|---|
| `scripts/claude-usage-collector.py` | + 3 funções, + chamada no fluxo principal, + flag `--test-sounds`, + leitura de `notifications` no config |
| `tests/test_notifier.py` | Novo — testes unitários de `detect_usage_transitions` |
| `~/.claude/widget-config.json` | Documentação atualizada em README; chave opcional, defaults internos |
| `~/.claude/widget-events-state.json` | Novo arquivo de runtime (gerado pelo collector, ignorado em git) |
| `README.md` (raiz) | Seção curta sobre notificações, lista dos 4 eventos e como customizar |

## Decisões registradas e razão

1. **Detecção no collector, não nas UIs.** Funciona com widget fechado, evita triplicar código em QML/JS/extension. (Confirmado pelo usuário.)
2. **Freedesktop como default + override custom.** Zero dependência de arte/binários no repo, mas usuário avançado pode trocar. (Confirmado pelo usuário.)
3. **Notificação sempre + som como complemento.** Visibilidade garantida mesmo com sistema mutado. (Confirmado pelo usuário.)
4. **Primeira execução = avisa se já em 100%.** Comportamento útil pós-instalação para usuários já estourados. (Confirmado pelo usuário.)
5. **`--test-sounds` + teste interativo agora.** Sons já validados pelo usuário durante o brainstorming. (Confirmado.)
6. **Reaproveitar padrão de `notify_status_change`** em vez de criar `notifier.py`. Feature pequena, mantém collector coeso. (Confirmado pelo usuário.)
7. **Sem Opus.** Decisão explícita do usuário.
8. **Snapshot em arquivo separado** (`widget-events-state.json`). Mantém contrato do `widget-data.json` limpo para as UIs.

## Mapeamento de sons aprovado

| Evento | Som freedesktop | Razão |
|---|---|---|
| sessionEnded | `dialog-warning` | Alerta moderado, ocorre com frequência |
| sessionReset | `complete` | Curto/neutro, "liberou" |
| weeklyEnded | `suspend-error` | Mais grave, raro e impactante |
| weeklyReset | `service-login` | Renovação positiva |
