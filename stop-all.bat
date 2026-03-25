@echo off
echo ==========================================
echo Stopping All FastAPI Servers
echo ==========================================
echo.

for %%p in (8001 8002 8003 8004 9000) do (
    echo Checking port %%p...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%%p ^| findstr LISTENING') do (
        echo   Killing PID %%a on port %%p
        taskkill /F /PID %%a >nul 2>&1
    )
)

echo.
echo Done!
pause