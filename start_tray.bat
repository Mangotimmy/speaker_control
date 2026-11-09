@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine = 'C:\Python314\pythonw.exe \""%~dp0tray_app.py\""'; CurrentDirectory = '%~dp0'}"
exit /b 0
