@echo off
echo Killing existing processes on port 8000...

for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo Terminating PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo Starting backend on 127.0.0.1:8000...
cd /d "%~dp0backend"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
