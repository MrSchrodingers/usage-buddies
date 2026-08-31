# ═══════════════════════════════════════════════════
# Claude Usage Monitor - Windows Uninstaller
# Removes ONLY components installed by install.ps1
# ═══════════════════════════════════════════════════

$ErrorActionPreference = "SilentlyContinue"
$BinDir = "$env:LOCALAPPDATA\ClaudeUsageMonitor"
$ClaudeDir = "$env:USERPROFILE\.claude"
$Removed = 0

Write-Host ""
Write-Host "=======================================" -ForegroundColor White
Write-Host "  Claude Usage Monitor - Uninstaller   " -ForegroundColor White
Write-Host "=======================================" -ForegroundColor White
Write-Host ""

# ── Kill running tray app (exact process name only) ──
$proc = Get-Process -Name "claude-usage-tray" -ErrorAction SilentlyContinue
if ($proc) {
    $proc | Stop-Process -Force
    Write-Host "  + Stopped running tray app" -ForegroundColor Green
    $Removed++
}

# ── Remove scheduled task (only our specific task name) ──
$task = Get-ScheduledTask -TaskName "ClaudeUsageCollector" -ErrorAction SilentlyContinue
if ($task) {
    Unregister-ScheduledTask -TaskName "ClaudeUsageCollector" -Confirm:$false
    Write-Host "  + Removed scheduled task 'ClaudeUsageCollector'" -ForegroundColor Green
    $Removed++
}

# ── Remove startup shortcut (verify it's ours before deleting) ──
# Both legacy names from install.ps1 ("Monitor") and install-windows.ps1 ("Widget")
$startupDir = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
foreach ($name in @("Claude Usage Monitor.lnk", "Claude Usage Widget.lnk")) {
    $shortcutPath = "$startupDir\$name"
    if (Test-Path $shortcutPath) {
        $shell = New-Object -ComObject WScript.Shell
        $link = $shell.CreateShortcut($shortcutPath)
        $isOurs = $link.TargetPath -like "*claude-usage-tray*" -or `
                  ($link.TargetPath -like "*python*" -and ($link.Arguments -like "*claude-usage*" -or $link.Arguments -like "*\widget\main.py*"))
        if ($isOurs) {
            Remove-Item $shortcutPath -Force
            Write-Host "  + Removed startup shortcut ($name)" -ForegroundColor Green
            $Removed++
        }
    }
}

# ── Remove our install directory (only our specific directory) ──
if (Test-Path $BinDir) {
    # Verify it contains our files before deleting
    if ((Test-Path "$BinDir\claude-usage-collector.py") -or (Test-Path "$BinDir\claude-usage-tray.exe")) {
        Remove-Item $BinDir -Recurse -Force
        Write-Host "  + Removed $BinDir" -ForegroundColor Green
        $Removed++
    }
}

# ── Remove only our widget data files (never touch other .claude files) ──
# NOTE: stats-cache.json belongs to Claude Code itself - never delete it.
$dataFiles = @("widget-data.json", "widget-config.json", "widget-status-prev.json")
$dataRemoved = 0
foreach ($f in $dataFiles) {
    $p = "$ClaudeDir\$f"
    if (Test-Path $p) {
        Remove-Item $p -Force
        $dataRemoved++
    }
}
if ($dataRemoved -gt 0) {
    Write-Host "  + Removed $dataRemoved widget data files" -ForegroundColor Green
    $Removed++
}

# ── Remove temp cookie files (only our specific pattern) ──
$tempDir = [System.IO.Path]::GetTempPath()
Get-ChildItem -Path $tempDir -Filter "claude_chrome_*.sqlite*" -ErrorAction SilentlyContinue | Remove-Item -Force
Get-ChildItem -Path $tempDir -Filter "claude_ff_*.sqlite*" -ErrorAction SilentlyContinue | Remove-Item -Force

Write-Host ""
Write-Host "  Uninstall complete. ($Removed components removed)" -ForegroundColor Green
Write-Host ""
Read-Host "Press Enter to close"
