param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
try {
    $projectPath = $PSScriptRoot
    $pythonPath = Join-Path $projectPath '.venv\Scripts\pythonw.exe'
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw 'Python environment missing. Install Python 3.12, then run: py -3.12 -m venv .venv and .venv\Scripts\python.exe -m pip install -r requirements.txt'
    }
    $logFolder = Join-Path $projectPath 'logs'
    New-Item -ItemType Directory -Path $logFolder -Force | Out-Null
    $runId = [Guid]::NewGuid().ToString('N')
    $errorLog = Join-Path $logFolder ('startup-' + $runId + '.log')
    $outputLog = Join-Path $logFolder ('startup-' + $runId + '.out.log')
    if ($CheckOnly) {
        $pythonArguments = '-c "import sys; import PyQt6, numpy, cv2; print(sys.executable)"'
    } else {
        $pythonArguments = '"' + (Join-Path $projectPath 'launch.py') + '"'
    }
    # The application is an interactive GUI. Hiding this child can also hide
    # its Qt window; pythonw already avoids creating a console window.
    $process = Start-Process -FilePath $pythonPath -ArgumentList $pythonArguments -WorkingDirectory $projectPath -WindowStyle Normal -RedirectStandardError $errorLog -RedirectStandardOutput $outputLog -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        $details = (Get-Content -LiteralPath $errorLog -Tail 18 -ErrorAction SilentlyContinue) -join [Environment]::NewLine
        throw "Life Box could not start (exit $($process.ExitCode)).`n$details`n`nLog: $errorLog`nIf .venv was copied from another PC, recreate it using README.md."
    }
    if ($CheckOnly) { Write-Output 'Python and desktop dependencies are ready.' }
} catch {
    if ($CheckOnly) { throw }
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Life Box - startup error') | Out-Null
}
