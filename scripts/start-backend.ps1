param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8011,
    [int]$TushareUniverseSize = 300,
    [int]$TushareMaxWorkers = 8,
    [int]$TushareCacheTtlSeconds = 600,
    [string]$TushareToken = "",
    [string]$CorsOrigins = "http://127.0.0.1:3000,http://localhost:3000"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $repoRoot "backend"

if (-not (Test-Path $backendRoot)) {
    throw "Backend directory not found: $backendRoot"
}

$env:DDTRADING_CORS_ORIGINS = $CorsOrigins
$env:DDTRADING_TUSHARE_UNIVERSE_SIZE = "$TushareUniverseSize"
$env:DDTRADING_TUSHARE_MAX_WORKERS = "$TushareMaxWorkers"
$env:DDTRADING_TUSHARE_CACHE_TTL_SECONDS = "$TushareCacheTtlSeconds"

if ($TushareToken) {
    $env:TUSHARE_TOKEN = $TushareToken
}

Set-Location $backendRoot
python -m uvicorn app.main:app --host $HostAddress --port $Port
