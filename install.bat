@echo off
echo ActivityMonitor - Installing Dependencies
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

echo Installing required packages...
pip install -r requirements.txt

echo.
echo Installation complete!
echo.
echo To start ActivityMonitor, run: run.bat
echo.
pause
