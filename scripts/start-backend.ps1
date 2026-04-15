param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8011,
    [string]$DataPath = "",
    [string]$CorsOrigins = "http://127.0.0.1:3000"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $repoRoot "backend"

if (-not (Test-Path $backendRoot)) {
    throw "Backend directory not found: $backendRoot"
}

$env:DDTRADING_CORS_ORIGINS = $CorsOrigins

if ($DataPath) {
    $env:DDTRADING_DATA_PATH = $DataPath
}

Set-Location $backendRoot
python -m uvicorn app.main:app --host $HostAddress --port $Port
