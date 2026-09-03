#!/usr/bin/env python3
"""KDE control center for the shared Claude Code/Codex tmux hub."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

HUB = str(Path.home() / ".local/bin/claude-hub")
STATE_HELPER = str(Path.home() / ".local/bin/ai-hub-state.py")
NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def run(command: list[str], timeout: float = 12) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)


def read_snapshot() -> dict:
    result = run([STATE_HELPER], timeout=15)
    if result.returncode != 0:
        init = run([HUB, "init"])
        if init.returncode != 0:
            raise RuntimeError(init.stderr.strip() or "Não foi possível iniciar o hub")
        result = run([STATE_HELPER], timeout=15)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Hub tmux indisponível")
    try:
        snapshot = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("O monitor retornou um estado inválido") from exc
    snapshot["windows"] = snapshot.get("sessions", [])
    for window in snapshot["windows"]:
        window["session_id"] = window.get("sessionId", "")
    return snapshot


class WorkerSignals(QObject):
    ready = Signal(dict)
    failed = Signal(str)


class SnapshotWorker(QRunnable):
    def __init__(self) -> None:
        super().__init__()
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            self.signals.ready.emit(read_snapshot())
        except Exception as exc:  # UI boundary: show a useful error instead of crashing.
            self.signals.failed.emit(str(exc))


class SessionDialog(QDialog):
    def __init__(self, parent: "CentralWindow", mode: str, provider: str = "claude") -> None:
        super().__init__(parent)
        self.central = parent
        self.mode = mode
        self.last_suggestion = ""
        titles = {
            "new": "Nova sessão sincronizada",
            "resume": "Retomar conversa por ID",
            "worktree": "Novo worktree isolado",
        }
        self.setWindowTitle(titles[mode])
        self.setMinimumWidth(620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(14)

        title = QLabel(titles[mode])
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        descriptions = {
            "new": "Cria um agente no hub, visível ao vivo no PC e no celular.",
            "resume": "Retoma uma conversa antiga dentro de uma nova janela sincronizada. Deixe o ID vazio para abrir o seletor do agente.",
            "worktree": "Cria uma cópia Git isolada para vários agentes trabalharem em paralelo no mesmo repositório.",
        }
        description = QLabel(descriptions[mode])
        description.setWordWrap(True)
        description.setObjectName("muted")
        layout.addWidget(description)

        layout.addWidget(QLabel("Agente"))
        self.provider = QComboBox()
        self.provider.addItem("Claude Code", "claude")
        self.provider.addItem("OpenAI Codex", "codex")
        self.provider.setCurrentIndex(1 if provider == "codex" else 0)
        layout.addWidget(self.provider)

        self.permission = QLabel("")
        self.permission.setObjectName("permission")
        layout.addWidget(self.permission)
        self.provider.currentIndexChanged.connect(self.update_provider_copy)
        self.update_provider_copy()

        self.name = self.add_field(layout, "Nome curto da sessão", "ex.: auditoria-api")
        path_label = "Repositório Git" if mode == "worktree" else "Pasta de trabalho"
        path_row = QHBoxLayout()
        self.path = QLineEdit()
        self.path.setPlaceholderText("Selecione a pasta")
        browse = QPushButton("Escolher…")
        browse.setIcon(QIcon.fromTheme("folder-open"))
        browse.clicked.connect(self.choose_directory)
        path_row.addWidget(self.path, 1)
        path_row.addWidget(browse)
        layout.addWidget(QLabel(path_label))
        layout.addLayout(path_row)

        self.session_id: QLineEdit | None = None
        self.branch: QLineEdit | None = None
        if mode == "resume":
            self.session_id = self.add_field(layout, "ID da conversa (opcional)", "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        if mode == "worktree":
            self.branch = self.add_field(layout, "Branch", "ai/nome-da-sessao")

        self.path.textChanged.connect(self.suggest_name)
        self.name.textChanged.connect(self.suggest_branch)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("Criar e abrir")
        buttons.button(QDialogButtonBox.Ok).setIcon(QIcon.fromTheme("system-run"))
        buttons.accepted.connect(self.submit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def add_field(layout: QVBoxLayout, label: str, placeholder: str) -> QLineEdit:
        layout.addWidget(QLabel(label))
        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        layout.addWidget(field)
        return field

    def update_provider_copy(self) -> None:
        if self.provider.currentData() == "codex":
            self.permission.setText("⚡ Controle pleno: bypass de aprovações e sandbox do Codex")
        else:
            self.permission.setText("⚡ Controle pleno: permission-mode bypassPermissions do Claude")

    def choose_directory(self) -> None:
        start = self.path.text().strip() or str(Path.home())
        directory = QFileDialog.getExistingDirectory(self, "Selecionar pasta", start)
        if directory:
            self.path.setText(directory)

    def suggest_name(self, directory: str) -> None:
        current = self.name.text().strip()
        if current and current != self.last_suggestion:
            return
        base = Path(directory).name.lower() if directory else "sessao"
        base = re.sub(r"[^a-z0-9_.-]+", "-", base).strip("-.") or "sessao"
        self.last_suggestion = f"{base}-{time.strftime('%H%M')}"
        self.name.setText(self.last_suggestion)

    def suggest_branch(self, name: str) -> None:
        if self.branch is not None and (not self.branch.text() or self.branch.text().startswith(("claude/", "codex/", "ai/"))):
            self.branch.setText(f"ai/{name.strip()}")

    def submit(self) -> None:
        name = self.name.text().strip()
        directory_text = self.path.text().strip()
        if not NAME_RE.fullmatch(name):
            QMessageBox.warning(self, "Nome inválido", "Use somente letras, números, ponto, sublinhado e hífen.")
            return
        directory = Path(directory_text).expanduser()
        if not directory.is_dir():
            QMessageBox.warning(self, "Pasta inválida", "Selecione uma pasta existente.")
            return
        directory = directory.resolve()
        provider = str(self.provider.currentData())
        provider_name = "Claude Code" if provider == "claude" else "Codex"

        if self.mode != "worktree":
            existing = self.central.live_window_for_directory(str(directory))
            if existing:
                answer = QMessageBox.question(
                    self,
                    "Sessão já sincronizada",
                    f"{existing['name']} já controla esta pasta.\n\nAbrir a sessão existente ao vivo?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if answer == QMessageBox.Yes:
                    self.central.open_window(existing["name"])
                    self.accept()
                return

        if self.mode == "new":
            arguments = [f"start-{provider}", name, str(directory)]
        elif self.mode == "resume":
            arguments = [f"resume-{provider}", name, str(directory)]
            session_id = self.session_id.text().strip() if self.session_id else ""
            if session_id:
                arguments.append(session_id)
        else:
            branch = self.branch.text().strip() if self.branch else ""
            if not branch or any(character.isspace() for character in branch):
                QMessageBox.warning(self, "Branch inválida", "Informe uma branch Git sem espaços.")
                return
            arguments = [f"worktree-{provider}", name, str(directory), branch]

        if self.central.launch_console(arguments, f"{provider_name} · {name}"):
            self.accept()
            QTimer.singleShot(1500, self.central.refresh)


class CentralWindow(QMainWindow):
    def __init__(self, startup_mode: str = "continue", startup_provider: str = "claude") -> None:
        super().__init__()
        self.snapshot: dict = {"windows": [], "clients": 0, "mobile": 0}
        self.loading = False
        self.worker: SnapshotWorker | None = None
        self.pool = QThreadPool.globalInstance()
        self.setWindowTitle("AI Central")
        self.setWindowIcon(QIcon.fromTheme("utilities-terminal"))
        self.resize(1080, 780)
        self.setMinimumSize(820, 600)

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(30, 26, 30, 24)
        outer.setSpacing(20)

        header = QHBoxLayout()
        brand = QVBoxLayout()
        title_row = QHBoxLayout()
        logo = QLabel("AI")
        logo.setObjectName("logo")
        title = QLabel("AI Central")
        title.setObjectName("title")
        title_row.addWidget(logo)
        title_row.addWidget(title)
        title_row.addStretch()
        brand.addLayout(title_row)
        subtitle = QLabel("Claude Code + Codex  ·  PC ↔ celular")
        subtitle.setObjectName("subtitle")
        brand.addWidget(subtitle)
        header.addLayout(brand)
        header.addStretch()
        self.summary = QLabel("Carregando estado ao vivo…")
        self.summary.setObjectName("summary")
        header.addWidget(self.summary, 0, Qt.AlignTop)
        outer.addLayout(header)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(self.action_button("Nova sessão", "list-add", "primary", lambda: self.show_dialog("new")))
        actions.addWidget(self.action_button("Retomar por ID", "document-open-recent", "secondary", lambda: self.show_dialog("resume")))
        actions.addWidget(self.action_button("Worktree isolado", "vcs-branch", "secondary", lambda: self.show_dialog("worktree")))
        actions.addWidget(self.action_button("Terminal central", "utilities-terminal", "secondary", self.open_central_terminal))
        actions.addStretch()
        self.refresh_button = self.action_button("Atualizar", "view-refresh", "ghost", self.refresh)
        actions.addWidget(self.refresh_button)
        outer.addLayout(actions)

        notice = QLabel("CONTROLE PLENO  ·  Claude e Codex iniciam sem prompts de permissão. Para vários agentes no mesmo repositório, use um Worktree isolado por agente.")
        notice.setObjectName("notice")
        notice.setWordWrap(True)
        outer.addWidget(notice)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 8, 0)
        self.content_layout.setSpacing(18)
        scroll.setWidget(self.content)
        outer.addWidget(scroll, 1)

        self.footer = QLabel("")
        self.footer.setObjectName("footer")
        outer.addWidget(self.footer)

        self.apply_style()
        self.refresh()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(8_000)
        if startup_mode in {"new", "resume", "worktree"}:
            QTimer.singleShot(250, lambda: self.show_dialog(startup_mode, startup_provider))

    @staticmethod
    def action_button(text: str, icon: str, style: str, callback) -> QPushButton:
        button = QPushButton(text)
        button.setIcon(QIcon.fromTheme(icon))
        button.setIconSize(QSize(18, 18))
        button.setProperty("kind", style)
        button.clicked.connect(callback)
        button.setCursor(Qt.PointingHandCursor)
        return button

    def apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QDialog, QWidget { background: #0b1220; color: #e5edf8; font-family: Inter, Noto Sans, sans-serif; font-size: 14px; }
            QLabel { background: transparent; }
            QLabel#logo { color: #071018; background: #67e8f9; border-radius: 10px; font-size: 23px; font-weight: 900; padding: 7px 10px; }
            QLabel#title { font-size: 28px; font-weight: 800; color: #f8fafc; padding-left: 8px; }
            QLabel#subtitle, QLabel#muted, QLabel#footer { color: #91a4bd; }
            QLabel#summary { color: #b8c7da; background: #111c2e; border: 1px solid #21324a; border-radius: 12px; padding: 10px 14px; }
            QLabel#notice { color: #fcd34d; background: #211c10; border: 1px solid #51421c; border-radius: 10px; padding: 10px 13px; font-size: 12px; font-weight: 650; }
            QLabel#alert { color: #fde68a; background: #261e0f; border: 1px solid #684d16; border-radius: 10px; padding: 10px 13px; font-size: 12px; font-weight: 650; }
            QLabel#section { color: #f8fafc; font-size: 17px; font-weight: 750; padding-top: 3px; }
            QLabel#cardTitle { color: #f8fafc; font-size: 17px; font-weight: 750; }
            QLabel#health { color: #b8c7da; background: #18263b; border-radius: 7px; padding: 4px 8px; font-size: 11px; font-weight: 650; }
            QLabel#usageLabel { color: #aebed1; min-width: 58px; font-size: 12px; }
            QLabel#usageDetail { color: #7890aa; font-size: 11px; }
            QLabel#path { color: #91a4bd; font-family: monospace; font-size: 12px; }
            QLabel#sessionId { color: #60738d; font-family: monospace; font-size: 11px; }
            QLabel#branch { color: #7dd3fc; font-size: 11px; font-weight: 650; }
            QLabel#providerBadge { border-radius: 6px; padding: 3px 7px; font-size: 10px; font-weight: 800; }
            QLabel#providerBadge[provider="claude"] { color: #fed7aa; background: #40251d; border: 1px solid #7c3f2c; }
            QLabel#providerBadge[provider="codex"] { color: #a7f3d0; background: #10352d; border: 1px solid #176550; }
            QLabel#providerBadge[provider="shell"] { color: #cbd5e1; background: #243247; border: 1px solid #40516a; }
            QLabel#dialogTitle { font-size: 22px; font-weight: 800; color: #f8fafc; }
            QLabel#permission { color: #fcd34d; background: #211c10; border-radius: 8px; padding: 8px 10px; }
            QFrame#card { background: #111c2e; border: 1px solid #21324a; border-radius: 14px; }
            QFrame#card:hover { border-color: #3b6684; background: #132238; }
            QFrame#usageCard { background: #101b2c; border: 1px solid #21324a; border-radius: 14px; }
            QPushButton { min-height: 38px; border-radius: 9px; padding: 0 14px; font-weight: 650; }
            QPushButton[kind="primary"] { color: #061019; background: #67e8f9; border: 1px solid #67e8f9; }
            QPushButton[kind="primary"]:hover { background: #a5f3fc; }
            QPushButton[kind="secondary"] { color: #dce9f8; background: #17243a; border: 1px solid #2a405e; }
            QPushButton[kind="secondary"]:hover { background: #203451; border-color: #4d739d; }
            QPushButton[kind="ghost"] { color: #9fb2c9; background: transparent; border: 1px solid #263a55; }
            QPushButton[kind="ghost"]:hover { color: #f8fafc; background: #17243a; }
            QLineEdit, QComboBox { min-height: 38px; color: #f8fafc; background: #0e1828; border: 1px solid #2a405e; border-radius: 8px; padding: 0 10px; selection-background-color: #29627d; }
            QLineEdit:focus, QComboBox:focus { border-color: #67e8f9; }
            QComboBox::drop-down { border: 0; width: 28px; }
            QComboBox QAbstractItemView { color: #f8fafc; background: #111c2e; border: 1px solid #2a405e; selection-background-color: #244761; }
            QProgressBar { min-height: 15px; max-height: 15px; color: #e5edf8; background: #08101d; border: 1px solid #263a55; border-radius: 7px; text-align: center; font-size: 9px; font-weight: 750; }
            QProgressBar::chunk { background: #d97757; border-radius: 6px; }
            QProgressBar[provider="codex"]::chunk { background: #10a37f; }
            QScrollArea { background: transparent; }
            QScrollBar:vertical { background: #0b1220; width: 10px; margin: 2px; }
            QScrollBar::handle:vertical { background: #30445f; min-height: 30px; border-radius: 5px; }
            """
        )

    def refresh(self) -> None:
        if self.loading:
            return
        self.loading = True
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("Atualizando…")
        self.worker = SnapshotWorker()
        self.worker.signals.ready.connect(self.render_snapshot)
        self.worker.signals.failed.connect(self.render_error)
        self.pool.start(self.worker)

    def render_error(self, message: str) -> None:
        self.loading = False
        self.refresh_button.setEnabled(True)
        self.refresh_button.setText("Atualizar")
        self.summary.setText("Hub indisponível")
        self.footer.setText(message)

    def render_snapshot(self, snapshot: dict) -> None:
        self.snapshot = snapshot
        self.loading = False
        self.refresh_button.setEnabled(True)
        self.refresh_button.setText("Atualizar")
        live = [window for window in snapshot["windows"] if window["live"]]
        external = snapshot.get("externalSessions", [])
        claude_live = sum(window.get("provider") == "claude" for window in live)
        codex_live = sum(window.get("provider") == "codex" for window in live)
        self.summary.setText(
            f"● {claude_live} Claude  ·  {codex_live} Codex  ·  {len(external)} fora do hub  ·  celular {'conectado' if snapshot['mobile'] else 'desconectado'}"
        )
        self.footer.setText(f"Atualizado às {snapshot['updated']}  ·  MENU no celular  ·  Ctrl+B W em qualquer terminal")

        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.add_usage(snapshot.get("usage", {}), snapshot.get("alerts", []))

        ai_windows = [window for window in snapshot["windows"] if window.get("provider") in {"claude", "codex"}]
        grouped: dict[str, list[dict]] = {}
        for window in ai_windows:
            repository = window.get("repository") or {}
            group = repository.get("group") or Path(window.get("directory", "")).name or "Outras sessões"
            grouped.setdefault(group, []).append(window)
        for group, windows in grouped.items():
            providers = {window.get("provider") for window in windows}
            label = "Claude + Codex" if len(providers) > 1 else ("Claude Code" if "claude" in providers else "Codex")
            self.add_section(f"{group}  ·  {label}", windows)

        if external:
            self.add_section("Ativos fora do hub  ·  preservados até finalizar", external)

        shell_windows = [window for window in snapshot["windows"] if window.get("provider") == "shell"]
        self.add_section("Shells compartilhados", shell_windows)
        self.content_layout.addStretch()

    @staticmethod
    def usage_percent(value) -> int:
        try:
            return max(0, min(100, round(float(value))))
        except (TypeError, ValueError):
            return 0

    def add_usage(self, usage: dict, alerts: list[dict]) -> None:
        section = QLabel("Visão geral  ·  consumo e saúde")
        section.setObjectName("section")
        self.content_layout.addWidget(section)

        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        providers = [("claude", "Claude Code"), ("codex", "OpenAI Codex")]
        columns = 1 if self.width() < 980 else 2
        for position, (key, label) in enumerate(providers):
            grid.addWidget(self.make_usage_card(label, usage.get(key, {}), key), position // columns, position % columns)
        self.content_layout.addWidget(grid_widget)

        if alerts:
            messages = "   ·   ".join(str(alert.get("message", "")) for alert in alerts if alert.get("message"))
            alert = QLabel(f"ATENÇÃO  ·  {messages}")
            alert.setObjectName("alert")
            alert.setWordWrap(True)
            self.content_layout.addWidget(alert)

    def make_usage_card(self, label: str, item: dict, provider: str) -> QFrame:
        card = QFrame()
        card.setObjectName("usageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(9)

        top = QHBoxLayout()
        title = QLabel(label)
        title.setObjectName("cardTitle")
        health = QLabel(str(item.get("health") or "Dados indisponíveis"))
        health.setObjectName("health")
        top.addWidget(title)
        top.addStretch()
        top.addWidget(health)
        layout.addLayout(top)

        plan = item.get("plan") or "—"
        source = str(item.get("source") or "local").upper()
        meta = QLabel(f"Plano {plan}  ·  fonte {source}")
        meta.setObjectName("muted")
        layout.addWidget(meta)

        for title_text, value in (("Sessão", item.get("sessionPercent")), ("Semana", item.get("weeklyPercent"))):
            row = QHBoxLayout()
            label_widget = QLabel(title_text)
            label_widget.setObjectName("usageLabel")
            progress = QProgressBar()
            percent = self.usage_percent(value)
            progress.setValue(percent)
            progress.setFormat(f"{percent}%")
            progress.setProperty("provider", provider)
            row.addWidget(label_widget)
            row.addWidget(progress, 1)
            layout.addLayout(row)

        errors = int(item.get("errors") or 0)
        if provider == "claude":
            burn = int(item.get("burnPerHour") or 0)
            latency = float(item.get("latency") or 0)
            detail = f"{errors} erros  ·  {burn:,} tokens/h  ·  {latency:.1f}s latência".replace(",", ".")
        else:
            tokens = int(item.get("currentThreadTokens") or 0)
            detail = f"{errors} erros de API  ·  {tokens:,} tokens nesta conversa".replace(",", ".")
        footer = QLabel(detail)
        footer.setObjectName("usageDetail")
        layout.addWidget(footer)
        return card

    def add_section(self, title: str, windows: list[dict]) -> None:
        section = QLabel(f"{title}   {len(windows)}")
        section.setObjectName("section")
        self.content_layout.addWidget(section)
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        columns = 1 if self.width() < 980 else 2
        for position, window in enumerate(windows):
            grid.addWidget(self.make_card(window), position // columns, position % columns)
        if not windows:
            empty = QLabel("Nenhuma sessão nesta seção")
            empty.setObjectName("muted")
            grid.addWidget(empty, 0, 0)
        self.content_layout.addWidget(grid_widget)

    def make_card(self, window: dict) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(17, 15, 17, 15)
        layout.setSpacing(8)

        top = QHBoxLayout()
        title = QLabel(f"{window['index']}  {window['name']}")
        title.setObjectName("cardTitle")
        provider = window.get("provider", "shell")
        provider_label = {"claude": "CLAUDE", "codex": "CODEX", "shell": "SHELL"}.get(provider, provider.upper())
        provider_badge = QLabel(provider_label)
        provider_badge.setProperty("provider", provider)
        provider_badge.setObjectName("providerBadge")
        status = QLabel(f"{window.get('marker', '●')}  {window['status']}")
        status_color = window["color"].lstrip("#")
        status.setStyleSheet(
            f"color: {window['color']}; background: #18{status_color}; border: 1px solid #55{status_color}; border-radius: 8px; padding: 4px 8px; font-size: 11px; font-weight: 750;"
        )
        top.addWidget(title)
        top.addWidget(provider_badge)
        top.addStretch()
        top.addWidget(status)
        layout.addLayout(top)

        detail = QLabel(window["detail"])
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        layout.addWidget(detail)
        path = QLabel(window["directory"])
        path.setObjectName("path")
        path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(path)
        repository = window.get("repository") or {}
        branch = repository.get("branch")
        if branch:
            worktree = "  ·  WORKTREE ISOLADO" if repository.get("isWorktree") else ""
            branch_label = QLabel(f"BRANCH  {branch}{worktree}")
            branch_label.setObjectName("branch")
            layout.addWidget(branch_label)
        if window["session_id"]:
            session = QLabel(f"ID  {window['session_id']}")
            session.setObjectName("sessionId")
            session.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(session)

        if window.get("external"):
            button_text = "Fora do hub · não duplicar"
            open_button = self.action_button(button_text, "dialog-warning", "ghost", lambda: None)
            open_button.setEnabled(False)
        else:
            button_text = "Continuar ao vivo" if window["live"] else "Abrir terminal"
            open_button = self.action_button(button_text, "window-new", "secondary", lambda _=False, name=window["name"]: self.open_window(name))
        layout.addWidget(open_button, 0, Qt.AlignRight)
        return card

    def show_dialog(self, mode: str, provider: str = "claude") -> None:
        SessionDialog(self, mode, provider).exec()

    def open_window(self, name: str) -> None:
        result = run([HUB, "continue", name])
        if result.returncode != 0:
            QMessageBox.critical(self, "Não foi possível abrir", result.stderr.strip() or result.stdout.strip())

    def open_central_terminal(self) -> None:
        first_live = next((window for window in self.snapshot.get("windows", []) if window["live"]), None)
        target = first_live["name"] if first_live else "amaral-hub"
        self.launch_console(["attach", target], "AI Central")

    def live_window_for_directory(self, directory: str) -> dict | None:
        for window in self.snapshot.get("windows", []):
            try:
                same = Path(window["directory"]).resolve() == Path(directory).resolve()
            except OSError:
                same = window["directory"] == directory
            if same and window["live"] and not window.get("external"):
                return window
        return None

    def launch_console(self, arguments: list[str], title: str) -> bool:
        unit = f"claude-central-{int(time.time())}-{os.getpid()}"
        command = [
            "systemd-run",
            "--user",
            f"--unit={unit}",
            "--collect",
            "--service-type=exec",
            "/usr/bin/konsole",
            "--separate",
            "-p",
            f"tabtitle={title}",
            "-e",
            HUB,
            *arguments,
        ]
        result = run(command)
        if result.returncode != 0:
            QMessageBox.critical(self, "Não foi possível abrir o terminal", result.stderr.strip() or result.stdout.strip())
            return False
        return True


def main() -> int:
    startup_mode = sys.argv[1] if len(sys.argv) > 1 else "continue"
    startup_provider = sys.argv[2] if len(sys.argv) > 2 else "claude"
    if startup_mode not in {"continue", "new", "resume", "worktree"}:
        startup_mode = "continue"
    if startup_provider not in {"claude", "codex"}:
        startup_provider = "claude"
    app = QApplication(sys.argv)
    app.setApplicationName("AI Central")
    app.setDesktopFileName("claude-hub")
    app.setStyle("Fusion")
    palette = app.palette()
    palette.setColor(QPalette.Window, QColor("#0b1220"))
    palette.setColor(QPalette.WindowText, QColor("#e5edf8"))
    app.setPalette(palette)
    window = CentralWindow(startup_mode, startup_provider)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
    QProgressBar,
