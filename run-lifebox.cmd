@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Python environment not found. Follow README.md to install it.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" "launch.py"
if errorlevel 1 (
    echo.
    echo Life Box failed to start. The error is shown above.
    pause
)
