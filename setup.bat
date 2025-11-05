@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR%"=="" set "SCRIPT_DIR=."

for /f "delims=" %%I in ('wsl -e sh -c "command -v bash" 2^>nul') do set "HAS_WSL=1"
if not defined HAS_WSL (
    echo Windows Subsystem for Linux (WSL) is required to run the setup from Windows.
    echo Install WSL and an Ubuntu distribution, then re-run this script.
    exit /b 1
)

for /f "usebackq delims=" %%I in (`wsl wslpath -a "%SCRIPT_DIR%"`) do set "WSL_PATH=%%I"

if not defined WSL_PATH (
    echo Failed to resolve project directory inside WSL.
    exit /b 1
)

echo Launching setup inside WSL...
wsl bash -lc "cd '%WSL_PATH%' && chmod +x setup.sh && ./setup.sh"

if %errorlevel% neq 0 (
    echo Setup finished with errors (exit code %errorlevel%).
    exit /b %errorlevel%
)

echo Setup completed successfully.
pause
