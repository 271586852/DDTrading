param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8011,
    [string]$DataPath = "",
    [string]$DataSource = "auto",
    [int]$AkshareUniverseSize = 300,
    [int]$AkshareHistoryDays = 120,
    [int]$AkshareMaxWorkers = 8,
    [int]$AkshareCacheTtlSeconds = 600,
    [string]$CorsOrigins = "http://127.0.0.1:3000"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $repoRoot "backend"

if (-not (Test-Path $backendRoot)) {
    throw "Backend directory not found: $backendRoot"
}

$env:DDTRADING_CORS_ORIGINS = $CorsOrigins
$env:DDTRADING_DATA_SOURCE = $DataSource
$env:DDTRADING_AKSHARE_UNIVERSE_SIZE = "$AkshareUniverseSize"
$env:DDTRADING_AKSHARE_HISTORY_DAYS = "$AkshareHistoryDays"
$env:DDTRADING_AKSHARE_MAX_WORKERS = "$AkshareMaxWorkers"
$env:DDTRADING_AKSHARE_CACHE_TTL_SECONDS = "$AkshareCacheTtlSeconds"

if ($DataPath) {
    $env:DDTRADING_DATA_PATH = $DataPath
}

Set-Location $backendRoot
python -m uvicorn app.main:app --host $HostAddress --port $Port
