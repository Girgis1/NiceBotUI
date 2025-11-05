@echo off
setlocal ENABLEDELAYEDEXPANSION

where ssh >NUL 2>&1
if errorlevel 1 (
    echo OpenSSH client not found. Install it from Windows Settings ^> Optional Features.
    exit /b 1
)

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

if not exist setup_jetson.sh (
    echo setup_jetson.sh not found. Please run this batch file from the NiceBotUI repository root.
    exit /b 1
)

echo This helper will execute setup_jetson.sh on your Jetson over SSH.
echo Ensure the repository is already cloned on the Jetson device.
echo.
set /p JETSON_HOST=Enter Jetson hostname or IP: 
if "%JETSON_HOST%"=="" (
    echo Hostname or IP is required.
    exit /b 1
)

set /p JETSON_USER=Enter Jetson username [default=jetson]: 
if "%JETSON_USER%"=="" set JETSON_USER=jetson
set JETSON_PATH_DEFAULT=/home/!JETSON_USER!/NiceBotUI
set /p JETSON_PATH=Enter path to NiceBotUI on Jetson [default=!JETSON_PATH_DEFAULT!]: 
if "%JETSON_PATH%"=="" set JETSON_PATH=!JETSON_PATH_DEFAULT!

echo.
echo Connecting to !JETSON_USER!@%JETSON_HOST% and running setup...
ssh !JETSON_USER!@%JETSON_HOST% "cd '!JETSON_PATH!' && chmod +x setup_jetson.sh && ./setup_jetson.sh"
if errorlevel 1 (
    echo.
    echo Remote setup failed. Check the output above for details.
    pause
    exit /b 1
)

echo.
echo Jetson setup completed successfully.
pause
