@echo off
echo Stopping Edifier R20 tray app...
taskkill /F /IM EdifierR20Tray.exe >nul 2>nul
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and $_.CommandLine -like '*tray_app.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>nul
echo Stopped.
exit /b 0
