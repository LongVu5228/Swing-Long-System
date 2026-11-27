@echo off
rem Double-click to (re)start the local HTF recorder / screener server and open the screener in your browser.
rem Any server already running on port 8765 is stopped first, so this is always a real restart with the newest code.
rem Close this window (or press Ctrl+C in it) to stop the server.
cd /d "%~dp0"
echo Stopping any screener server already running on port 8765...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
rem open the browser once the server has had time to load (~15 s)
start "" /min cmd /c "timeout /t 15 /nobreak >nul & start http://127.0.0.1:8765/screener"
"..\..\..\..\.venv\Scripts\python.exe" server.py
pause
