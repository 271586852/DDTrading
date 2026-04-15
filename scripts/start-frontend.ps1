param(
    [int]$Port = 3000,
    [string]$ApiBaseUrl = "http://127.0.0.1:8011"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $repoRoot "frontend"

if (-not (Test-Path $frontendRoot)) {
    throw "Frontend directory not found: $frontendRoot"
}

$env:NEXT_PUBLIC_API_BASE_URL = $ApiBaseUrl

Set-Location $frontendRoot
corepack pnpm dev --port $Port
