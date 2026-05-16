@echo off
chcp 65001 >nul

set SCRIPT_DIR=%~dp0

cd /d "%SCRIPT_DIR%"

echo =========================
echo LaunchDeck Setup
echo =========================
echo.

python --version >nul 2>nul

if errorlevel 1 (
    echo [ERROR] Python is not installed
    echo.
    pause
    exit /b
)

python -m pip install --upgrade pip
python -m pip install -r "%SCRIPT_DIR%requirements.txt"

echo.
echo =========================
echo Setup Complete
echo =========================
echo.

pause