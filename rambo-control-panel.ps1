# ============================================================
#  R.A.M.B.O CONTROL PANEL  —  v2
# ============================================================

Clear-Host

# ============================
#  STEP 1 — CONFIG
# ============================

$dockerRoot = "C:\Users\dokun\PycharmProjects\R.A.M.B.O"
$soundRoot  = "$dockerRoot\sounds"

$BackendName      = "rambo-backend"
$FrontendProdName = "rambo-frontend"
$FrontendDevName  = "rambo-frontend-dev"

$BackendPort      = 8000
$FrontendProdPort = 3000
$FrontendDevPort  = 3001

$Global:CurrentMode = "Dev"

# ============================
#  STEP 1 — DOCKER DAEMON CHECK
# ============================

function Assert-Docker {
    $info = docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "  [ERROR] Docker Desktop is not running." -ForegroundColor Red
        Write-Host "  Start Docker Desktop, wait a few seconds, then try again." -ForegroundColor Yellow
        Write-Host ""
        return $false
    }
    return $true
}

# ============================
#  STEP 2 — SOUND ENGINE
# ============================

function Play-Sound {
    param([string]$File)
    if (Test-Path $File) {
        $player = New-Object System.Media.SoundPlayer
        $player.SoundLocation = $File
        $player.Load()
        $player.Play()
    }
}

$Sounds = @{
    Startup  = Join-Path $soundRoot "startup.wav"
    HudBoot  = Join-Path $soundRoot "hud_boot.wav"
    Nav      = Join-Path $soundRoot "nav.wav"
    Online   = Join-Path $soundRoot "online.wav"
    Alert    = Join-Path $soundRoot "alert.wav"
    Critical = Join-Path $soundRoot "critical.wav"
}

# ============================
#  STEP 2 — TYPEWRITER ENGINE
# ============================

function Type-Write {
    param(
        [string]$Text,
        [int]$Delay = 6,
        [ConsoleColor]$Color = "Cyan"
    )
    foreach ($char in $Text.ToCharArray()) {
        Write-Host -NoNewline $char -ForegroundColor $Color
        Start-Sleep -Milliseconds $Delay
    }
    Write-Host ""
}

function Type-Section {
    param([string]$Text)
    Type-Write $Text -Delay 4 -Color Yellow
}

function Type-OK {
    param([string]$Text)
    Type-Write "  [OK] $Text" -Delay 4 -Color Green
}

function Type-Error {
    param([string]$Text)
    Type-Write "  [!!] $Text" -Delay 4 -Color Red
}

function Type-Info {
    param([string]$Text)
    Type-Write "  $Text" -Delay 5 -Color Cyan
}

function Center-Text {
    param([string]$Text, [ConsoleColor]$Color = "Cyan")
    $w   = $Host.UI.RawUI.WindowSize.Width
    $pad = [Math]::Max(0, [int](($w - $Text.Length) / 2))
    Write-Host (" " * $pad + $Text) -ForegroundColor $Color
}

# ============================
#  STEP 3 — BOOT ANIMATION
# ============================

function Show-BootAnimation {
    Clear-Host
    Play-Sound $Sounds.Startup

    $w       = $Host.UI.RawUI.WindowSize.Width
    $barLen  = [Math]::Max(20, [int]($w * 0.55))   # 55% of terminal width, min 20
    $steps   = 10
    $filled  = [int]($barLen / $steps)

    Write-Host ""
    Center-Text "Booting R.A.M.B.O Control Systems..." -Color Cyan
    Write-Host ""

    for ($i = 0; $i -le $steps; $i++) {
        $done    = "█" * ($i * $filled)
        $empty   = " " * ($barLen - $done.Length)
        $pct     = "$([int]($i * 10))%".PadLeft(5)
        $frame   = "[ $done$empty ] $pct"
        $pad     = " " * [Math]::Max(0, [int](($w - $frame.Length) / 2))
        Write-Host "`r$pad$frame" -NoNewline -ForegroundColor Cyan
        Start-Sleep -Milliseconds 90
    }

    Write-Host ""
    Start-Sleep -Milliseconds 200

    Center-Text "Neural core......... ONLINE" -Color DarkCyan
    Center-Text "HUD interface....... ACTIVE" -Color DarkCyan
    Center-Text "Docker daemon....... LINKED" -Color DarkCyan

    Start-Sleep -Milliseconds 150
    Play-Sound $Sounds.HudBoot
}

# ============================
#  STEP 3 — HEADER
# ============================

function Show-Header {
    Clear-Host
    $w     = $Host.UI.RawUI.WindowSize.Width
    $title = "R . A . M . B . O   CONTROL PANEL   |   Mode: $Global:CurrentMode"

    Write-Host ""
    Write-Host ("=" * $w) -ForegroundColor Cyan
    Center-Text $title -Color Cyan
    Write-Host ("=" * $w) -ForegroundColor Cyan
    Write-Host ""
}

# ============================
#  STEP 6 — SYSTEM STATUS
# ============================

function Show-SystemStatus {
    if (-not (Assert-Docker)) { return }

    Play-Sound $Sounds.Online
    Clear-Host
    Write-Host ""
    Type-Section "  SYSTEM STATUS"
    Write-Host ""

    $cpu = [math]::Round(
        (Get-Counter '\Processor(_Total)\% Processor Time').CounterSamples.CookedValue, 1)
    $ramAvailMB = [math]::Round(
        (Get-Counter '\Memory\Available MBytes').CounterSamples.CookedValue)
    $ramTotalMB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1MB)
    $ramUsedMB  = $ramTotalMB - $ramAvailMB
    $ramPct     = [math]::Round(($ramUsedMB / $ramTotalMB) * 100, 1)

    Type-Info "CPU Load  : $cpu%"
    Type-Info "RAM Used  : ${ramUsedMB} MB / ${ramTotalMB} MB  ($ramPct%)"
    Write-Host ""

    Type-Section "  CONTAINERS"
    Write-Host ""

    $containers = @(
        @{ Name = $BackendName;      Port = $BackendPort;      Label = "Backend" }
        @{ Name = $FrontendProdName; Port = $FrontendProdPort; Label = "Frontend PROD" }
        @{ Name = $FrontendDevName;  Port = $FrontendDevPort;  Label = "Frontend DEV" }
    )

    Push-Location $dockerRoot
    foreach ($c in $containers) {
        $running = docker ps --format "{{.Names}}" | Select-String -Quiet $c.Name
        if ($running) {
            $uptime = docker ps --format "{{.Names}} {{.Status}}" |
                      Select-String $c.Name |
                      ForEach-Object { ($_ -split "\s+", 2)[1] }
            Write-Host ("  {0,-18} " -f $c.Label) -NoNewline -ForegroundColor Cyan
            Write-Host "RUNNING" -NoNewline -ForegroundColor Green
            Write-Host "  —  $uptime  —  http://localhost:$($c.Port)" -ForegroundColor DarkGray
        } else {
            Write-Host ("  {0,-18} " -f $c.Label) -NoNewline -ForegroundColor Cyan
            Write-Host "STOPPED" -ForegroundColor DarkRed
        }
    }
    Pop-Location

    Write-Host ""
    Type-Section "  PORT SNAPSHOT"
    Write-Host ""

    foreach ($c in $containers) {
        $inUse = netstat -ano | Select-String ":$($c.Port)\s"
        if ($inUse) {
            Write-Host ("  Port {0}  ({1,-18}) " -f $c.Port, $c.Label) -NoNewline -ForegroundColor Cyan
            Write-Host "IN USE" -ForegroundColor Green
        } else {
            Write-Host ("  Port {0}  ({1,-18}) " -f $c.Port, $c.Label) -NoNewline -ForegroundColor Cyan
            Write-Host "FREE"   -ForegroundColor DarkGray
        }
    }

    Write-Host ""
}

# ============================
#  STEP 5 — DOCKER ACTIONS
# ============================

function Start-Docker {
    if (-not (Assert-Docker)) { return }

    Push-Location $dockerRoot
    Play-Sound $Sounds.HudBoot
    Type-Info "Launching $Global:CurrentMode mode..."
    Write-Host ""

    switch ($Global:CurrentMode) {
        "Prod" {
            Type-Info "Building production frontend..."
            docker compose build $FrontendProdName
            docker compose stop $FrontendDevName 2>$null | Out-Null
            docker compose up -d $BackendName $FrontendProdName
        }
        "Dev" {
            docker compose stop $FrontendProdName 2>$null | Out-Null
            docker compose up -d --build $BackendName $FrontendDevName
        }
        "Hybrid" {
            Type-Info "Building production frontend..."
            docker compose build $FrontendProdName
            docker compose up -d --build $BackendName $FrontendProdName $FrontendDevName
        }
    }

    Pop-Location
    Play-Sound $Sounds.Online
    Write-Host ""
    Type-OK "$Global:CurrentMode containers are up."

    switch ($Global:CurrentMode) {
        "Prod"   { Type-Info "Frontend: http://localhost:$FrontendProdPort" }
        "Dev"    { Type-Info "Frontend: http://localhost:$FrontendDevPort" }
        "Hybrid" {
            Type-Info "Prod : http://localhost:$FrontendProdPort"
            Type-Info "Dev  : http://localhost:$FrontendDevPort"
        }
    }
}

function Stop-Docker {
    if (-not (Assert-Docker)) { return }

    Play-Sound $Sounds.Alert
    Type-Info "Stopping all RAMBO containers..."

    Push-Location $dockerRoot
    docker compose down 2>&1 | Out-Null
    Pop-Location

    Play-Sound $Sounds.Online
    Type-OK "All containers stopped."
}

function Restart-Docker {
    if (-not (Assert-Docker)) { return }

    Play-Sound $Sounds.HudBoot
    Type-Info "Restarting $Global:CurrentMode mode..."

    Push-Location $dockerRoot
    docker compose down 2>&1 | Out-Null
    Pop-Location

    Start-Docker
}

function Show-Logs {
    if (-not (Assert-Docker)) { return }

    Play-Sound $Sounds.HudBoot
    Type-Info "Streaming logs — press CTRL+C to exit."
    Write-Host ""

    Push-Location $dockerRoot
    switch ($Global:CurrentMode) {
        "Prod"   { docker compose logs -f $BackendName $FrontendProdName }
        "Dev"    { docker compose logs -f $BackendName $FrontendDevName }
        "Hybrid" { docker compose logs -f }
    }
    Pop-Location
}

# ============================
#  STEP 7 — DOCKER HEALTH SCAN
# ============================

function Show-HealthScan {
    if (-not (Assert-Docker)) { return }

    Play-Sound $Sounds.Online
    Clear-Host
    Write-Host ""
    Type-Section "  DOCKER HEALTH SCAN"
    Write-Host ""

    Push-Location $dockerRoot

    $names = docker ps --format "{{.Names}}" 2>$null
    if (-not $names) {
        Type-Error "No containers are running."
        Pop-Location
        return
    }

    foreach ($name in $names) {
        $health = docker inspect --format "{{json .State.Health}}" $name 2>$null
        $status = docker inspect --format "{{.State.Status}}"      $name 2>$null

        Write-Host ("  {0,-26} " -f $name) -NoNewline -ForegroundColor Cyan
        Write-Host "[$status]" -NoNewline -ForegroundColor White

        if ($health -and $health -ne "null") {
            $parsed = $health | ConvertFrom-Json
            $hStatus = $parsed.Status
            $color = switch ($hStatus) {
                "healthy"   { "Green" }
                "unhealthy" { "Red" }
                default     { "Yellow" }
            }
            Write-Host "  health: $hStatus" -ForegroundColor $color
        } else {
            Write-Host "  no healthcheck" -ForegroundColor DarkGray
        }
    }

    Pop-Location
    Write-Host ""
}

# ============================
#  STEP 7 — FORCE REBUILD
# ============================

function Force-Rebuild {
    if (-not (Assert-Docker)) { return }

    Play-Sound $Sounds.Alert
    Write-Host ""
    Type-Error "This will stop all containers, remove images, and rebuild from scratch."
    Write-Host ""
    $confirm = Read-Host "  Type YES to confirm"

    if ($confirm -ne "YES") {
        Type-Info "Rebuild cancelled."
        return
    }

    Play-Sound $Sounds.HudBoot
    Push-Location $dockerRoot

    Type-Info "Bringing down all containers..."
    docker compose down --rmi local 2>&1 | Out-Null

    Type-Info "Rebuilding $Global:CurrentMode from scratch..."

    switch ($Global:CurrentMode) {
        "Prod" {
            docker compose build --no-cache $BackendName $FrontendProdName
            docker compose up -d $BackendName $FrontendProdName
        }
        "Dev" {
            docker compose build --no-cache $BackendName $FrontendDevName
            docker compose up -d $BackendName $FrontendDevName
        }
        "Hybrid" {
            docker compose build --no-cache
            docker compose up -d
        }
    }

    Pop-Location
    Play-Sound $Sounds.Online
    Type-OK "Force rebuild complete."
}

# ============================
#  STEP 7 — OPEN IN BROWSER
# ============================

function Open-Browser {
    if (-not (Assert-Docker)) { return }

    $targets = switch ($Global:CurrentMode) {
        "Prod"   { @(@{ Name = $FrontendProdName; Url = "http://localhost:$FrontendProdPort"; Label = "Prod" }) }
        "Dev"    { @(@{ Name = $FrontendDevName;  Url = "http://localhost:$FrontendDevPort";  Label = "Dev"  }) }
        "Hybrid" { @(
            @{ Name = $FrontendProdName; Url = "http://localhost:$FrontendProdPort"; Label = "Prod" }
            @{ Name = $FrontendDevName;  Url = "http://localhost:$FrontendDevPort";  Label = "Dev"  }
        )}
    }

    # Check if any target containers are down and start them first
    $anyDown = $false
    foreach ($t in $targets) {
        $running = docker ps --format "{{.Names}}" | Select-String -Quiet $t.Name
        if (-not $running) { $anyDown = $true }
    }

    if ($anyDown) {
        Type-Info "Containers not running — starting $Global:CurrentMode mode first..."
        Write-Host ""
        Start-Docker
        Write-Host ""
        Start-Sleep -Milliseconds 1500   # brief pause so Docker is fully up before the browser hits it
    }

    foreach ($t in $targets) {
        Play-Sound $Sounds.Nav
        Type-Info "Opening $($t.Label): $($t.Url)"
        Start-Process $t.Url
    }
}

# ============================
#  STEP 7 — KILL PORT
# ============================

function Kill-Port {
    Write-Host ""
    $port = Read-Host "  Enter port number to free"

    if ($port -notmatch '^\d+$') {
        Type-Error "Invalid port."
        return
    }

    $lines = netstat -ano | Select-String ":$port\s"
    $pids  = @()

    foreach ($line in $lines) {
        $parts = ($line -split "\s+")
        $p     = $parts[-1]
        if ($p -match '^\d+$' -and $p -ne "0") { $pids += [int]$p }
    }

    $pids = $pids | Select-Object -Unique

    if ($pids.Count -eq 0) {
        Type-Info "Port $port is already free."
        return
    }

    Play-Sound $Sounds.Alert
    foreach ($pp in $pids) {
        Type-Info "Killing PID $pp on port $port..."
        Stop-Process -Id $pp -Force -ErrorAction SilentlyContinue
    }

    Play-Sound $Sounds.Online
    Type-OK "Port $port is now free."
}

# ============================
#  STEP 4 — MODE SWITCHER
# ============================

function Switch-Mode {
    Play-Sound $Sounds.Nav
    Clear-Host
    Write-Host ""
    Type-Section "  SELECT MODE"
    Write-Host ""
    Write-Host "  1)  Prod   — Nginx build, port $FrontendProdPort" -ForegroundColor White
    Write-Host "  2)  Dev    — Hot reload,   port $FrontendDevPort"  -ForegroundColor White
    Write-Host "  3)  Hybrid — Both running simultaneously"           -ForegroundColor White
    Write-Host ""

    $pick = Read-Host "  Choose mode"

    switch ($pick) {
        "1" { $Global:CurrentMode = "Prod";   Play-Sound $Sounds.Online; Type-OK "Mode set to PROD." }
        "2" { $Global:CurrentMode = "Dev";    Play-Sound $Sounds.Online; Type-OK "Mode set to DEV." }
        "3" { $Global:CurrentMode = "Hybrid"; Play-Sound $Sounds.Online; Type-OK "Mode set to HYBRID." }
        default { Play-Sound $Sounds.Alert; Type-Error "Invalid selection." }
    }

    Start-Sleep -Milliseconds 400
}

# ============================
#  STEP 4 — MAIN MENU
# ============================

function Show-Menu {
    Show-Header

    Write-Host "  DOCKER" -ForegroundColor Yellow
    Write-Host "  1)  Start          ($Global:CurrentMode mode)" -ForegroundColor Cyan
    Write-Host "  2)  Stop           (all containers)"           -ForegroundColor Cyan
    Write-Host "  3)  Restart        ($Global:CurrentMode mode)" -ForegroundColor Cyan
    Write-Host "  4)  Logs           ($Global:CurrentMode)"      -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  CONTROL" -ForegroundColor Yellow
    Write-Host "  5)  Switch Mode    (currently: $Global:CurrentMode)" -ForegroundColor Cyan
    Write-Host "  6)  System Status"                                    -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  TOOLS" -ForegroundColor Yellow
    Write-Host "  7)  Health Scan"    -ForegroundColor Cyan
    Write-Host "  8)  Force Rebuild  (wipe + rebuild from scratch)"    -ForegroundColor Cyan
    Write-Host "  9)  Open Browser   ($Global:CurrentMode frontend)"   -ForegroundColor Cyan
    Write-Host "  10) Kill Port      (free a blocked port)"            -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  0)  Exit" -ForegroundColor Red
    Write-Host ""
}

# ============================
#  ENTRY POINT
# ============================

if (-not (Assert-Docker)) { exit 1 }

Show-BootAnimation

while ($true) {
    Show-Menu

    $input = Read-Host "  Select an option"
    Play-Sound $Sounds.Nav

    switch ($input) {
        "1"  { Start-Docker }
        "2"  { Stop-Docker }
        "3"  { Restart-Docker }
        "4"  { Show-Logs }
        "5"  { Switch-Mode }
        "6"  { Show-SystemStatus }
        "7"  { Show-HealthScan }
        "8"  { Force-Rebuild }
        "9"  { Open-Browser }
        "10" { Kill-Port }
        "0"  {
            Play-Sound $Sounds.Critical
            Type-Write "  Shutting down RAMBO Control Panel... Goodbye, Commander." -Delay 5 -Color DarkGray
            Start-Sleep -Milliseconds 500
            exit
        }
        default { Play-Sound $Sounds.Alert; Type-Error "Invalid selection." }
    }

    if ($input -ne "5") {
        Write-Host ""
        Read-Host "  Press ENTER to return to menu"
    }
}
