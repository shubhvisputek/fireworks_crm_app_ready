@echo off
setlocal
cd /d %~dp0
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3 is required. Please install Python 3.10+ and rerun.
  pause
  exit /b 1
)
start "Fireworks CRM" cmd /k "python server.py"
timeout /t 2 >nul
start http://localhost:8000
