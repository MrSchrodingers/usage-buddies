#!/usr/bin/env python3
"""One read-only state snapshot for the AI terminal hub.

The desktop GUI, tmux menu and notifier all consume this file so status words
cannot drift between surfaces. Claude state comes from Usage Buddies'
background-aware sessions probe. Codex state comes from structural rollout
events: a turn is not complete until ``task_complete`` is the latest lifecycle
event and has remained settled long enough for an automatic continuation to
start.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from ai_hub_registry import sync_snapshot as sync_session_registry
except ImportError:  # The status view still works during a partial install.
    sync_session_registry = None

HOME = Path.home()
CLAUDE_USAGE = HOME / ".claude" / "widget-data.json"
CODEX_USAGE = HOME / ".codex" / "widget-data.json"
CLAUDE_SESSIONS = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / "usage-buddies" / "sessions.json"
CODEX_ROLLOUTS = HOME / ".codex" / "sessions"
NOTIFY_STATE = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / "claude-hub" / "notify-state.json"
STATE_CACHE = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / "claude-hub" / "state.json"
SETTLED_SECONDS = 20
IDLE_SECONDS = 600
ACTIVE_SHELLS = {"bash", "dash", "fish", "pwsh", "sh", "zsh"}

STATE_UI = {
    "working": ("TRABALHANDO", "#38bdf8", "●"),
    "background": ("WORKFLOW ATIVO", "#c084fc", "◉"),
    "asking": ("PRECISA DE VOCÊ", "#fbbf24", "◆"),
    "finished": ("FINALIZADO", "#4ade80", "●"),
    "waiting": ("FINALIZADO", "#4ade80", "●"),
    "idle": ("PARADO", "#94a3b8", "◌"),
    "finalizing": ("FINALIZANDO", "#67e8f9", "◉"),
    "live": ("AO VIVO", "#a78bfa", "●"),
    "dead": ("ENCERRADO", "#f87171", "×"),
    "shell": ("SHELL", "#94a3b8", "○"),
}


def run(command: list[str], timeout: float = 5) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return subprocess.CompletedProcess(command, 1, "", "")


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def cached_snapshot(max_age: int = 15) -> dict | None:
    try:
        if time.time() - STATE_CACHE.stat().st_mtime > max(1, max_age):
            return None
    except OSError:
        return None
    data = read_json(STATE_CACHE, None)
    return data if isinstance(data, dict) and isinstance(data.get("sessions"), list) else None


def write_snapshot_cache(data: dict) -> None:
    STATE_CACHE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = STATE_CACHE.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, STATE_CACHE)


def process_children(pid: int) -> list[int]:
    try:
        raw = Path(f"/proc/{pid}/task/{pid}/children").read_text().split()
        return [int(child) for child in raw]
    except (OSError, ValueError):
        return []


def process_name(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/comm").read_text().strip()
    except OSError:
        return ""


def process_session_hint(pid: int | None) -> str:
    if not pid:
        return ""
    try:
        arguments = [part.decode(errors="replace") for part in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0") if part]
    except OSError:
        return ""
    for flag in ("--resume", "attach"):
        if flag in arguments:
            position = arguments.index(flag)
            if position + 1 < len(arguments):
                return arguments[position + 1]
    return ""


def descendant_process(root_pid: int, names: set[str]) -> int | None:
    queue = [root_pid]
    seen: set[int] = set()
    while queue:
        pid = queue.pop(0)
        if pid in seen:
            continue
        seen.add(pid)
        if process_name(pid) in names:
            return pid
        queue.extend(process_children(pid))
    return None


def active_shell_descendant(root_pid: int | None) -> int | None:
    """Return a shell still owned by an agent after its foreground turn."""
    if not root_pid:
        return None
    queue = process_children(root_pid)
    seen: set[int] = set()
    while queue:
        pid = queue.pop(0)
        if pid in seen:
            continue
        seen.add(pid)
        if process_name(pid) in ACTIVE_SHELLS:
            return pid
        queue.extend(process_children(pid))
    return None


def process_started_at(pid: int | None) -> float:
    if not pid:
        return 0.0
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().split()
        ticks = float(fields[21])
        uptime = float(Path("/proc/uptime").read_text().split()[0])
        return time.time() - uptime + ticks / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError):
        return 0.0


def git_info(directory: str) -> dict:
    root_result = run(["git", "-C", directory, "rev-parse", "--show-toplevel"], timeout=2)
    if root_result.returncode != 0:
        return {"root": directory, "groupRoot": directory, "group": Path(directory).name or directory, "branch": ""}
    root = root_result.stdout.strip()
    common_result = run(
        ["git", "-C", directory, "rev-parse", "--path-format=absolute", "--git-common-dir"], timeout=2
    )
    common = common_result.stdout.strip() if common_result.returncode == 0 else str(Path(root) / ".git")
    common_path = Path(common)
    group_root = str(common_path.parent) if common_path.name == ".git" else root
    branch_result = run(["git", "-C", directory, "branch", "--show-current"], timeout=2)
    return {
        "root": root,
        "groupRoot": group_root,
        "group": Path(group_root).name or group_root,
        "branch": branch_result.stdout.strip() if branch_result.returncode == 0 else "",
        "isWorktree": Path(root) != Path(group_root),
    }


def parse_time(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def file_records(path: Path, tail_bytes: int = 256 * 1024) -> list[dict]:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > tail_bytes:
                handle.seek(-tail_bytes, os.SEEK_END)
                handle.readline()
            lines = handle.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return []
    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def rollout_identity(path: Path) -> tuple[str, str]:
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for _ in range(8):
                line = handle.readline()
                if not line:
                    break
                record = json.loads(line)
                if record.get("type") == "session_meta":
                    payload = record.get("payload") or {}
                    return str(payload.get("cwd") or ""), str(payload.get("id") or "")
    except (OSError, json.JSONDecodeError):
        pass
    return "", ""


def newest_codex_rollout(directory: str, started_at: float) -> tuple[Path | None, str]:
    try:
        candidates = sorted(CODEX_ROLLOUTS.glob("**/*.jsonl"), key=lambda item: item.stat().st_mtime, reverse=True)
    except OSError:
        return None, ""
    resolved = str(Path(directory).resolve())
    for candidate in candidates[:500]:
        try:
            if started_at and candidate.stat().st_mtime < started_at - 90:
                continue
        except OSError:
            continue
        cwd, session_id = rollout_identity(candidate)
        try:
            matches = str(Path(cwd).resolve()) == resolved
        except OSError:
            matches = cwd == directory
        if matches:
            return candidate, session_id
    return None, ""


def codex_state(directory: str, started_at: float) -> tuple[str, str, str]:
    rollout, session_id = newest_codex_rollout(directory, started_at)
    if not rollout:
        return "live", "Codex conectado", ""
    records = file_records(rollout)

    completed_calls = {
        (record.get("payload") or {}).get("call_id")
        for record in records
        if record.get("type") == "response_item"
        and (record.get("payload") or {}).get("type") in {"custom_tool_call_output", "function_call_output"}
    }
    for record in reversed(records):
        payload = record.get("payload") or {}
        if record.get("type") != "response_item":
            continue
        if payload.get("type") not in {"custom_tool_call", "function_call"}:
            continue
        name = str(payload.get("name") or "")
        if "request_user_input" in name and payload.get("call_id") not in completed_calls:
            return "asking", "Aguardando sua resposta", session_id
        break

    lifecycle = None
    for record in reversed(records):
        payload = record.get("payload") or {}
        if record.get("type") == "event_msg" and payload.get("type") in {"task_started", "task_complete"}:
            lifecycle = (payload.get("type"), parse_time(record.get("timestamp")))
            break
    if not lifecycle:
        return "live", "Codex conectado", session_id
    event, timestamp = lifecycle
    age = max(0, int(time.time() - timestamp)) if timestamp else 0
    if event == "task_started":
        return "working", "Turno ou workflow em execução", session_id
    if age < SETTLED_SECONDS:
        return "finalizing", "Confirmando que não haverá continuação automática", session_id
    if age >= IDLE_SECONDS:
        return "idle", f"Sem atividade há {age // 60} min", session_id
    return "finished", "Turno concluído; pronto para novo comando", session_id


def usage_summary(provider: str, data: dict) -> dict:
    limits = data.get("rateLimits") or {}
    session = limits.get("session") or {}
    weekly = limits.get("weeklyAll") or limits.get("weekly") or {}
    base = {
        "provider": provider,
        "available": data.get("available", True),
        "sessionPercent": float(session.get("percentUsed") or 0),
        "sessionResetMinutes": session.get("resetsInMinutes"),
        "weeklyPercent": float(weekly.get("percentUsed") or 0),
        "weeklyReset": weekly.get("resetsLabel") or "",
        "plan": limits.get("plan") or "",
        "source": limits.get("source") or data.get("source") or "",
    }
    if provider == "claude":
        errors = data.get("errorRate") or {}
        service = data.get("serviceStatus") or {}
        base.update(
            errors=int(errors.get("total") or 0),
            errorDetail=errors,
            health=service.get("description") or (data.get("health") or {}).get("state") or "Desconhecido",
            incident=(service.get("active_incidents") or [{}])[0].get("name", ""),
            burnPerHour=int((data.get("burnRate") or {}).get("output_per_hour") or 0),
            latency=float((data.get("health") or {}).get("latencySeconds") or 0),
        )
    else:
        endpoints = (data.get("browserApi") or {}).get("endpoints") or {}
        bad_endpoints = [name for name, status in endpoints.items() if status != "ok"]
        account = data.get("account") or {}
        base.update(
            errors=len(bad_endpoints),
            errorDetail={"endpoints": bad_endpoints},
            health="Limite atingido" if account.get("limitReached") else ("API conectada" if data.get("available") else "Indisponível"),
            incident="",
            currentThreadTokens=int((data.get("activity") or {}).get("currentThreadTokens") or 0),
            weeklyTokens=int((data.get("activity") or {}).get("last7DaysTokens") or 0),
        )
    return base


def snapshot() -> dict:
    claude_probe = read_json(CLAUDE_SESSIONS, {})
    claude_by_pid = {int(item["pid"]): item for item in claude_probe.get("sessions", []) if item.get("pid")}
    claude_by_dir = {item.get("cwd"): item for item in claude_probe.get("sessions", [])}
    claude_by_session = {item.get("sessionId"): item for item in claude_probe.get("sessions", []) if item.get("sessionId")}

    windows_result = run(
        ["tmux", "list-windows", "-t", "claude-hub", "-F",
         "#{window_index}\t#{window_name}\t#{pane_current_path}\t#{pane_current_command}\t#{pane_dead}\t#{pane_pid}"],
        timeout=5,
    )
    sessions = []
    for line in windows_result.stdout.splitlines():
        fields = line.split("\t", 5)
        if len(fields) != 6:
            continue
        index, name, directory, command, dead_raw, pane_pid_raw = fields
        dead = dead_raw == "1"
        pane_pid = int(pane_pid_raw)
        provider = "shell"
        state = "dead" if dead else "shell"
        detail = "Pane encerrado" if dead else "Shell compartilhado"
        session_id = ""
        pid = None
        background = 0

        if command == "claude" and not dead:
            provider = "claude"
            pid = descendant_process(pane_pid, {"claude"})
            session_hint = process_session_hint(pid)
            probed = (claude_by_pid.get(pid or -1) or claude_by_session.get(session_hint)
                      or next((value for key, value in claude_by_session.items()
                               if session_hint and key.startswith(session_hint)), None)
                      or claude_by_dir.get(directory) or {})
            state = str(probed.get("state") or "live")
            detail = str(probed.get("detail") or "Claude conectado")
            background = int(probed.get("background") or 0)
            if state == "background" and background:
                detail = f"{background} agente(s) ou tarefa(s) em background"
            session_id = str(probed.get("sessionId") or session_hint)
        elif command in {"codex", "codex-cli"} and not dead:
            provider = "codex"
            pid = descendant_process(pane_pid, {"codex", "codex-cli"})
            state, detail, session_id = codex_state(directory, process_started_at(pid))
            if state in {"finalizing", "finished", "idle"} and active_shell_descendant(pid):
                state = "background"
                background = 1
                detail = "Comando ou workflow ainda ativo em background"

        status, color, marker = STATE_UI.get(state, STATE_UI["live"])
        repository = git_info(directory)
        sessions.append(
            {
                "index": int(index),
                "name": name,
                "directory": directory,
                "command": command,
                "provider": provider,
                "state": state,
                "status": status,
                "color": color,
                "marker": marker,
                "detail": detail,
                "sessionId": session_id,
                "pid": pid,
                "background": background,
                "live": provider in {"claude", "codex"} and not dead,
                "dead": dead,
                "repository": repository,
            }
        )

    known_pids = {item.get("pid") for item in sessions if item.get("pid")}
    external_sessions = []
    try:
        process_entries = list(Path("/proc").iterdir())
    except OSError:
        process_entries = []
    for entry in process_entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        provider_name = process_name(pid)
        if pid in known_pids or provider_name not in {"claude", "codex", "codex-cli"}:
            continue
        try:
            directory = str(Path(f"/proc/{pid}/cwd").resolve())
        except OSError:
            continue
        if provider_name == "claude":
            provider = "claude"
            probed = claude_by_pid.get(pid) or {}
            state = str(probed.get("state") or "live")
            detail = str(probed.get("detail") or "Claude ativo fora do hub")
            session_id = str(probed.get("sessionId") or process_session_hint(pid))
            background = int(probed.get("background") or 0)
            display_name = str(probed.get("name") or Path(directory).name or f"claude-{pid}")
        else:
            provider = "codex"
            state, detail, session_id = codex_state(directory, process_started_at(pid))
            background = 0
            if state in {"finalizing", "finished", "idle"} and active_shell_descendant(pid):
                state = "background"
                background = 1
                detail = "Comando ou workflow ainda ativo em background"
            display_name = Path(directory).name or f"codex-{pid}"
        status, color, marker = STATE_UI.get(state, STATE_UI["live"])
        external_sessions.append(
            {
                "index": "EXT",
                "name": display_name,
                "directory": directory,
                "command": provider_name,
                "provider": provider,
                "state": state,
                "status": status,
                "color": color,
                "marker": marker,
                "detail": detail,
                "sessionId": session_id,
                "pid": pid,
                "background": background,
                "live": True,
                "dead": False,
                "external": True,
                "repository": git_info(directory),
            }
        )

    clients_result = run(["tmux", "list-clients", "-F", "#{client_session}\t#{client_width}x#{client_height}"], timeout=3)
    clients = clients_result.stdout.splitlines() if clients_result.returncode == 0 else []
    usage = {
        "claude": usage_summary("claude", read_json(CLAUDE_USAGE, {})),
        "codex": usage_summary("codex", read_json(CODEX_USAGE, {})),
    }
    alerts = []
    for provider, item in usage.items():
        if item["sessionPercent"] >= 95:
            alerts.append({"severity": "critical", "provider": provider, "message": f"Sessão em {item['sessionPercent']:.0f}%"})
        elif item["sessionPercent"] >= 80:
            alerts.append({"severity": "warning", "provider": provider, "message": f"Sessão em {item['sessionPercent']:.0f}%"})
        if item.get("errors"):
            alerts.append({"severity": "warning", "provider": provider, "message": f"{item['errors']} erro(s) recente(s)"})
        if item.get("incident"):
            alerts.append({"severity": "warning", "provider": provider, "message": item["incident"]})
    if external_sessions:
        alerts.append(
            {
                "severity": "warning",
                "provider": "hub",
                "message": f"{len(external_sessions)} agente(s) ativo(s) fora da central",
            }
        )

    return {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "updated": time.strftime("%H:%M:%S"),
        "sessions": sorted(sessions, key=lambda item: item["index"]),
        "externalSessions": sorted(external_sessions, key=lambda item: (item["provider"], item["name"], item["pid"])),
        "clients": len(clients),
        "mobile": sum(1 for item in clients if item.startswith("claude-mobile\t")),
        "usage": usage,
        "alerts": alerts,
    }


def human_number(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}k"
    return str(value)


def dashboard(data: dict) -> str:
    lines = ["\033[1;36mAI CENTRAL · STATUS GERAL\033[0m", ""]
    for provider in ("claude", "codex"):
        item = data["usage"][provider]
        name = provider.upper().ljust(6)
        health = item.get("health") or "--"
        lines.append(
            f"\033[1m{name}\033[0m  sessão {item['sessionPercent']:>3.0f}%  semana {item['weeklyPercent']:>3.0f}%  "
            f"erros {item.get('errors', 0)}"
        )
        lines.append(f"        {health[:52]}")
    lines.extend(["", "\033[1mSESSÕES E SHELLS\033[0m"])
    for item in data["sessions"]:
        provider = {"claude": "CL", "codex": "CX", "shell": "SH"}[item["provider"]]
        lines.append(f"{item['marker']} {item['index']:<2} {provider} {item['name'][:18]:<18} {item['status']}")
        if item["background"]:
            lines.append(f"       {item['background']} trabalho(s) em background")
    external = data.get("externalSessions", [])
    if external:
        names = ", ".join(f"{item['provider'][:2].upper()}:{item['name']}" for item in external)
        lines.extend(["", f"\033[1;33mFORA DO HUB ({len(external)})\033[0m  {names}"])
    if data["alerts"]:
        lines.extend(["", "\033[1;33mATENÇÃO\033[0m"])
        lines.extend(f"! {item['provider'].upper()}: {item['message']}" for item in data["alerts"][:5])
    lines.extend(
        [
            "",
            "\033[1mCOMANDOS RÁPIDOS\033[0m",
            "ch gui                   central gráfica",
            "ch wizard claude         novo Claude",
            "ch wizard codex          novo Codex",
            "ch wizard resume-claude  retomar Claude",
            "ch wizard resume-codex   retomar Codex",
            "ch wizard worktree       paralelo isolado",
            "Ctrl-b w                 menu em qualquer tela",
            "",
            f"Atualizado {data['updated']} · {data['clients']} tela(s) · celular {'on' if data['mobile'] else 'off'}",
        ]
    )
    return "\n".join(lines)


def send_notification(title: str, body: str, urgency: str = "normal") -> None:
    run(
        ["notify-send", "--app-name=AI Central", "--icon=utilities-terminal", f"--urgency={urgency}",
         "--expire-time=12000", title, body],
        timeout=3,
    )


def notify_transitions(data: dict) -> None:
    previous = read_json(NOTIFY_STATE, {})
    initialized = bool(previous)
    current = {}
    for item in data["sessions"]:
        if item["provider"] not in {"claude", "codex"}:
            continue
        key = item["name"]
        current[key] = {"provider": item["provider"], "state": item["state"], "directory": item["directory"]}
        before = previous.get(key) or {}
        if not initialized or before.get("state") == item["state"]:
            continue
        if not before:
            provider_name = "Claude" if item["provider"] == "claude" else "Codex"
            send_notification(
                f"{provider_name} · {item['name']}: conectado",
                "Sessão sincronizada e pronta no PC e no celular.",
            )
            continue
        # Claude completion/question notifications are already emitted by the
        # sessions probe. Codex has no equivalent collector hook here.
        if item["provider"] == "codex" and item["state"] in {"finished", "asking"}:
            asking = item["state"] == "asking"
            title = f"Codex · {item['name']}: {'precisa de você' if asking else 'finalizado'}"
            body = "Está aguardando sua resposta." if asking else "Turno concluído e sem workflow ativo."
            send_notification(title, body, "critical" if asking else "normal")
        elif item["state"] == "idle":
            provider_name = "Claude" if item["provider"] == "claude" else "Codex"
            send_notification(
                f"{provider_name} · {item['name']}: parado",
                "A sessão continua sincronizada e pode receber um novo comando.",
                "low",
            )

    if initialized:
        for key, before in previous.items():
            if key in current or before.get("provider") not in {"claude", "codex"}:
                continue
            send_notification(
                f"{before['provider'].title()} · {key}: encerrado",
                "O processo saiu do hub; o histórico da sessão foi preservado.",
            )

    NOTIFY_STATE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = NOTIFY_STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(current, separators=(",", ":")), encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, NOTIFY_STATE)


def monitor(interval: int) -> None:
    running = True

    def stop(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while running:
        try:
            data = snapshot()
            write_snapshot_cache(data)
            if sync_session_registry:
                sync_session_registry(data)
            notify_transitions(data)
        except Exception as error:
            print(f"ai-hub monitor: {type(error).__name__}", file=sys.stderr)
        for _ in range(interval):
            if not running:
                break
            time.sleep(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", action="store_true")
    parser.add_argument("--monitor", action="store_true")
    parser.add_argument("--notify-once", action="store_true")
    parser.add_argument("--cached", action="store_true")
    parser.add_argument("--max-age", type=int, default=15)
    parser.add_argument("--interval", type=int, default=8)
    args = parser.parse_args()
    if args.monitor:
        monitor(max(3, args.interval))
        return 0
    data = cached_snapshot(args.max_age) if args.cached else None
    if data is None:
        data = snapshot()
        if args.cached:
            write_snapshot_cache(data)
    if args.notify_once:
        notify_transitions(data)
    if args.text:
        print(dashboard(data))
    else:
        print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
