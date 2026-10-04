<#
.SYNOPSIS
  Start AutoGrader+ locally without Docker (SQLite, single process).

.EXAMPLE
  .\scripts\start.ps1              # http://localhost:8000 (this machine only)
  .\scripts\start.ps1 -Lan         # also reachable from classmates on the same network
  .\scripts\start.ps1 -Port 9000
#>
param(
    [int]$Port = 8000,
    [switch]$Lan
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    python -m venv .venv
}
Write-Host "Checking dependencies..." -ForegroundColor Cyan
& $py -m pip install --disable-pip-version-check -q -r requirements.txt

$bindHost = if ($Lan) { "0.0.0.0" } else { "127.0.0.1" }
if (-not $env:AUTOGRADER_WORK_DIR) { $env:AUTOGRADER_WORK_DIR = Join-Path $root "data" }

Write-Host ""
Write-Host "AutoGrader+ -> http://localhost:$Port" -ForegroundColor Green
if ($Lan) {
    $ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' -and $_.PrefixOrigin -ne 'WellKnown' } |
        Select-Object -ExpandProperty IPAddress
    foreach ($ip in $ips) { Write-Host "             http://${ip}:$Port  (LAN)" -ForegroundColor Green }
    Write-Host "LAN mode: anyone on this network can reach the site. Disable demo accounts (AUTOGRADER_DEMO_SEED=0)" -ForegroundColor Yellow
    Write-Host "and set AUTOGRADER_INSTRUCTOR_EMAIL/PASSWORD for anything beyond a classroom demo." -ForegroundColor Yellow
}
Write-Host "Data directory: $env:AUTOGRADER_WORK_DIR   (Ctrl+C to stop)" -ForegroundColor DarkGray
& $py -m uvicorn app.main:app --host $bindHost --port $Port
