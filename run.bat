@echo off
echo ActivityMonitor - Automatic Time Tracking
echo ==========================================
echo.

REM Check if Python is available
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python from https://www.python.org/
    pause
    exit /b 1
)

REM Check if dependencies are installed
echo Checking dependencies...
python -c "import win32gui" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing pywin32...
    pip install pywin32
)

python -c "import pystray" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing pystray and Pillow...
    pip install pystray Pillow
)

python -c "import cv2" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing opencv-python ^(for camera detection^)...
    pip install opencv-python
)

echo.
echo Starting ActivityMonitor...
echo ^(Look for the icon in your system tray^)
echo.

cd /d "%~dp0"
python src/activity_monitor.py

pause
