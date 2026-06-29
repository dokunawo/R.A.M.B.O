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
#   .\rambo-startup.ps1 -Fresh     # bring the stack DOWN, then rebuild + up
#   .\rambo-startup.ps1 -Clean     # full no-cache rebuild (rarely needed)

param(
    [switch]$Rebuild,
    [switch]$Fresh,     # docker compose down, then rebuild changed layers + up
    [switch]$Clean,
    [switch]$Dev,       # open the dev frontend (:3001) instead of prod (:3000)
    [switch]$DevTools,  # open Chrome with DevTools panel auto-open
    [switch]$Kiosk      # TRUE locked kiosk (no F11/X exit; quit with Alt+F4). Default is
                        # --start-fullscreen: immersive but F11 / top-edge X still exit.
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

# 0) Single-instance guard. The boot Task Scheduler job and the desktop shortcut
# can both fire around login; without this they race and open TWO Chrome windows.
# A global mutex lets only the first run proceed — a concurrent second run exits
# HERE (before Docker/Chrome) so exactly one window ever opens. Released right
# after Chrome launches (bottom of script) so a later manual relaunch still works
# even though the desktop shortcut runs with -NoExit (its process stays alive).
$singletonMutex = $null
try {
    $singletonMutex = New-Object System.Threading.Mutex($false, "Global\RamboStartupSingleton")
    $acquired = $false
    try { $acquired = $singletonMutex.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $acquired = $true }  # prior run crashed; take it
    if (-not $acquired) {
        Log "Another R.A.M.B.O startup is already running — exiting to avoid a duplicate window."
        exit 0
    }
} catch { Log "WARNING: could not create singleton mutex: $_" }

# 1) Route the hardware media keys to the R.A.M.B.O player — FRONT-LOADED so the
# keys are captured from login, NOT after the multi-minute Docker/frontend waits
# below (that gap let the native keys / keyboard software mute audio). The Spotify
# Web Playback SDK's cross-origin iframe owns the browser media session, so Chrome
# won't deliver the play/pause key to our page — this OS-level helper intercepts
# the keys and POSTs to the backend. Until the backend is up, the POSTs no-op
# gracefully (the key does nothing rather than falling through). Needs AutoHotkey v2.
$ahkScript = "$projectRoot\rambo-mediakeys.ahk"
$ahkExe = @(
    "C:\Program Files\AutoHotkey\v2\AutoHotkey.exe",
    "C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe",
    "C:\Program Files\AutoHotkey\AutoHotkey.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($ahkExe -and (Test-Path $ahkScript)) {
    # Replace any prior instance so we don't stack duplicate key hooks.
    Get-CimInstance Win32_Process -Filter "Name LIKE 'AutoHotkey%'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*rambo-mediakeys.ahk*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Process $ahkExe -ArgumentList "`"$ahkScript`""
    Log "Media-key helper launched ($ahkExe)."
} else {
    Log "NOTE: AutoHotkey v2 not found — hardware media keys won't control RAMBO. Install from https://www.autohotkey.com/ to enable rambo-mediakeys.ahk."
}

# 2) Wait for the Docker daemon to be ready (Docker Desktop can take a bit
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

# 3) Bring the stack up. Everyday use = prod only. The dev frontend (:3001) is
# behind the "dev" compose profile, so it starts ONLY when -Dev is passed.
Set-Location $projectRoot
$profileArgs = if ($Dev) { @("--profile", "dev") } else { @() }
if ($Clean) {
    Log "Full no-cache rebuild (this takes a few minutes)..."
    docker compose @profileArgs down
    docker compose @profileArgs build --no-cache
    docker compose @profileArgs up -d
} elseif ($Fresh) {
    Log "Bringing the stack down, then rebuilding changed layers..."
    docker compose @profileArgs down
    docker compose @profileArgs up -d --build
} elseif ($Rebuild) {
    Log "Rebuilding changed layers..."
    docker compose @profileArgs up -d --build
} else {
    Log "Fast start (reusing images)..."
    docker compose @profileArgs up -d
}
if ($LASTEXITCODE -ne 0) { Log "WARNING: docker compose returned non-zero." }

# 4) Wait until the frontend actually answers (not just the container up).
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

# 5) Seed the dedicated profile so it: skips Chrome's first-run UI, pre-grants
# mic + geolocation to the RAMBO origins, and hides the bookmarks bar for a
# clean kiosk look. Written fresh each boot so it's deterministic.
$ramboProfile = "$projectRoot\.chrome-profile"
$prefDir = "$ramboProfile\Default"
try {
    New-Item -ItemType Directory -Force -Path $prefDir | Out-Null
    $prefs = @'
{
  "bookmark_bar": { "show_on_all_tabs": false },
  "session": { "restore_on_startup": 4, "startup_urls": [] },
  "profile": {
    "exit_type": "Normal",
    "exited_cleanly": true,
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

# 6) Open the browser.
Log "Opening browser at $url"
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"

# Close any leftover RAMBO-profile Chrome from a previous launch FIRST. If one is
# already alive, a second launch can't apply the fullscreen flags and you get a
# stray/blank extra window. We match ONLY processes using the dedicated RAMBO
# profile (--user-data-dir=...\.chrome-profile) — your everyday Chrome is untouched.
try {
    # Loop: kill, wait, re-check — a single Stop-Process can race Chrome's own
    # child processes, leaving one alive that then becomes the stray 2nd window.
    for ($i = 0; $i -lt 6; $i++) {
        $stale = Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -and $_.CommandLine -like "*--user-data-dir=$ramboProfile*" }
        if (-not $stale) { break }
        $stale | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Log "Closed $($stale.Count) leftover RAMBO Chrome process(es) before relaunch."
        Start-Sleep -Seconds 1   # let the profile lock release before re-checking
    }
} catch { Log "WARNING: could not check for leftover RAMBO Chrome: $_" }

# Wipe the prior browsing session AFTER the kill (so the dying Chrome can't rewrite
# it). We force-kill the leftover RAMBO Chrome above, which Chrome records as
# exit_type="Crashed" — so on the next launch its crash-restore re-opens the
# previous tab ON TOP OF the fresh ?boot=1 tab, giving TWO overlapping app tabs (a
# doubled greeting). --restore-last-session=false doesn't fully suppress that path;
# removing the session files is the only deterministic fix. Dedicated kiosk profile
# only — the everyday Chrome profile is never touched.
try {
    foreach ($s in @(
        "$prefDir\Sessions",
        "$prefDir\Current Session", "$prefDir\Current Tabs",
        "$prefDir\Last Session",    "$prefDir\Last Tabs"
    )) {
        if (Test-Path $s) { Remove-Item $s -Recurse -Force -ErrorAction SilentlyContinue }
    }
    Log "Cleared prior RAMBO browser session (prevents duplicate restore tab)."
} catch { Log "WARNING: could not clear prior RAMBO session: $_" }

# RAMBO gets its OWN dedicated Chrome profile (--user-data-dir): a separate,
# isolated instance, so the flags below are honored even if your normal Chrome
# is already open. Your everyday Chrome is left untouched.
# Fullscreen mode: default --start-fullscreen (immersive, but F11 and the
# top-edge tab × still let you exit). -Kiosk = truly locked (no F11/X; Alt+F4 only).
$fullscreenFlag = if ($Kiosk) { "--kiosk" } else { "--start-fullscreen" }
$chromeFlags = @(
    "--user-data-dir=$ramboProfile",               # dedicated, isolated profile
    "--no-first-run",                              # skip the "Sign in to Chrome" welcome
    "--no-default-browser-check",                  # skip "make Chrome default" prompt
    "--hide-crash-restore-bubble",                 # never prompt to restore tabs after an unclean (shutdown) exit
    "--restore-last-session=false",                # boot to a single fresh tab, not the previous session's stray tabs
    "--autoplay-policy=no-user-gesture-required",  # intro sound, no click needed
    "--force-device-scale-factor=0.8",             # boot the UI at 80% zoom (Daniel's preferred view) — no manual Ctrl+- needed
    # Screen vision: auto-pick the display so sharing starts with NO "Choose what
    # to share" dialog. The value is matched against the capture SOURCE NAME. On a
    # MULTI-MONITOR box the sources are "Screen 1" / "Screen 2" (NOT "Entire screen",
    # which only matches single-monitor) — RAMBO runs on the primary, so "Screen 1".
    # If RAMBO ever moves to the other monitor, change this to "Screen 2".
    # The value has a SPACE; it MUST stay quoted or Start-Process splits it and
    # Chrome opens the leftover token as a bogus URL (the stray blank tab).
    '--auto-select-desktop-capture-source="Screen 1"',
    $fullscreenFlag
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

# Release the single-instance lock now that Chrome is up — the desktop shortcut
# runs with -NoExit so this process lingers; holding the mutex would block the
# next manual relaunch. Releasing here keeps "one window at a time" without
# blocking deliberate restarts.
if ($singletonMutex) {
    try { $singletonMutex.ReleaseMutex() } catch {}
    $singletonMutex.Dispose()
}
