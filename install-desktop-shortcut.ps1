$ErrorActionPreference = 'Stop'
$desktopPath = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktopPath 'Life Box.lnk'
$launcherPath = Join-Path $PSScriptRoot 'start-lifebox.ps1'
if (-not (Test-Path -LiteralPath $launcherPath -PathType Leaf)) {
    throw 'start-lifebox.ps1 is missing. Extract all project files first.'
}
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $launcherPath + '"'
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.IconLocation = (Join-Path $PSScriptRoot 'icon.ico') + ',0'
$shortcut.Description = 'Life Box'
$shortcut.WindowStyle = 7
$shortcut.Save()
$saved = $shell.CreateShortcut($shortcutPath)
if ($saved.Arguments -ne $shortcut.Arguments -or $saved.TargetPath -ne $shortcut.TargetPath) {
    throw 'Windows did not save the shortcut correctly.'
}
Write-Output "Shortcut created and verified: $shortcutPath"
