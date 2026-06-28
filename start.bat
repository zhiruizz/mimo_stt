@echo off
title MiMo STT

echo ============================================================
echo   MiMo STT - Speech to Text Tool
echo ============================================================
echo.

python --version >NUL 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.8+
    pause
    exit /b 1
)

ffmpeg -version >NUL 2>&1
if errorlevel 1 (
    echo [ERROR] ffmpeg not found. Please install ffmpeg and add to PATH
    pause
    exit /b 1
)

echo [1/2] Installing dependencies...
pip install -r "%~dp0requirements.txt" -q >NUL 2>&1
echo       Done.
echo.

echo [2/2] Starting server at http://localhost:5000
echo.

start "" cmd /c "timeout /t 2 /nobreak >NUL && start http://localhost:5000"

cd /d "%~dp0"
python backend.py

echo.
echo Server stopped.
pause
