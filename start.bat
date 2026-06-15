@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ================================
echo   ConfigHub
echo ================================
echo.
start http://127.0.0.1:5000
echo Starting server (Ctrl+C to stop)...
echo ================================
python app.py
pause