<#
.SYNOPSIS
  Start AutoGrader+ locally without Docker (SQLite, single process).

.DESCRIPTION
  Creates/reuses a .venv, installs dependencies only when they change, and serves
  the app with uvicorn. A hash of requirements.txt is stored inside the venv; repeat
  starts skip `pip install` when the hash matches, so startup is near-instant. A new
  venv, a changed requirements.txt, or -Reinstall forces a fresh install.

.PARAMETER Port
  TCP port to serve on. Default: 8000.

.PARAMETER Lan
  Bind 0.0.0.0 so classmates on the same network can reach the site (default is
  localhost only).

.PARAMETER Reinstall
  Force `pip install` even when the requirements hash is unchanged.

.EXAMPLE
  .\scripts\start.ps1              # http://localhost:8000 (this machine only)

.EXAMPLE
  .\scripts\start.ps1 -Lan         # also reachable from classmates on the same network

.EXAMPLE
  .\scripts\start.ps1 -Port 9000

.EXAMPLE
  .\scripts\start.ps1 -Reinstall   # re-run pip install even if requirements are unchanged
#>
param(
    [int]$Port = 8000,
    [switch]$Lan,
    [switch]$Reinstall
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = Join-Path $root ".venv\Scripts\python.exe"
$reqFile = Join-Path $root "requirements.txt"
# Marker lives inside the venv, so deleting .venv (or a fresh clone) forces a reinstall.
$stamp = Join-Path $root ".venv\.requirements.sha256"

$venvCreated = $false
if (-not (Test-Path $py)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    python -m venv .venv
    $venvCreated = $true
}

# Content hash of requirements.txt. Using the file hash (not a timestamp) means an
# unchanged-but-touched file still skips install, and any real edit triggers one.
$wantHash = (Get-FileHash -Path $reqFile -Algorithm SHA256).Hash
$haveHash = if (Test-Path $stamp) { (Get-Content $stamp -Raw).Trim() } else { "" }

if ($Reinstall -or $venvCreated -or ($wantHash -ne $haveHash)) {
    if ($Reinstall) {
        $reason = "-Reinstall requested"
    } elseif ($venvCreated) {
        $reason = "new virtual environment"
    } else {
        $reason = "requirements.txt changed"
    }
    Write-Host "Installing dependencies ($reason)..." -ForegroundColor Cyan
    & $py -m pip install --disable-pip-version-check -q -r $reqFile
    if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit $LASTEXITCODE)" }
    # Record the hash only after a successful install, so a failed install retries next time.
    Set-Content -Path $stamp -Value $wantHash -NoNewline
} else {
    Write-Host "Dependencies up to date (requirements.txt unchanged) - skipping pip install." -ForegroundColor DarkGray
}

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
Write-Host "Health check: http://localhost:$Port/api/health" -ForegroundColor DarkGray
Write-Host "Data directory: $env:AUTOGRADER_WORK_DIR   (Ctrl+C to stop)" -ForegroundColor DarkGray
& $py -m uvicorn app.main:app --host $bindHost --port $Port
