@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch.ps1" -Mode Check
echo Exit code: %errorlevel%
pause
