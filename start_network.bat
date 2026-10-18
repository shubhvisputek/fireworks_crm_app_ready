@echo off
rem Kept for older instructions: same as "start.bat start --network" (share on the shop Wi-Fi).
call "%~dp0start.bat" start --network %*
if errorlevel 1 pause
