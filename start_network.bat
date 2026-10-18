@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Fireworks CRM (Wi-Fi network)
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3 is required. Please install Python 3.10+ and rerun.
  pause
  exit /b 1
)

set "HOST=0.0.0.0"
if not defined PORT set "PORT=8000"

rem A new database needs an admin password before it can be shared on the network.
if exist "data\fireworks.db" goto have_db
if defined FIREWORKS_ADMIN_PASSWORD goto have_db
echo No database yet. Choose the password for the "admin" account.
echo It must be at least 12 characters. Typing is hidden.
echo.
:ask_password
set "P1="
set "P2="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$s=Read-Host 'Admin password' -AsSecureString; [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))"`) do set "P1=%%P"
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$s=Read-Host 'Repeat password' -AsSecureString; [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))"`) do set "P2=%%P"
setlocal EnableDelayedExpansion
set "MATCH=0"
if "!P1!"=="!P2!" if not "!P1!"=="" set "MATCH=1"
set "LEN=0"
if "!P1:~11,1!" neq "" set "LEN=12"
for %%M in (!MATCH!!LEN!) do endlocal & set "CHECK=%%M"
if not "%CHECK%"=="112" (
  echo.
  echo Passwords did not match or are shorter than 12 characters. Try again.
  echo.
  goto ask_password
)
set "FIREWORKS_ADMIN_PASSWORD=%P1%"
set "P1="
set "P2="
echo.

:have_db
echo ============================================================
echo  Fireworks CRM - shared on your Wi-Fi network
echo ============================================================
echo  On THIS computer open:   http://localhost:%PORT%
echo  On other devices open one of these addresses:
for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | ForEach-Object { $_.IPAddress }"`) do echo      http://%%A:%PORT%
echo.
echo  - Devices must be on the same Wi-Fi as this computer.
echo  - If Windows Firewall asks, allow Python on PRIVATE networks only.
echo  - Keep this window open. Closing it stops the CRM.
echo  - Use only your own password-protected Wi-Fi, never public Wi-Fi.
echo ============================================================
echo.

start "" cmd /c "timeout /t 3 >nul & start http://localhost:%PORT%"
python server.py
echo.
echo The CRM has stopped.
pause
