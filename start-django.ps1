$ErrorActionPreference = "Stop"
if (-not $env:DJANGO_DEBUG) { $env:DJANGO_DEBUG = "1" }
if (-not $env:DJANGO_ALLOWED_HOSTS) { $env:DJANGO_ALLOWED_HOSTS = "127.0.0.1,localhost,192.168.100.95" }
if (-not $env:DJANGO_CSRF_TRUSTED_ORIGINS) { $env:DJANGO_CSRF_TRUSTED_ORIGINS = "http://192.168.100.95:8000" }
if (-not $env:FITTRACK_DB_PATH) {
    $parent = Split-Path -Parent $PSScriptRoot
    $outer = Split-Path -Parent $parent
    $outerCandidate = Join-Path $outer "database\gym_users.db"
    $siblingCandidate = Join-Path $parent "database\gym_users.db"
    $env:FITTRACK_DB_PATH = if (Test-Path -LiteralPath $outerCandidate) {
        $outerCandidate
    } else {
        $siblingCandidate
    }
}
& "$PSScriptRoot\.venv\Scripts\python.exe" "$PSScriptRoot\web_portal\manage.py" runserver 192.168.100.95:8000
