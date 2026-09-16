@echo off
echo ============================================
echo PULSEGUARD - Machine Health Monitoring System
echo ============================================
echo.
echo Starting servers...
echo.

cd /d "%~dp0"

echo [1/2] Starting Flask API Server...
echo    URL: http://localhost:5000
echo.
start "PulseGuard API" cmd /k "cd flask_api && python app.py"

timeout /t 3 /nobreak >nul

echo [2/2] Starting Web Dashboard Server...
echo    URL: http://localhost:8000
echo.
start "PulseGuard Dashboard" cmd /k "cd web && python -m http.server 8000"

echo.
echo ============================================
echo Both servers are starting...
echo.
echo Open these URLs in your browser:
echo   - Dashboard: http://localhost:8000
echo   - API Docs:  http://localhost:5000/
echo.
echo Press Ctrl+C in each window to stop servers.
echo.
pause
