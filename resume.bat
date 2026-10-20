@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" jumpbot.py resume
) else (
    py -3 jumpbot.py resume
)
echo If the main window already exited, double-click start.bat.
pause
