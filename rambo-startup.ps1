# rambo-startup.ps1 — seamless boot for R.A.M.B.O
#
# Waits for Docker, brings the stack up, waits for the frontend to be
# reachable, then opens the browser. Designed to be run by Task Scheduler at
# login (see the registration command in the README / your notes).
#
# Usage:
#   .\rambo-startup.ps1            # fast start, opens PROD frontend (:3000)
#   .\rambo-startup.ps1 -Dev       # open the DEV frontend (:3001, hot reload)
#   .\rambo-startup.ps1 -Rebuild   # rebuild changed layers (deps changed)
#   .\rambo-startup.ps1 -Clean     # full no-cache rebuild (rarely needed)

param(
    [switch]$Rebuild,
    [switch]$Clean,
    [switch]$Dev,       # open the dev frontend (:3001) instead of prod (:3000)
    [switch]$DevTools   # open Chrome with DevTools panel auto-open
)

$ErrorActionPreference = "Continue"
$projectRoot = "C:\Users\dokun\PycharmProjects\R.A.M.B.O"
# Default to the prod frontend (:3000) — fast, optimized, for everyday use.
# Pass -Dev for the hot-reload dev frontend (:3001) while building.
$url         = if ($Dev) { "http://localhost:3001" } else { "http://localhost:3000" }
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

# 3) Wait until the frontend actually answers (not just the container up).
Log "Waiting for $url ..."
$frontendReady = $false
for ($i = 0; $i -lt 36; $i++) {
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 4
        if ($r.StatusCode -eq 200) { $frontendReady = $true; break }
    } catch { Start-Sleep -Seconds 5 }
}
if (-not $frontendReady) {
    Log "WARNING: $url did not respond in time; opening anyway."
}

# 4) Open the browser.
# --autoplay-policy lets the intro sound play on boot without a click. NOTE:
# Chrome only applies these flags when it launches a FRESH process — at login
# Chrome isn't running yet, so this works. If Chrome is already open, the URL
# opens in the existing window and the flag is ignored (you'd need a gesture).
Log "Opening browser at $url"
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$autoplay = "--autoplay-policy=no-user-gesture-required"
if ((Test-Path $chrome) -and $DevTools) {
    Start-Process $chrome -ArgumentList $autoplay, "--auto-open-devtools-for-tabs", $url
} elseif (Test-Path $chrome) {
    Start-Process $chrome -ArgumentList $autoplay, $url
} else {
    Start-Process $url   # default browser
}

Log "=== startup complete ==="
