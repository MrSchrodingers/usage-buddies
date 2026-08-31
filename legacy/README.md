# Legacy uninstallers

These scripts remove installs made **before** the project was renamed from
`claude-usage-widget` to `usage-buddies`, and before the Windows widget was
rebuilt in Tauri (PR #8, which deleted the PySide6 build and its installers).

They reference the old artifact names on purpose — `claude-usage-collector.py`,
`claude-usage-tray`, `org.kde.plasma.claudeusage`, the `Claude Usage Monitor`
scheduled task. **Do not rename anything in this directory.** The whole point is
that it still knows the old names.

| Script | Removes |
|---|---|
| `uninstall.sh` | Linux: collector, systemd units, plasmoid, tray binary, autostart entry |
| `uninstall.ps1` / `uninstall.bat` | Windows: collector, scheduled task, Tauri tray, Startup shortcut |
| `uninstall-windows.ps1` | Windows: the PySide6 AppBar widget and its Chrome cookie-bridge extension |

`install.sh` detects an old install and points here before installing. To run one
by hand:

```bash
bash legacy/uninstall.sh
```

Your data in `~/.claude/` (`widget-data.json`, `widget-config.json`) is not
touched by the rename — the new install reads the same files.

Once you have no machines left on the old names, this directory can go.
