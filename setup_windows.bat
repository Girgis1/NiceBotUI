@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR%"=="" set "SCRIPT_DIR=."

echo =========================================
echo NiceBotUI Setup (Windows helper)
echo =========================================
echo.

where wsl.exe >NUL 2>&1
if %ERRORLEVEL%==0 (
    for /f "usebackq delims=" %%I in (`wsl.exe wslpath -a "%SCRIPT_DIR%" 2^>NUL`) do set "WSL_DIR=%%I"
    if not defined WSL_DIR (
        echo Failed to translate project path for WSL.
        echo Run ^`setup.sh^` manually inside your WSL/Jetson environment.
        goto END
    )

    echo Launching setup inside WSL...
    wsl.exe bash -lc "cd '%WSL_DIR%' && chmod +x setup.sh && ./setup.sh"
    goto END
)

echo WSL not detected. To run the setup from Windows, either:
echo   1. Install Windows Subsystem for Linux (Ubuntu recommended), or
echo   2. SSH into the Jetson and execute ^`./setup.sh^` directly.

:END
echo.
pause
