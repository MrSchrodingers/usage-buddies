@echo off
:: Check for admin rights (Task Scheduler removal may need it)
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting administrator rights...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)
echo Starting Claude Usage Monitor uninstaller...
powershell -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1"
