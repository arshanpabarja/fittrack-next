$ErrorActionPreference = "Stop"
if (-not $env:DJANGO_DEBUG) { $env:DJANGO_DEBUG = "1" }
if (-not $env:DJANGO_ALLOWED_HOSTS) { $env:DJANGO_ALLOWED_HOSTS = "127.0.0.1,localhost,192.168.100.95" }
if (-not $env:DJANGO_CSRF_TRUSTED_ORIGINS) { $env:DJANGO_CSRF_TRUSTED_ORIGINS = "http://192.168.100.95:8000" }
& "$PSScriptRoot\.venv\Scripts\python.exe" "$PSScriptRoot\web_portal\manage.py" runserver 192.168.100.95:8000
