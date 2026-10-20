@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating Python environment...
    py -3 -m venv ".venv"
    if errorlevel 1 goto :failed
)

echo [2/3] Checking dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed

echo [3/3] Starting Jump Bot. Press F12 or run stop.bat to stop.
".venv\Scripts\python.exe" jumpbot.py resume
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" jumpbot.py auto --max-jumps 1000000
echo.
echo Jump Bot has stopped. Check the message above for details.
pause
exit /b 0

:failed
echo.
echo Startup failed. Check that Python 3.10+ is installed and py works.
pause
exit /b 1
