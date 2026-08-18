$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot ".venv\Scripts\pythonw.exe"
$launcher = Join-Path $PSScriptRoot "launch.py"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found. Install requirements first."
}

Start-Process -FilePath $python -ArgumentList $launcher -WorkingDirectory $PSScriptRoot
