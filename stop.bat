@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" jumpbot.py stop
) else (
    py -3 jumpbot.py stop
)
pause
