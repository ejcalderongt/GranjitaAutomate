$installer = Join-Path $PSScriptRoot 'Configurar-ProxyLocal-Admin.ps1'
$ErrorActionPreference = 'Stop'
$process = Start-Process -FilePath 'powershell.exe' -Verb RunAs -WindowStyle Hidden `
    -ArgumentList ('-NoProfile -ExecutionPolicy RemoteSigned -File "' + $installer + '"') -Wait -PassThru
exit $process.ExitCode
