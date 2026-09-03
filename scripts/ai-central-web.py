#!/usr/bin/env python3
"""Private, Tailscale-first web control surface for AI Central."""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import pty
import re
import secrets
import signal
import struct
import subprocess
import termios
from contextlib import suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

HOME = Path.home()
ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "ai-central-web"
STATIC = WEB_ROOT / "static"
HUB = HOME / ".local/bin/claude-hub"
STATE = HOME / ".local/bin/ai-hub-state.py"
RESTORE = HOME / ".local/bin/ai-hub-restore.py"
REGISTRY = HOME / ".local/bin/ai-hub-registry.py"
TOKEN_FILE = Path(os.environ.get("AI_CENTRAL_TOKEN_FILE", HOME / ".config/ai-central/web-token"))
NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

app = FastAPI(title="AI Central", docs_url=None, redoc_url=None, openapi_url=None)


def run(command: list[str], timeout: float = 15, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, text=True, capture_output=True, check=False, timeout=timeout, env=env)
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(command, 1, "", str(exc))


def access_token() -> str:
    try:
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if len(token) >= 32:
            return token
    except OSError:
        pass
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    token = secrets.token_urlsafe(32)
    temporary = TOKEN_FILE.with_suffix(".tmp")
    temporary.write_text(token + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, TOKEN_FILE)
    return token


def authorised(value: str | None) -> bool:
    return bool(value and secrets.compare_digest(value, access_token()))


def request_token(request: Request) -> str | None:
    return request.headers.get("x-ai-token")


def websocket_auth_protocol(websocket: WebSocket) -> tuple[str | None, str | None]:
    for protocol in websocket.headers.get("sec-websocket-protocol", "").split(","):
        offered = protocol.strip()
        if offered.startswith("ai-central-auth."):
            return offered.removeprefix("ai-central-auth."), offered
    return None, None


def require_http(request: Request) -> None:
    if not authorised(request_token(request)):
        raise HTTPException(status_code=401, detail="Token da AI Central necessário")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "public, max-age=300"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self' ws: wss:; font-src 'self'; manifest-src 'self'"
    )
    return response


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/app.css")
async def css():
    return FileResponse(STATIC / "app.css", media_type="text/css")


@app.get("/app.js")
async def javascript():
    return FileResponse(STATIC / "app.js", media_type="text/javascript")


@app.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js")
async def service_worker():
    return FileResponse(STATIC / "sw.js", media_type="text/javascript")


@app.get("/icon.svg")
async def icon():
    return FileResponse(STATIC / "icon.svg", media_type="image/svg+xml")


@app.get("/vendor/xterm.js")
async def xterm_js():
    return FileResponse(WEB_ROOT / "node_modules/@xterm/xterm/lib/xterm.js", media_type="text/javascript")


@app.get("/vendor/xterm.css")
async def xterm_css():
    return FileResponse(WEB_ROOT / "node_modules/@xterm/xterm/css/xterm.css", media_type="text/css")


@app.get("/vendor/addon-fit.js")
async def fit_js():
    return FileResponse(WEB_ROOT / "node_modules/@xterm/addon-fit/lib/addon-fit.js", media_type="text/javascript")


@app.get("/health")
async def health():
    return {"ok": True, "service": "ai-central"}


@app.get("/api/status")
async def status(request: Request):
    require_http(request)
    result = await asyncio.to_thread(run, [str(STATE)], 20)
    if result.returncode != 0:
        raise HTTPException(status_code=503, detail=result.stderr.strip() or "Monitor indisponível")
    try:
        return JSONResponse(json.loads(result.stdout))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=503, detail="Estado inválido") from exc


@app.get("/api/registry")
async def registry(request: Request):
    require_http(request)
    result = await asyncio.to_thread(run, [str(REGISTRY), "show"], 8)
    if result.returncode != 0:
        raise HTTPException(status_code=503, detail=result.stderr.strip() or "Registro indisponível")
    return JSONResponse(json.loads(result.stdout))


class LaunchRequest(BaseModel):
    mode: str
    provider: str
    name: str
    directory: str
    sessionId: str = ""
    branch: str = ""


@app.post("/api/launch")
async def launch(payload: LaunchRequest, request: Request):
    require_http(request)
    if payload.mode not in {"new", "resume", "worktree"}:
        raise HTTPException(status_code=400, detail="Modo inválido")
    if payload.provider not in {"claude", "codex"}:
        raise HTTPException(status_code=400, detail="Agente inválido")
    if not NAME_RE.fullmatch(payload.name):
        raise HTTPException(status_code=400, detail="Nome inválido")
    directory = Path(payload.directory).expanduser()
    if not directory.is_dir():
        raise HTTPException(status_code=400, detail="Pasta inexistente")
    directory = directory.resolve()

    if payload.mode == "new":
        arguments = [f"start-{payload.provider}", payload.name, str(directory)]
    elif payload.mode == "resume":
        arguments = [f"resume-{payload.provider}", payload.name, str(directory)]
        if payload.sessionId.strip():
            arguments.append(payload.sessionId.strip())
    else:
        branch = payload.branch.strip() or f"ai/{payload.name}"
        if any(character.isspace() for character in branch):
            raise HTTPException(status_code=400, detail="Branch inválida")
        arguments = [f"worktree-{payload.provider}", payload.name, str(directory), branch]

    environment = {**os.environ, "AI_HUB_DETACHED": "1"}
    result = await asyncio.to_thread(run, [str(HUB), *arguments], 90, environment)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "Não foi possível iniciar"
        raise HTTPException(status_code=409, detail=detail)
    return {"ok": True, "name": payload.name, "message": result.stdout.strip()}


@app.post("/api/restore")
async def restore(request: Request):
    require_http(request)
    result = await asyncio.to_thread(run, [str(RESTORE)], 90)
    if result.returncode != 0:
        raise HTTPException(status_code=503, detail=result.stderr.strip() or "Restauração falhou")
    return {"ok": True, "events": result.stdout.splitlines()}


def set_window_size(fd: int, cols: int, rows: int) -> None:
    cols = max(30, min(400, int(cols)))
    rows = max(10, min(200, int(rows)))
    with suppress(OSError):
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def tmux_windows() -> set[str]:
    result = run(["tmux", "list-windows", "-t", "=claude-hub", "-F", "#{window_name}"], timeout=4)
    return set(result.stdout.splitlines()) if result.returncode == 0 else set()


@app.websocket("/ws/terminal")
async def terminal_socket(websocket: WebSocket):
    token, auth_protocol = websocket_auth_protocol(websocket)
    if not authorised(token):
        await websocket.close(code=4401, reason="token required")
        return
    await websocket.accept(subprotocol=auth_protocol)
    await asyncio.to_thread(run, [str(HUB), "init"], 12)
    view_session = f"ai-web-{os.getpid()}-{secrets.token_hex(4)}"
    requested_window = websocket.query_params.get("window", "")
    create = await asyncio.to_thread(
        run, ["tmux", "new-session", "-d", "-t", "=claude-hub", "-s", view_session], 6
    )
    if create.returncode != 0:
        await websocket.send_json({"type": "error", "message": create.stderr.strip() or "tmux indisponível"})
        await websocket.close(code=1011)
        return
    if requested_window in await asyncio.to_thread(tmux_windows):
        await asyncio.to_thread(run, ["tmux", "select-window", "-t", f"{view_session}:{requested_window}"], 3)

    master, slave = pty.openpty()
    set_window_size(master, 110, 34)
    environment = {**os.environ, "TERM": "xterm-256color", "COLORTERM": "truecolor"}
    process = subprocess.Popen(
        ["tmux", "-u", "attach-session", "-t", f"={view_session}"],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=environment,
        start_new_session=True,
        close_fds=True,
    )
    os.close(slave)

    async def output_pump() -> None:
        while process.poll() is None:
            try:
                chunk = await asyncio.to_thread(os.read, master, 65536)
            except OSError:
                break
            if not chunk:
                break
            await websocket.send_bytes(chunk)

    output_task = asyncio.create_task(output_pump())
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                os.write(master, message["bytes"])
                continue
            raw = message.get("text")
            if raw is None:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                os.write(master, raw.encode())
                continue
            event_type = event.get("type")
            if event_type == "input":
                os.write(master, str(event.get("data", "")).encode())
            elif event_type == "resize":
                set_window_size(master, event.get("cols", 110), event.get("rows", 34))
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGWINCH)
            elif event_type == "select":
                name = str(event.get("window", ""))
                if name in await asyncio.to_thread(tmux_windows):
                    await asyncio.to_thread(run, ["tmux", "select-window", "-t", f"{view_session}:{name}"], 3)
    except (WebSocketDisconnect, ConnectionError, OSError):
        pass
    finally:
        output_task.cancel()
        with suppress(asyncio.CancelledError):
            await output_task
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)
        with suppress(OSError):
            os.close(master)
        await asyncio.to_thread(run, ["tmux", "kill-session", "-t", f"={view_session}"], 4)


def tailscale_ipv4() -> str:
    result = run(["tailscale", "ip", "-4"], timeout=5)
    return result.stdout.strip().splitlines()[0] if result.returncode == 0 and result.stdout.strip() else "127.0.0.1"


def public_base_url(port: int) -> str:
    served = run(["tailscale", "serve", "status", "--json"], timeout=5)
    if served.returncode == 0:
        try:
            if json.loads(served.stdout or "{}"):
                status = run(["tailscale", "status", "--json"], timeout=5)
                dns_name = str((json.loads(status.stdout).get("Self") or {}).get("DNSName") or "").rstrip(".")
                if dns_name:
                    return f"https://{dns_name}"
        except (json.JSONDecodeError, AttributeError):
            pass
    return f"http://{tailscale_ipv4()}:{port}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--print-url", action="store_true")
    args = parser.parse_args()
    if args.print_url:
        print(f"{public_base_url(args.port)}/#token={access_token()}")
        return 0
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info", access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
