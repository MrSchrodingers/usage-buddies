# =====================================================
# Claude Usage Monitor - Windows AppBar uninstaller
# Removes only artifacts created by install-windows.ps1.
# =====================================================

$ErrorActionPreference = "SilentlyContinue"
$BinDir    = "$env:LOCALAPPDATA\ClaudeUsageMonitor"
$ClaudeDir = "$env:USERPROFILE\.claude"
$Removed   = 0

Write-Host ""
Write-Host "=========================================" -ForegroundColor White
Write-Host "  Claude Usage Monitor - Uninstall       " -ForegroundColor White
Write-Host "=========================================" -ForegroundColor White
Write-Host ""

# Stop any running widget (pythonw running main.py)
$mainPy = "$BinDir\widget\main.py"
Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" `
  | Where-Object { $_.CommandLine -and $_.CommandLine -like "*$mainPy*" } `
  | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force
        Write-Host "  + Stopped widget process PID $($_.ProcessId)" -ForegroundColor Green
        $Removed++
    }

# Scheduled task
$task = Get-ScheduledTask -TaskName "ClaudeUsageCollector" -ErrorAction SilentlyContinue
if ($task) {
    Unregister-ScheduledTask -TaskName "ClaudeUsageCollector" -Confirm:$false
    Write-Host "  + Removed scheduled task 'ClaudeUsageCollector'" -ForegroundColor Green
    $Removed++
}

# Startup shortcut (verify before delete)
$shortcutPath = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Claude Usage Widget.lnk"
if (Test-Path $shortcutPath) {
    $shell = New-Object -ComObject WScript.Shell
    $link  = $shell.CreateShortcut($shortcutPath)
    if ($link.Arguments -like "*main.py*" -and $link.WorkingDirectory -like "*ClaudeUsageMonitor*") {
        Remove-Item $shortcutPath -Force
        Write-Host "  + Removed startup shortcut" -ForegroundColor Green
        $Removed++
    }
}

# Install dir (verify it is ours)
if (Test-Path $BinDir) {
    $marker = "$BinDir\widget\main.py"
    if ((Test-Path "$BinDir\claude-usage-collector.py") -or (Test-Path $marker)) {
        Remove-Item $BinDir -Recurse -Force
        Write-Host "  + Removed $BinDir" -ForegroundColor Green
        $Removed++
    }
}

# Widget data files only (never touch other ~/.claude files)
# NOTE: stats-cache.json belongs to Claude Code itself - never delete it.
$dataFiles = @(
    "widget-data.json", "widget-config.json",
    "widget-status-prev.json"
)
$dataRemoved = 0
foreach ($f in $dataFiles) {
    $p = "$ClaudeDir\$f"
    if (Test-Path $p) { Remove-Item $p -Force; $dataRemoved++ }
}
if ($dataRemoved -gt 0) {
    Write-Host "  + Removed $dataRemoved widget data file(s)" -ForegroundColor Green
    $Removed++
}

# Collector temp artifacts
$tempDir = [System.IO.Path]::GetTempPath()
Get-ChildItem $tempDir -Filter "claude_chrome_*.sqlite*" -EA SilentlyContinue | Remove-Item -Force
Get-ChildItem $tempDir -Filter "claude_ff_*.sqlite*"     -EA SilentlyContinue | Remove-Item -Force

Write-Host ""
Write-Host "  Uninstall complete. ($Removed components removed)" -ForegroundColor Green
Write-Host ""
Read-Host "Press Enter to close"
