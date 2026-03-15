@echo off
echo ==========================================
echo Stopping All FastAPI Servers
echo ==========================================

for %%p in (8001 8002 8003 8004 9000) do (
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr :%%p') do (
        if not "%%a"=="0" taskkill /F /PID %%a >nul 2>&1
    )
)

echo.
echo All FastAPI servers stopped!
pause