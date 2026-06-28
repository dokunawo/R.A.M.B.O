<#
  cmc-daily.ps1  —  Chances Make Champions daily run

  Pulls a fresh MLB slate, prints the results + all five ChatGPT image prompts to
  the console, and exports everything into a readable Word document saved in the
  R.A.M.B.O repo folder (CMC_Daily_<date>.docx).

  USAGE
    .\cmc-daily.ps1                      # today, pull fresh slate, write the doc
    .\cmc-daily.ps1 -Date 2026-06-27     # a specific slate date
    .\cmc-daily.ps1 -SkipPrep            # DON'T re-pull (free) — just read + write doc
    .\cmc-daily.ps1 -Open                # open the doc in Word when done
    .\cmc-daily.ps1 -PropEvents 1        # CHEAP prop-shop test: pull props for 1 game (~4 credits)
    .\cmc-daily.ps1 -SkipProps           # skip the sportsbook-props pull (no Odds API prop credits)

  NOTE: the slate pull hits paid Apify sources. Run it once per day. Use -SkipPrep
        to regenerate the doc from already-pulled data without spending again.
        Sportsbook player props (for prop line shopping) come from The Odds API and
        cost (games x markets) credits per pull — use -PropEvents N to cap a test,
        or -SkipProps to skip. Moneyline line-shop + CLV are FREE (reuse pulled odds).
#>
param(
    [string]$Date = (Get-Date).ToString("yyyy-MM-dd"),
    [string]$Base = "http://localhost:8000",
    [string]$Repo = "C:\Users\dokun\PycharmProjects\R.A.M.B.O",
    [switch]$SkipPrep,
    [int]$PropEvents = 0,                 # 0 = full slate; >0 = cap events (cheap test)
    [switch]$SkipProps,
    [switch]$Open
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

# Windows PowerShell 5.1's Invoke-RestMethod mis-decodes UTF-8 JSON (em-dashes ->
# mojibake). Fetch raw bytes and decode as UTF-8 ourselves.
function Get-Json([string]$Uri, [string]$Method = "GET") {
    $resp = Invoke-WebRequest -Uri $Uri -Method $Method -TimeoutSec 60 -UseBasicParsing
    $bytes = $resp.RawContentStream.ToArray()
    [System.Text.Encoding]::UTF8.GetString($bytes) | ConvertFrom-Json
}

# market key -> display label (ordered so the doc reads HR..ML)
$markets = [ordered]@{
    hr  = "Home Runs"
    hrr = "H+R+RBI"
    sb  = "Stolen Bases"
    k   = "Strikeouts"
    ml  = "Moneyline"
}

function Test-Backend {
    try { Invoke-WebRequest -Uri "$Base/betting/daily-edge?market=hr" -TimeoutSec 5 -UseBasicParsing | Out-Null; return $true }
    catch { return $false }
}

Write-Host ""
Write-Host "===== Chances Make Champions — Daily Edge ($Date) =====" -ForegroundColor Yellow

if (-not (Test-Backend)) {
    Write-Host "ERROR: backend not reachable at $Base." -ForegroundColor Red
    Write-Host "       The RAMBO backend runs in Docker on :8000 — start the container and retry." -ForegroundColor Red
    exit 1
}

# 1) Pull the fresh slate (paid) unless skipped --------------------------------
if ($SkipPrep) {
    Write-Host "Skipping slate pull (-SkipPrep) — reading existing data." -ForegroundColor DarkGray
} else {
    Write-Host "Pulling fresh slate (paid Apify sources)..." -ForegroundColor Cyan
    try {
        $prep = Get-Json "$Base/betting/prep?date=$Date" "POST"
        Write-Host "Slate prepped." -ForegroundColor Green
    } catch {
        Write-Host "ERROR pulling slate: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
    # Sportsbook player props (The Odds API per-event) — for prop line shopping.
    # COSTS Odds API credits (games x markets). -PropEvents N caps a cheap test.
    if ($SkipProps) {
        Write-Host "Skipping sportsbook-props pull (-SkipProps)." -ForegroundColor DarkGray
    } else {
        $propUri = "$Base/betting/pull-book-props?date=$Date"
        if ($PropEvents -gt 0) { $propUri += "&max_events=$PropEvents" }
        $scope = if ($PropEvents -gt 0) { "$PropEvents event(s)" } else { "full slate" }
        Write-Host "Pulling sportsbook props ($scope, paid Odds API credits)..." -ForegroundColor Cyan
        try {
            $bp = Get-Json $propUri "POST"
            Write-Host ("Book props pulled: {0} events, resolved {1} players." -f $bp.pulled, $bp.resolved) -ForegroundColor Green
        } catch {
            Write-Host "WARN pulling book props: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

# 2) Gather per-market results + prompts ---------------------------------------
$results = @()
foreach ($m in $markets.Keys) {
    $edge = Get-Json "$Base/betting/daily-edge?market=$m&date=$Date"   # real +EV plays only
    $slip = Get-Json "$Base/betting/slip?market=$m&date=$Date"          # roster + prompt (incl. near-misses)
    $results += [pscustomobject]@{
        Key   = $m
        Label = $markets[$m]
        Edge  = $edge
        Slip  = $slip
    }
}

# Boards (read already-pulled data; free under -SkipPrep)
$playerWatch    = Get-Json "$Base/betting/player-watch?date=$Date"
$moneylineBoard = Get-Json "$Base/betting/moneyline-board?date=$Date"
$strikeoutWatch = Get-Json "$Base/betting/strikeout-watch?date=$Date"
$hitsTbWatch    = Get-Json "$Base/betting/hits-tb-watch?date=$Date"

# New: line shopping (best ML price per book, FREE), Pick6-vs-book prop shop, and
# CLV (how the close moved vs our leans). All read-only over already-pulled data.
$lineShop = Get-Json "$Base/betting/line-shop?date=$Date"
$propShop = Get-Json "$Base/betting/prop-shop?date=$Date"
$clv      = Get-Json "$Base/betting/clv?date=$Date"

# 3) Print to console ----------------------------------------------------------
foreach ($r in $results) {
    Write-Host ""
    Write-Host ("----- {0} ({1}) -----" -f $r.Label, $r.Key) -ForegroundColor Cyan
    Write-Host ("Real +EV plays: {0}" -f $r.Edge.count)
    if ($r.Slip.players.Count -gt 0) {
        foreach ($p in $r.Slip.players) {
            if ($r.Key -eq "ml") {
                Write-Host ("  {0}. {1} vs {2} — {3} — model {4}% / lean {5}%" -f $p.rank, $p.team, $p.opponent, $p.pick, $p.model_pct, $p.edge_pct)
            } else {
                Write-Host ("  {0}. {1} ({2} vs {3}) — {4} — model {5}% / edge {6}%" -f $p.rank, $p.name, $p.team, $p.opponent, $p.pick, $p.model_pct, $p.edge_pct)
            }
        }
    } else {
        Write-Host "  (no plays available today)" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "===== ChatGPT image prompts =====" -ForegroundColor Yellow
foreach ($r in $results) {
    Write-Host ""
    Write-Host ("##### {0} #####" -f $r.Label) -ForegroundColor Magenta
    Write-Host $r.Slip.prompt
}

Write-Host ""
Write-Host "##### PLAYER WATCH #####" -ForegroundColor Magenta
Write-Host $playerWatch.prompt
Write-Host ""
Write-Host "##### MONEYLINE BOARD #####" -ForegroundColor Magenta
Write-Host $moneylineBoard.prompt
Write-Host ""
Write-Host "##### STRIKEOUT WATCH #####" -ForegroundColor Magenta
Write-Host $strikeoutWatch.prompt
Write-Host ""
Write-Host "##### HITS & TOTAL BASES #####" -ForegroundColor Magenta
Write-Host $hitsTbWatch.prompt

# 3b) New analytics: line shopping, prop shop, CLV -----------------------------
Write-Host ""
Write-Host ("----- MONEYLINE LINE SHOPPING ({0} games) -----" -f $lineShop.games.Count) -ForegroundColor Cyan
foreach ($g in $lineShop.games) {
    $h = $g.sides.home; $a = $g.sides.away
    Write-Host ("  {0}@{1} — HOME best {2} @{3} (val {4}) | AWAY best {5} @{6} (val {7})" -f `
        $g.away, $g.home, $h.best_price, $h.best_book, $h.edge, $a.best_price, $a.best_book, $a.edge)
}

Write-Host ""
$plus = $propShop.legs | Where-Object { $_.value -gt 0 }
Write-Host ("----- PROP SHOP — Pick6 vs sportsbook ({0} compared, {1} +EV) -----" -f $propShop.summary.compared, $propShop.summary.plus_ev) -ForegroundColor Cyan
if ($propShop.legs.Count -eq 0) {
    Write-Host "  (no comparable book props — pull them with a prop-events run)" -ForegroundColor DarkGray
} else {
    foreach ($l in ($propShop.legs | Select-Object -First 12)) {
        Write-Host ("  {0} {1} {2}+ — Pick6 x{3} (be {4}) vs book {5} — {6} [{7}]" -f `
            $l.player, $l.market, $l.line, $l.pick6_multiplier, $l.pick6_breakeven, $l.book_consensus_over, $l.value, $l.verdict)
    }
}

Write-Host ""
Write-Host "----- CLOSING LINE VALUE (moneyline leans) -----" -ForegroundColor Cyan
if ($clv.summary.graded -gt 0) {
    Write-Host ("  Graded {0} leans · beat the close {1} ({2}) · avg CLV {3} pts" -f `
        $clv.summary.graded, $clv.summary.beat_close, $clv.summary.beat_close_rate, $clv.summary.avg_clv_pts)
} else {
    Write-Host "  (no graded leans yet — CLV fills in once closing lines are captured)" -ForegroundColor DarkGray
}

# 4) Export to a Word document -------------------------------------------------
$outPath = Join-Path $Repo ("CMC_Daily_{0}.docx" -f $Date)
Write-Host ""
Write-Host "Writing Word doc -> $outPath" -ForegroundColor Cyan

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$doc  = $word.Documents.Add()

# Whole document: Consolas 9, single line spacing, NO space before/after paragraphs.
$normal = $doc.Styles.Item("Normal")
$normal.Font.Name = "Consolas"
$normal.Font.Size = 9
$normal.ParagraphFormat.SpaceBefore   = 0
$normal.ParagraphFormat.SpaceAfter    = 0
$normal.ParagraphFormat.LineSpacingRule = 0   # wdLineSpaceSingle

$sel = $word.Selection
$sel.Style = $normal

# Every line is Consolas 9, zero spacing; $bold just toggles weight for headers.
function Add-Line([string]$text, [bool]$bold = $false) {
    $sel.Font.Bold = [int]$bold
    if ($text) { $sel.TypeText($text) }
    $sel.TypeParagraph()
    $sel.Font.Bold = 0
}

Add-Line "CHANCES MAKE CHAMPIONS — DAILY EDGE" $true
Add-Line ("Slate date: {0}   ·   Generated: {1}" -f $Date, (Get-Date -Format "yyyy-MM-dd HH:mm"))
Add-Line "Data-only tool. Pick6 single legs are structurally -EV (shown as skips/near-misses); moneyline are honest leans, not guaranteed winners."

foreach ($r in $results) {
    Add-Line ""                                   # one blank line BETWEEN market sections
    $prov = $r.Edge.provenance
    Add-Line ("{0} ({1})  —  Real +EV plays: {2}  ·  {3}  ·  as of {4}" -f $r.Label, $r.Key, $r.Edge.count, $prov.product, $prov.data_as_of) $true
    if ($prov.stale) { Add-Line ("WARNING: {0}" -f $prov.warning) }

    if ($r.Slip.players.Count -gt 0) {
        foreach ($p in $r.Slip.players) {
            if ($r.Key -eq "ml") {
                Add-Line ("{0}. {1} vs {2} — {3} — model {4}% / lean {5}%" -f $p.rank, $p.team, $p.opponent, $p.pick, $p.model_pct, $p.edge_pct)
            } else {
                Add-Line ("{0}. {1} ({2} vs {3}) — {4} — model {5}% / edge {6}%" -f $p.rank, $p.name, $p.team, $p.opponent, $p.pick, $p.model_pct, $p.edge_pct)
            }
        }
    } else {
        Add-Line "(no plays available today)"
    }

    Add-Line "ChatGPT image prompt:" $true
    foreach ($line in ($r.Slip.prompt -split "`n")) { Add-Line $line }
}

Add-Line ""
Add-Line ("PLAYER WATCH — top {0} HR chances" -f $playerWatch.count) $true
foreach ($line in ($playerWatch.prompt -split "`n")) { Add-Line $line }

Add-Line ""
Add-Line ("MONEYLINE BOARD — {0} games" -f $moneylineBoard.count) $true
foreach ($line in ($moneylineBoard.prompt -split "`n")) { Add-Line $line }

Add-Line ""
Add-Line ("STRIKEOUT WATCH — top {0} starters" -f $strikeoutWatch.count) $true
foreach ($line in ($strikeoutWatch.prompt -split "`n")) { Add-Line $line }

Add-Line ""
Add-Line ("HITS & TOTAL BASES — top {0} hitters" -f $hitsTbWatch.count) $true
foreach ($line in ($hitsTbWatch.prompt -split "`n")) { Add-Line $line }

Add-Line ""
Add-Line ("MONEYLINE LINE SHOPPING — {0} games (best price per side across books)" -f $lineShop.games.Count) $true
foreach ($g in $lineShop.games) {
    $h = $g.sides.home; $a = $g.sides.away
    Add-Line ("{0}@{1} — HOME {2} @{3} (val {4}) | AWAY {5} @{6} (val {7})" -f `
        $g.away, $g.home, $h.best_price, $h.best_book, $h.edge, $a.best_price, $a.best_book, $a.edge)
}

Add-Line ""
Add-Line ("PROP SHOP — Pick6 vs sportsbook ({0} compared, {1} +EV)" -f $propShop.summary.compared, $propShop.summary.plus_ev) $true
if ($propShop.legs.Count -eq 0) {
    Add-Line "(no comparable book props — run with -PropEvents to pull sportsbook props)"
} else {
    foreach ($l in $propShop.legs) {
        Add-Line ("{0} {1} {2}+ — Pick6 x{3} (breakeven {4}) vs book fair {5} — value {6} [{7}] · best {8}" -f `
            $l.player, $l.market, $l.line, $l.pick6_multiplier, $l.pick6_breakeven, $l.book_consensus_over, $l.value, $l.verdict, $l.best_book)
    }
}

Add-Line ""
Add-Line "CLOSING LINE VALUE — moneyline leans vs the close" $true
if ($clv.summary.graded -gt 0) {
    Add-Line ("Graded {0} leans · beat the close {1} (rate {2}) · avg CLV {3} pts" -f `
        $clv.summary.graded, $clv.summary.beat_close, $clv.summary.beat_close_rate, $clv.summary.avg_clv_pts)
} else {
    Add-Line "(no graded leans yet — CLV fills in once closing lines are captured over the day)"
}

# wdFormatDocumentDefault = 16  (.docx). SaveAs2 takes plain args (avoids the
# PS 5.1 [ref] PSObject-cast bug).
$doc.SaveAs2([string]$outPath, [int]16)
$doc.Close()
$word.Quit()
[System.Runtime.Interopservices.Marshal]::ReleaseComObject($sel)  | Out-Null
[System.Runtime.Interopservices.Marshal]::ReleaseComObject($doc)  | Out-Null
[System.Runtime.Interopservices.Marshal]::ReleaseComObject($word) | Out-Null
[GC]::Collect(); [GC]::WaitForPendingFinalizers()

Write-Host "Done. Saved: $outPath" -ForegroundColor Green
if ($Open) { Start-Process $outPath }
