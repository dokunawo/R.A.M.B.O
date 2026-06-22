$projectRoot = "C:\Users\dokun\PycharmProjects\R.A.M.B.O"
$soundsPath  = Join-Path $projectRoot "sounds"

if (-not (Test-Path $soundsPath)) {
    New-Item -ItemType Directory -Path $soundsPath | Out-Null
}

$sampleRate = 44100
$channels = 2
$bitsPerSample = 16

function Clamp {
    param($v)
    if ($v -gt 1.0) { return 1.0 }
    if ($v -lt -1.0) { return -1.0 }
    return $v
}

function New-StereoWav {
    param(
        [string]$Path,
        [int]$DurationMs,
        [scriptblock]$SampleFunc
    )

    $totalSamples = [int]($sampleRate * $DurationMs / 1000.0)
    $blockAlign = $channels * ($bitsPerSample / 8)
    $byteRate = $sampleRate * $blockAlign
    $dataSize = $totalSamples * $blockAlign
    $riffSize = 36 + $dataSize

    $fs = [System.IO.File]::Open($Path, [System.IO.FileMode]::Create)
    $bw = New-Object System.IO.BinaryWriter($fs)

    # RIFF header
    $bw.Write([System.Text.Encoding]::ASCII.GetBytes("RIFF"))
    $bw.Write([System.BitConverter]::GetBytes([int]$riffSize))
    $bw.Write([System.Text.Encoding]::ASCII.GetBytes("WAVE"))

    # fmt chunk
    $bw.Write([System.Text.Encoding]::ASCII.GetBytes("fmt "))
    $bw.Write([System.BitConverter]::GetBytes([int]16))
    $bw.Write([System.BitConverter]::GetBytes([int16]1))
    $bw.Write([System.BitConverter]::GetBytes([int16]$channels))
    $bw.Write([System.BitConverter]::GetBytes([int]$sampleRate))
    $bw.Write([System.BitConverter]::GetBytes([int]$byteRate))
    $bw.Write([System.BitConverter]::GetBytes([int16]$blockAlign))
    $bw.Write([System.BitConverter]::GetBytes([int16]$bitsPerSample))

    # data chunk
    $bw.Write([System.Text.Encoding]::ASCII.GetBytes("data"))
    $bw.Write([System.BitConverter]::GetBytes([int]$dataSize))

    for ($n = 0; $n -lt $totalSamples; $n++) {
        $t = $n / [double]$sampleRate

        $vals = & $SampleFunc $t $n $totalSamples
        $left  = Clamp $vals[0]
        $right = Clamp $vals[1]

        $bw.Write([System.BitConverter]::GetBytes([int16]([int]($left  * 32767))))
        $bw.Write([System.BitConverter]::GetBytes([int16]([int]($right * 32767))))
    }

    $bw.Close()
    $fs.Close()
}

# -------------------------
# nav.wav – short UI tap
# -------------------------
New-StereoWav -Path (Join-Path $soundsPath "nav.wav") -DurationMs 120 -SampleFunc {
    param($t, $n, $total)

    $freq = 900 + 80 * $t
    $env  = [math]::Exp(-12 * $t)
    $pan  = 0.5 * [math]::Sin(2 * [math]::PI * 4 * $t)

    $base = [math]::Sin(2 * [math]::PI * $freq * $t)
    $harm = 0.3 * [math]::Sin(2 * [math]::PI * ($freq * 2.2) * $t)
    $sig  = ($base + $harm) * $env * 0.6

    $left  = $sig * (0.5 - $pan)
    $right = $sig * (0.5 + $pan)
    return @($left, $right)
}

Write-Host "nav.wav generated successfully!" -ForegroundColor Green

# -------------------------
# alert.wav – descending warning
# -------------------------
New-StereoWav -Path (Join-Path $soundsPath "alert.wav") -DurationMs 280 -SampleFunc {
    param($t, $n, $total)

    $freqStart = 700.0
    $freqEnd   = 420.0
    $freq = $freqStart + ($freqEnd - $freqStart) * $t

    $env  = [math]::Exp(-5 * $t)
    $pan  = 0.6 * [math]::Sin(2 * [math]::PI * 2 * $t)

    $base = [math]::Sin(2 * [math]::PI * $freq * $t)
    $harm = 0.25 * [math]::Sin(2 * [math]::PI * ($freq * 1.5) * $t)
    $sig  = ($base + $harm) * $env * 0.7

    $left  = $sig * (0.5 - $pan)
    $right = $sig * (0.5 + $pan)
    return @($left, $right)
}

Write-Host "alert.wav generated!" -ForegroundColor Green

# -------------------------
# hud_boot.wav – rising sweep
# -------------------------
New-StereoWav -Path (Join-Path $soundsPath "hud_boot.wav") -DurationMs 1600 -SampleFunc {
    param($t, $n, $total)

    $freqStart = 220.0
    $freqEnd   = 1600.0
    $freq = $freqStart + ($freqEnd - $freqStart) * ($t * $t)

    $env  = [math]::Min(1.0, $t * 3.0) * [math]::Exp(-1.5 * [math]::Max(0, $t - 0.7))
    $pan  = 0.7 * [math]::Sin(2 * [math]::PI * 0.7 * $t)

    $base = [math]::Sin(2 * [math]::PI * $freq * $t)
    $harm = 0.35 * [math]::Sin(2 * [math]::PI * ($freq * 2.3) * $t)
    $sig  = ($base + $harm) * $env * 0.6

    $left  = $sig * (0.5 - $pan)
    $right = $sig * (0.5 + $pan)
    return @($left, $right)
}

Write-Host "hud_boot.wav generated!" -ForegroundColor Green

# -------------------------
# online.wav – soft chime
# -------------------------
New-StereoWav -Path (Join-Path $soundsPath "online.wav") -DurationMs 350 -SampleFunc {
    param($t, $n, $total)

    $freq1 = 880.0
    $freq2 = 1320.0
    $env   = [math]::Exp(-4 * $t)
    $pan   = 0.4 * [math]::Sin(2 * [math]::PI * 1.5 * $t)

    $tone1 = [math]::Sin(2 * [math]::PI * $freq1 * $t)
    $tone2 = [math]::Sin(2 * [math]::PI * $freq2 * $t)
    $sig   = ($tone1 + 0.6 * $tone2) * $env * 0.5

    $left  = $sig * (0.5 - $pan)
    $right = $sig * (0.5 + $pan)
    return @($left, $right)
}

Write-Host "online.wav generated!" -ForegroundColor Green

# -------------------------
# critical.wav – dual-tone alarm
# -------------------------
New-StereoWav -Path (Join-Path $soundsPath "critical.wav") -DurationMs 650 -SampleFunc {
    param($t, $n, $total)

    $freqA = 520.0
    $freqB = 390.0
    $pulse = 0.5 * (1.0 + [math]::Sign([math]::Sin(2 * [math]::PI * 3 * $t)))
    $env   = [math]::Exp(-2.5 * $t)
    $pan   = 0.8 * [math]::Sin(2 * [math]::PI * 1.2 * $t)

    $toneA = [math]::Sin(2 * [math]::PI * $freqA * $t)
    $toneB = [math]::Sin(2 * [math]::PI * $freqB * $t)
    $sig   = (($toneA * $pulse) + ($toneB * (1 - $pulse))) * $env * 0.7

    $left  = $sig * (0.5 - $pan)
    $right = $sig * (0.5 + $pan)
    return @($left, $right)
}

Write-Host "critical.wav generated!" -ForegroundColor Green

# -------------------------
# startup.wav – full reactor boot
# -------------------------
New-StereoWav -Path (Join-Path $soundsPath "startup.wav") -DurationMs 4500 -SampleFunc {
    param($t, $n, $total)

    $lowFreq   = 80.0
    $sweepStart = 260.0
    $sweepEnd   = 1800.0

    $sweepPos = $t
    $sweepFreq = $sweepStart + ($sweepEnd - $sweepStart) * ($sweepPos * $sweepPos)

    $lowHum   = [math]::Sin(2 * [math]::PI * $lowFreq * $t)
    $sweep    = [math]::Sin(2 * [math]::PI * $sweepFreq * $t)
    $shimmer  = 0.4 * [math]::Sin(2 * [math]::PI * ($sweepFreq * 2.5) * $t)

    $riseEnv  = [math]::Min(1.0, $t * 1.2)
    $fallEnv  = [math]::Exp(-1.2 * [math]::Max(0, $t - 2.5))
    $env      = $riseEnv * $fallEnv

    $pan      = 0.7 * [math]::Sin(2 * [math]::PI * 0.35 * $t)

    $sig = (0.6 * $lowHum + 0.7 * $sweep + $shimmer) * $env * 0.6

    $left  = $sig * (0.5 - $pan)
    $right = $sig * (0.5 + $pan)
    return @($left, $right)
}

Write-Host "startup.wav generated!" -ForegroundColor Green
