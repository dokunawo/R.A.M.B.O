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

# 4) Seed the dedicated profile so it skips Chrome's first-run UI and pre-grants
# geolocation to the RAMBO origins (mic is handled by a launch flag below). This
# is written fresh each boot so it's deterministic for a kiosk profile.
$ramboProfile = "$projectRoot\.chrome-profile"
$prefDir = "$ramboProfile\Default"
try {
    New-Item -ItemType Directory -Force -Path $prefDir | Out-Null
    $prefs = @'
{
  "profile": {
    "content_settings": {
      "exceptions": {
        "geolocation": {
          "http://localhost:3000,*": { "setting": 1 },
          "http://localhost:3001,*": { "setting": 1 }
        },
        "media_stream_mic": {
          "http://localhost:3000,*": { "setting": 1 },
          "http://localhost:3001,*": { "setting": 1 }
        }
      }
    }
  },
  "browser": { "has_seen_welcome_page": true }
}
'@
    # Write UTF-8 WITHOUT BOM — Chrome's Preferences parser rejects a BOM.
    [System.IO.File]::WriteAllText("$prefDir\Preferences", $prefs, (New-Object System.Text.UTF8Encoding($false)))
    Log "Seeded RAMBO Chrome profile (geolocation + mic allowed)."
} catch {
    Log "WARNING: could not seed Chrome profile prefs: $_"
}

# 5) Open the browser.
Log "Opening browser at $url"
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
# RAMBO gets its OWN dedicated Chrome profile (--user-data-dir): a separate,
# isolated instance, so the flags below are honored even if your normal Chrome
# is already open. Your everyday Chrome is left untouched.
$chromeFlags = @(
    "--user-data-dir=$ramboProfile",               # dedicated, isolated profile
    "--no-first-run",                              # skip the "Sign in to Chrome" welcome
    "--no-default-browser-check",                  # skip "make Chrome default" prompt
    "--autoplay-policy=no-user-gesture-required",  # intro sound, no click needed
    "--start-fullscreen"                           # F11-style fullscreen on launch
    # NOTE: mic is granted via the seeded profile Preferences above (no need for
    # --use-fake-ui-for-media-stream, which triggers Chrome's "unsupported flag" bar).
)
# ?boot=1 tells the app this is a fresh machine boot → reset to unmuted/max so a
# persisted mute never survives a restart. The app strips the flag after reading.
$openUrl = "$url/?boot=1"
if ((Test-Path $chrome) -and $DevTools) {
    Start-Process $chrome -ArgumentList ($chromeFlags + "--auto-open-devtools-for-tabs" + $openUrl)
} elseif (Test-Path $chrome) {
    Start-Process $chrome -ArgumentList ($chromeFlags + $openUrl)
} else {
    Start-Process $openUrl   # default browser
}

Log "=== startup complete ==="
