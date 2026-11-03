#requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$resultPath = Join-Path $workspace 'sessions\local_proxy\admin-result.json'
try {
    $settings = Get-Content -LiteralPath (Join-Path $workspace 'config\local_proxy.local.json') -Raw | ConvertFrom-Json
    $localIp = [System.Net.IPAddress]::Parse($settings.host).ToString()
    if (-not (Get-NetIPAddress -AddressFamily IPv4 | Where-Object IPAddress -eq $localIp)) {
        throw 'La IP de escucha no pertenece a este equipo.'
    }
    if (($settings.ports -join ',') -ne '8001,8002,8003') { throw 'Puertos no previstos.' }
    $clients = @($settings.allowed_clients | ForEach-Object { [System.Net.IPAddress]::Parse($_).ToString() })
    if ($clients.Count -lt 1) { throw 'ACL de clientes vacia.' }
    $ruleName = 'PandaProxy-Laboratorio-8001-8003'
    Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -Name $ruleName -DisplayName 'Panda Proxy laboratorio (clientes autorizados)' `
        -Direction Inbound -Action Allow -Protocol TCP -LocalAddress Any `
        -LocalPort 8001,8002,8003 -RemoteAddress $clients -Profile Any -EdgeTraversalPolicy Block | Out-Null
    @{ status='ok'; rule=$ruleName; host=$localIp; ports=@(8001,8002,8003) } |
        ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
} catch {
    @{ status='error'; detail=$_.Exception.Message } | ConvertTo-Json |
        Set-Content -LiteralPath $resultPath -Encoding UTF8
    exit 1
}
