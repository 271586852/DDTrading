param(
    [int]$FrontendPort = 3000,
    [int]$BackendPort = 8011,
    [string]$HostAddress = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendScript = Join-Path $PSScriptRoot "start-backend.ps1"
$frontendScript = Join-Path $PSScriptRoot "start-frontend.ps1"
$apiBaseUrl = "http://$HostAddress`:$BackendPort"
$corsOrigins = "http://127.0.0.1:$FrontendPort"

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$backendScript`"",
    "-HostAddress", $HostAddress,
    "-Port", $BackendPort,
    "-CorsOrigins", $corsOrigins
)

Start-Sleep -Seconds 2

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$frontendScript`"",
    "-Port", $FrontendPort,
    "-ApiBaseUrl", $apiBaseUrl
)

Write-Host "Frontend: http://127.0.0.1:$FrontendPort"
Write-Host "Backend:  $apiBaseUrl"
