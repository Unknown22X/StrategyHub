@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-StrategyHub-Paper-Demo.ps1"
if errorlevel 1 (
  echo.
  echo StrategyHub Paper demo failed to start. See PAPER_DEMO_STATUS.md.
  pause
)
