@echo off
rem Kept for older instructions: same as "start.bat start".
call "%~dp0start.bat" start %*
if errorlevel 1 pause
