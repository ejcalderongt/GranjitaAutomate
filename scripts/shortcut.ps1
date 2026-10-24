$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$desktopPath = [Environment]::GetFolderPath('Desktop')
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $desktopPath 'GranjitaAutomate.lnk'))
$shortcut.TargetPath = Join-Path $env:WINDIR 'System32\wscript.exe'
$shortcut.Arguments = '"' + (Join-Path $projectRoot 'iniciar.vbs') + '"'
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = 'GranjitaAutomate v2 - inventario y servidores ADB de Panda'
$shortcut.IconLocation = (Join-Path $env:WINDIR 'System32\shell32.dll') + ',17'
$shortcut.Save()
Write-Output "Acceso directo creado: $desktopPath\GranjitaAutomate.lnk"
