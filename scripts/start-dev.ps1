param(
    [int]$FrontendPort = 3010,
    [int]$BackendPort = 8010,
    [string]$HostAddress = "127.0.0.1",
    [string]$TushareToken = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendScript = Join-Path $PSScriptRoot "start-backend.ps1"
$frontendScript = Join-Path $PSScriptRoot "start-frontend.ps1"
$apiBaseUrl = "http://$HostAddress`:$BackendPort"
$corsOrigins = "http://127.0.0.1:$FrontendPort,http://localhost:$FrontendPort"

function Stop-ProcessUsingPort {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $pids = @()
    try {
        $pids = Get-NetTCPConnection -LocalPort $Port -ErrorAction Stop |
            Select-Object -ExpandProperty OwningProcess -Unique
    } catch {
        # Fallback when Get-NetTCPConnection is unavailable.
        $pids = netstat -ano | Select-String ":$Port\s" |
            ForEach-Object {
                $line = $_.ToString().Trim()
                $parts = $line -split "\s+"
                if ($parts.Length -ge 5) { $parts[-1] }
            } |
            Where-Object { $_ -match "^\d+$" } |
            ForEach-Object { [int]$_ } |
            Select-Object -Unique
    }

    foreach ($processId in $pids) {
        if ($processId -gt 0 -and $processId -ne $PID) {
            try {
                Stop-Process -Id $processId -Force -ErrorAction Stop
                Write-Host "Killed process $processId on port $Port"
            } catch {
                Write-Warning "Failed to kill process $processId on port ${Port}: $($_.Exception.Message)"
            }
        }
    }
}

Stop-ProcessUsingPort -Port $BackendPort
Stop-ProcessUsingPort -Port $FrontendPort

$backendArgs = @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$backendScript`"",
    "-HostAddress", $HostAddress,
    "-Port", $BackendPort,
    "-CorsOrigins", $corsOrigins
)
if (-not [string]::IsNullOrWhiteSpace($TushareToken)) {
    $backendArgs += @("-TushareToken", $TushareToken)
}
Start-Process powershell -ArgumentList $backendArgs

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
