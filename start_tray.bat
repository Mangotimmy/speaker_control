@echo off
rem Starts the Edifier R20 tray controller in the background (no console window).
rem VBScript is no longer used: wscript/VBScript is an optional Windows feature
rem that is disabled on many managed machines.
setlocal
cd /d "%~dp0"

where pyw >nul 2>nul
if not errorlevel 1 (
    start "" pyw -3 "%~dp0run.py"
    exit /b 0
)

where pythonw >nul 2>nul
if not errorlevel 1 (
    start "" pythonw "%~dp0run.py"
    exit /b 0
)

where py >nul 2>nul
if not errorlevel 1 (
    start "" py -3 "%~dp0run.py"
    exit /b 0
)

echo Python 3.10+ was not found. Install Python, or use the packaged installer
echo (packaging\installer.nsi) that ships a standalone executable.
pause
exit /b 1
