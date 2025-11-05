@echo off
REM Helper to launch the Linux setup script from Windows environments
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
if "%SCRIPT_DIR%"=="" set SCRIPT_DIR=.

where wsl >nul 2>nul
if %errorlevel%==0 (
    echo Running setup inside WSL...
    for /f "delims=" %%I in ('wslpath "%SCRIPT_DIR%"') do set "WSL_DIR=%%I"
    if not defined WSL_DIR (
        echo Unable to convert path for WSL. Please run setup.sh manually inside WSL.
        goto end
    )
    wsl -e bash -lc "cd \"%WSL_DIR%\" && bash setup.sh"
    goto end
)

where bash >nul 2>nul
if %errorlevel%==0 (
    echo Running setup using Git Bash...
    pushd "%SCRIPT_DIR%"
    bash setup.sh
    popd
    goto end
)

echo This project is intended to be installed on a Linux-based NVIDIA Jetson device.
echo Please copy the repository to the Jetson and run setup.sh there.

:end
pause
