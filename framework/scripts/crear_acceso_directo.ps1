$ErrorActionPreference = 'Stop'
$frameworkRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $frameworkRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Primero crea el entorno virtual e instala las dependencias del framework.'
}
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'AGX Auditoría.lnk'
$shortcutShell = New-Object -ComObject WScript.Shell
$shortcut = $shortcutShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonPath
$shortcut.Arguments = '-m ui.poc_dashboard'
$shortcut.WorkingDirectory = $frameworkRoot
$shortcut.Description = 'Panel AGX de auditoría: solo lectura y desplazamiento'
$shortcut.Save()
Write-Output "Acceso directo creado: $shortcutPath"
