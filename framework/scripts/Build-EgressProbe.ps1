param([string]$SdkPath)
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
if (-not $SdkPath) {
    $native = Get-Content -LiteralPath (Join-Path $workspace 'config\native_dependencies.local.json') -Raw | ConvertFrom-Json
    $SdkPath = Split-Path -Parent (Split-Path -Parent $native.adb_path)
}
$d8 = Get-ChildItem -LiteralPath (Join-Path $SdkPath 'build-tools') -Recurse -Filter d8.bat |
    Sort-Object FullName -Descending | Select-Object -First 1
$android = Get-ChildItem -LiteralPath (Join-Path $SdkPath 'platforms') -Recurse -Filter android.jar |
    Sort-Object FullName -Descending | Select-Object -First 1
if (-not $d8 -or -not $android) { throw 'Faltan build-tools D8 o android.jar en el SDK.' }
$classes = Join-Path $workspace 'tools\local_proxy\build\classes'
$dex = Join-Path $workspace 'tools\local_proxy\build\dex'
New-Item -ItemType Directory -Force -Path $classes,$dex | Out-Null
& javac.exe --release 8 -d $classes (Join-Path $workspace 'android\egress_probe\org\panda\qa\EgressProbe.java')
if ($LASTEXITCODE -ne 0) { throw 'Fallo de javac.' }
& $d8.FullName --lib $android.FullName --min-api 23 --output $dex (Join-Path $classes 'org\panda\qa\EgressProbe.class')
if ($LASTEXITCODE -ne 0) { throw 'Fallo de D8.' }
& (Join-Path $workspace '.venv\Scripts\python.exe') (Join-Path $workspace 'scripts\package_egress_probe.py')
if ($LASTEXITCODE -ne 0) { throw 'Fallo creando el JAR.' }
