$ErrorActionPreference = "Stop"
$desktopPath = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktopPath 'Life Box.lnk'

# Resolve the desktop at launch time so the shortcut also works for another user.
$launchCommand = @'
$ErrorActionPreference = 'Stop'
try {
    $desktopPath = [Environment]::GetFolderPath('Desktop')
    $candidates = @('lifebox', 'FitTrack Next', 'fittrack-next', 'fittrack-next-main') | ForEach-Object { Join-Path $desktopPath $_ }
    $candidates += '__INSTALL_PATH__'
    $projectPath = $candidates | Where-Object {
        (Test-Path -LiteralPath (Join-Path $_ 'launch.py') -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $_ 'start-lifebox.ps1') -PathType Leaf)
    } | Select-Object -First 1
    if (-not $projectPath) {
        throw 'Life Box project was not found. Extract the complete project and run create-desktop-shortcut.cmd inside it.'
    }
    & (Join-Path $projectPath 'start-lifebox.ps1')
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Life Box') | Out-Null
}
'@
$launchCommand = $launchCommand.Replace('__INSTALL_PATH__', $PSScriptRoot.Replace("'", "''"))
$encodedCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($launchCommand))
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$shortcut.Arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -EncodedCommand ' + $encodedCommand
$shortcut.WorkingDirectory = $desktopPath
$projectIcon = Join-Path $desktopPath 'lifebox\icon.ico'
if (-not (Test-Path -LiteralPath $projectIcon)) {
    $projectIcon = Join-Path $PSScriptRoot 'icon.ico'
}
$shortcut.IconLocation = $projectIcon + ',0'
$shortcut.Description = 'Life Box - Desktop\lifebox\launch.py'
$shortcut.WindowStyle = 7
$shortcut.Save()
Write-Output "Shortcut created: $shortcutPath"
