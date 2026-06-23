# rambo-startup.ps1 — seamless boot for R.A.M.B.O
#
# Waits for Docker, brings the stack up, waits for the dev frontend to be
# reachable, then opens the browser. Designed to be run by Task Scheduler at
# login (see the registration command in the README / your notes).
#
# Usage:
#   .\rambo-startup.ps1            # fast start (reuses images — seconds)
#   .\rambo-startup.ps1 -Rebuild   # rebuild changed layers (deps changed)
#   .\rambo-startup.ps1 -Clean     # full no-cache rebuild (rarely needed)

param(
    [switch]$Rebuild,
    [switch]$Clean,
    [switch]$DevTools   # open Chrome with DevTools panel auto-open
)

$ErrorActionPreference = "Continue"
$projectRoot = "C:\Users\dokun\PycharmProjects\R.A.M.B.O"
$devUrl      = "http://localhost:3001"
$logFile     = "$projectRoot\rambo-startup.log"

function Log($msg) {
    $line = "{0}  {1}" -f (Get-Date -Format "HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $logFile -Value $line -ErrorAction SilentlyContinue
}

Log "=== R.A.M.B.O startup ==="

# 1) Wait for the Docker daemon to be ready (Docker Desktop can take a bit
#    after login). Poll up to ~3 minutes.
Log "Waiting for Docker daemon..."
$dockerReady = $false
for ($i = 0; $i -lt 36; $i++) {
    docker info *> $null
    if ($LASTEXITCODE -eq 0) { $dockerReady = $true; break }
    Start-Sleep -Seconds 5
}
if (-not $dockerReady) {
    Log "ERROR: Docker daemon never came up. Is Docker Desktop set to start at login?"
    exit 1
}
Log "Docker daemon ready."

# 2) Bring the stack up.
Set-Location $projectRoot
if ($Clean) {
    Log "Full no-cache rebuild (this takes a few minutes)..."
    docker compose build --no-cache
    docker compose up -d
} elseif ($Rebuild) {
    Log "Rebuilding changed layers..."
    docker compose up -d --build
} else {
    Log "Fast start (reusing images)..."
    docker compose up -d
}
if ($LASTEXITCODE -ne 0) { Log "WARNING: docker compose returned non-zero." }

# 3) Wait until the dev frontend actually answers (not just the container up).
Log "Waiting for $devUrl ..."
$frontendReady = $false
for ($i = 0; $i -lt 36; $i++) {
    try {
        $r = Invoke-WebRequest -Uri $devUrl -UseBasicParsing -TimeoutSec 4
        if ($r.StatusCode -eq 200) { $frontendReady = $true; break }
    } catch { Start-Sleep -Seconds 5 }
}
if (-not $frontendReady) {
    Log "WARNING: $devUrl did not respond in time; opening anyway."
}

# 4) Open the browser.
Log "Opening browser at $devUrl"
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
if ((Test-Path $chrome) -and $DevTools) {
    Start-Process $chrome -ArgumentList "--auto-open-devtools-for-tabs", $devUrl
} elseif (Test-Path $chrome) {
    Start-Process $chrome -ArgumentList $devUrl
} else {
    Start-Process $devUrl   # default browser
}

Log "=== startup complete ==="
