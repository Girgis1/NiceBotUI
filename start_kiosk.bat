@echo off
REM Robot Control Kiosk Startup Script (Windows)
REM Verifies dependencies and launches kiosk mode

echo ================================
echo Robot Control Kiosk
echo ================================
echo.

REM Check if virtual environment exists
if exist ".venv\Scripts\activate.bat" (
    echo [OK] Found virtual environment
    call .venv\Scripts\activate.bat
) else (
    echo [ERROR] No virtual environment found
    echo   Run setup.sh first
    exit /b 1
)

REM Check Python
python --version
if errorlevel 1 (
    echo [ERROR] Python not found
    exit /b 1
)

REM Check for PySide6
python -c "import PySide6" 2>nul
if errorlevel 1 (
    echo [WARN] PySide6 not found, installing...
    pip install PySide6
) else (
    echo [OK] PySide6 installed
)

REM Check for OpenCV
python -c "import cv2" 2>nul
if errorlevel 1 (
    echo [WARN] OpenCV not found (camera detection disabled)
) else (
    echo [OK] OpenCV installed
)

REM Check for config file
if exist "config.json" (
    echo [OK] Configuration file found
) else (
    echo [WARN] No config.json found (will create default)
)

echo.
echo Starting kiosk mode...
echo Press Escape, Ctrl+Q, or Alt+F4 to exit
echo.

REM Parse arguments
if "%1"=="--windowed" (
    echo Running in windowed mode
    python NiceBot.py --windowed
) else if "%1"=="-w" (
    echo Running in windowed mode
    python NiceBot.py --windowed
) else (
    echo Running in fullscreen mode
    python NiceBot.py
)


