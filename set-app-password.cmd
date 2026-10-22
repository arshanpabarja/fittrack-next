@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" "tools\setup_app_password.py" --gui
if errorlevel 1 pause
