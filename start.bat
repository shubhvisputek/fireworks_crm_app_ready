@echo off
rem Fireworks CRM launcher for Windows. Double-click for the menu, or run with options,
rem e.g.  start.bat start --network   or   start.bat help
setlocal
cd /d "%~dp0"
set "FIREWORKS_LAUNCHER=start.bat"
set "PY="
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul && set "PY=python"
if not defined PY (
  echo Fireworks CRM needs Python 3.10 or newer.
  echo Install it from https://www.python.org/downloads/  ^(tick "Add python.exe to PATH"^)
  echo or run:  winget install Python.Python.3.12
  pause
  exit /b 1
)
%PY% fireworks.py %*
set "CODE=%ERRORLEVEL%"
rem Keep the window open when started by double-click, so messages can be read.
if "%~1"=="" pause
exit /b %CODE%
