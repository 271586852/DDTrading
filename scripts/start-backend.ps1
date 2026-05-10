param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8011,
    [Nullable[int]]$TushareMaxWorkers = $null,
    [string]$TushareToken = "",
    [string]$CorsOrigins = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $repoRoot "backend"

if (-not (Test-Path $backendRoot)) {
    throw "Backend directory not found: $backendRoot"
}

# Load backend/.env as the primary config source.
$envFile = Join-Path $backendRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }
        $parts = $line -split "=", 2
        if ($parts.Length -ne 2) {
            return
        }
        $key = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"')
        if ($key) {
            [System.Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
}

if ($CorsOrigins) {
    $env:DDTRADING_CORS_ORIGINS = $CorsOrigins
}
if ($TushareMaxWorkers -ne $null) {
    $env:DDTRADING_TUSHARE_MAX_WORKERS = "$TushareMaxWorkers"
}

if ($TushareToken) {
    $env:TUSHARE_TOKEN = $TushareToken
}

Set-Location $backendRoot
python -m uvicorn app.main:app --host $HostAddress --port $Port
