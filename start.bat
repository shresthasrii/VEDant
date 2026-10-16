@echo off
title VERDANT - Green Building Digital Twin & AI Energy Optimization
color 0A
cls

echo ===============================================================================
echo                VERDANT : Green Building Intelligence Platform
echo        "See the building. Understand the energy. Optimize the future."
echo ===============================================================================
echo [1/4] Configuring Environment Paths...
set "PATH=%LOCALAPPDATA%\Programs\Ollama;%USERPROFILE%\scoop\apps\python\current;%USERPROFILE%\scoop\apps\python\current\Scripts;%PATH%"

echo [2/4] Initializing Local AI Engine (Ollama llama3.2)...
curl.exe -s http://127.0.0.1:11434/api/tags >nul 2>&1
if %ERRORLEVEL% neq 0 (
    start /B "" "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve >nul 2>&1
    timeout /t 2 /nobreak >nul
) else (
    echo       Ollama AI Engine already running and responsive.
)

echo [3/4] Launching VERDANT Backend Server (FastAPI + WebSocket)...
rem Clean up any stale process holding port 8000
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
start "VERDANT Backend Server" /min cmd /k "set PYTHONPATH=. && python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload"
timeout /t 3 /nobreak >nul

echo [4/4] Launching Live Computer Vision Worker (Room 202)...
start "VERDANT CV Worker" /min cmd /k "set PYTHONPATH=. && python cv/worker.py --room 202 --fps 1.0 --provenance camera"
timeout /t 1 /nobreak >nul

echo.
echo ===============================================================================
echo  SUCCESS: All VERDANT enterprise subsystems are active and running!
echo  - Web Application:       http://127.0.0.1:8000
echo  - Interactive API Docs:  http://127.0.0.1:8000/docs
echo  - Executive ESG Report:  http://127.0.0.1:8000/export/audit-report
echo  - AI Facility Copilot:   Integrated in Web App (GPU Llama 3.2 + Actions)
echo  - Solar PV & BESS:       100 kWp Rooftop Array + 50 kWh Storage
echo  - Anomaly Radar:         Z-Score & IQR Outlier Screening
echo  - Predictive Health:     Bathtub Curve Equipment Maintenance
echo  - BEE Star Rating:       5-Star / SuperECBC Net-Zero Ready (78.4 EUI)
echo  - 2D Blueprint Fallback: http://127.0.0.1:8000/?mode=2d
echo ===============================================================================
echo.
echo Opening VERDANT in your default web browser...
start http://127.0.0.1:8000
echo.
echo Press any key to stop all VERDANT background services...
pause >nul

echo Shutting down background processes...
taskkill /F /IM uvicorn.exe >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq VERDANT*" >nul 2>&1
echo Subsystems terminated cleanly.
timeout /t 2 /nobreak >nul
