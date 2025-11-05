@echo off
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
pushd %SCRIPT_DIR% >NUL

set BASH_EXEC=

if exist "%SYSTEMROOT%\System32\wsl.exe" (
    set BASH_EXEC=wsl.exe
) else if exist "%ProgramFiles%\Git\bin\bash.exe" (
    set BASH_EXEC="%ProgramFiles%\Git\bin\bash.exe"
) else if exist "%ProgramFiles(x86)%\Git\bin\bash.exe" (
    set BASH_EXEC="%ProgramFiles(x86)%\Git\bin\bash.exe"
)

if "!BASH_EXEC!"=="" (
    echo Could not find WSL or Git Bash on this system.
    echo Please copy the repository to your Jetson device and run setup_jetson_orin.sh there.
    goto :END
)

echo =========================================
echo LeRobot Operator Console - Jetson Setup
echo =========================================
echo.

echo Launching Jetson setup script using !BASH_EXEC! ...
!BASH_EXEC! bash "setup_jetson_orin.sh"

echo.
echo Setup script finished. Review the output above for any errors.

echo.
:END
popd >NUL
pause
