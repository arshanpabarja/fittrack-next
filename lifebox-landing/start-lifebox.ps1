param(
    [string]$HostAddress = '192.168.100.95',
    [int]$Port = 8000,
    [ValidateSet('development', 'production')]
    [string]$Environment = 'development'
)

$ErrorActionPreference = 'Stop'
$siteRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $siteRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$managePath = Join-Path $projectRoot 'web_portal\manage.py'

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Django environment was not found. Create .venv and install the project requirements.'
}

Set-Location -LiteralPath $projectRoot
$env:DJANGO_DEBUG = if ($Environment -eq 'production') { '0' } else { '1' }
$env:DJANGO_ALLOWED_HOSTS = "127.0.0.1,localhost,$HostAddress"
$env:DJANGO_CSRF_TRUSTED_ORIGINS = "http://${HostAddress}:$Port"
& $pythonPath $managePath 'runserver' "${HostAddress}:$Port"
