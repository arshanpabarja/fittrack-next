$ErrorActionPreference = "Stop"
if (-not $env:FITTRACK_DB_PATH) { $env:FITTRACK_DB_PATH = Join-Path (Split-Path -Parent $PSScriptRoot) "database\gym_users.db" }
if (-not $env:FITTRACK_ATTENDANCE_PATH) { $env:FITTRACK_ATTENDANCE_PATH = Join-Path $PSScriptRoot "state\fittrack_next.db" }
& "$PSScriptRoot\.venv\Scripts\python.exe" "$PSScriptRoot\web_portal\manage.py" runserver 0.0.0.0:8000
