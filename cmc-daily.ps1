<#
  cmc-daily.ps1  —  Chances Make Champions daily run

  Pulls a fresh MLB slate, prints the results + all five ChatGPT image prompts to
  the console, and exports everything into a readable Word document saved in the
  R.A.M.B.O repo folder (CMC_Daily_<date>.docx).

  The Word doc renders every data section as a TABLE with a bold section header
  (landscape page so the wide Strikeout 1+..10+ ladder fits). The long ChatGPT
  image-gen prompts are collected in an "IMAGE PROMPTS" appendix at the end so
  they don't clutter the tables.

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

# PrizePicks board markets (distinct taxonomy from the EV markets above). Keys are
# the API market codes; "H+R+RBI" must be URL-encoded (+ means space in a query).
$ppMarkets = [ordered]@{
    HR        = "Home Runs"
    SO        = "Strikeouts"
    TB        = "Total Bases"
    H         = "Hits"
    "H+R+RBI" = "H+R+RBI"
    SB        = "Stolen Bases"
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
        # PrizePicks props come from the free public API, with a paid Apify actor as an
        # auto-fallback (when PRIZEPICKS_APIFY_ACTOR is set). If both yield 0, the prop
        # boards (HR/HRR/SB/K + PrizePicks confidence/tiers) serve stale/empty — warn loudly.
        if ([int]$prep.props -le 0) {
            Write-Host ("WARNING: PrizePicks props pulled 0 — the source is likely down " +
                "(free API + paid fallback both empty). Prop boards (Home Runs / H+R+RBI / " +
                "Stolen Bases / Strikeouts + PrizePicks confidence/tiers) will be STALE or EMPTY " +
                "until it's back.") -ForegroundColor Yellow
        }
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
$strikeoutWatch = Get-Json "$Base/betting/strikeout-watch?date=$Date&limit=0&min_starts=0"  # every starter
$hitsTbWatch    = Get-Json "$Base/betting/hits-tb-watch?date=$Date"

# New: line shopping (best ML price per book, FREE), Pick6-vs-book prop shop, and
# CLV (how the close moved vs our leans). All read-only over already-pulled data.
$lineShop = Get-Json "$Base/betting/line-shop?date=$Date"
$propShop = Get-Json "$Base/betting/prop-shop?date=$Date"
$clv      = Get-Json "$Base/betting/clv?date=$Date"

# PrizePicks boards (model-confidence + goblin/standard/demon tiers) per market.
# Read-only over already-pulled PrizePicks props — free, and work under -SkipPrep.
$ppConfidence = [ordered]@{}
$ppTiers      = [ordered]@{}
foreach ($mk in $ppMarkets.Keys) {
    $enc = [uri]::EscapeDataString([string]$mk)        # "H+R+RBI" -> "H%2BR%2BRBI"
    try { $ppConfidence[$mk] = Get-Json "$Base/betting/prizepicks?market=$enc&date=$Date" }
    catch { $ppConfidence[$mk] = $null; Write-Host ("WARN prizepicks {0}: {1}" -f $mk, $_.Exception.Message) -ForegroundColor Yellow }
    try { $ppTiers[$mk] = Get-Json "$Base/betting/prizepicks-tiers?market=$enc&date=$Date" }
    catch { $ppTiers[$mk] = $null; Write-Host ("WARN prizepicks-tiers {0}: {1}" -f $mk, $_.Exception.Message) -ForegroundColor Yellow }
}

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

# 3c) PrizePicks confidence + tiers -------------------------------------------
Write-Host ""
Write-Host "===== PrizePicks Confidence =====" -ForegroundColor Yellow
foreach ($mk in $ppMarkets.Keys) {
    $b = $ppConfidence[$mk]
    Write-Host ("----- {0} ({1}) — {2} legs -----" -f $ppMarkets[$mk], $mk, ($(if ($b) { $b.count } else { 0 }))) -ForegroundColor Cyan
    if ($b -and $b.rows.Count -gt 0) {
        foreach ($x in ($b.rows | Select-Object -First 11)) {
            Write-Host ("  {0}. {1} ({2} vs {3}) — {4} {5} — {6}%" -f $x.rank, $x.name, $x.team, $x.opponent, $x.side.ToUpper(), $x.line, $x.model_pct)
        }
    } else { Write-Host "  (none)" -ForegroundColor DarkGray }
}

Write-Host ""
Write-Host "===== PrizePicks Tiers (goblin / standard / demon) =====" -ForegroundColor Yellow
foreach ($mk in $ppMarkets.Keys) {
    $b = $ppTiers[$mk]
    Write-Host ("----- {0} ({1}) — {2} players -----" -f $ppMarkets[$mk], $mk, ($(if ($b) { $b.count } else { 0 }))) -ForegroundColor Cyan
    if ($b -and $b.rows.Count -gt 0) {
        foreach ($x in ($b.rows | Select-Object -First 11)) {
            $segs = foreach ($t in @("goblin","standard","demon")) {
                if ($x.tiers.$t) { "{0} {1} ({2}%)" -f $t, $x.tiers.$t.line, $x.tiers.$t.model_pct }
            }
            Write-Host ("  {0} ({1} vs {2}) — {3}" -f $x.name, $x.team, $x.opponent, ($segs -join "  ·  "))
        }
    } else { Write-Host "  (none)" -ForegroundColor DarkGray }
}

# 4) Export to a Word document (tables + headers) ------------------------------
$outPath = Join-Path $Repo ("CMC_Daily_{0}.docx" -f $Date)
Write-Host ""
Write-Host "Writing Word doc -> $outPath" -ForegroundColor Cyan

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$doc  = $word.Documents.Add()

# Landscape so the wide Strikeout 1+..10+ ladder fits comfortably.
$doc.PageSetup.Orientation = 1            # wdOrientLandscape

# Whole document: Consolas 9, single line spacing, NO space before/after paragraphs.
$normal = $doc.Styles.Item("Normal")
$normal.Font.Name = "Consolas"
$normal.Font.Size = 9
$normal.ParagraphFormat.SpaceBefore   = 0
$normal.ParagraphFormat.SpaceAfter    = 0
$normal.ParagraphFormat.LineSpacingRule = 0   # wdLineSpaceSingle

$sel = $word.Selection
$sel.Style = $normal

# A plain paragraph line. $bold toggles weight (used for section headers).
function Add-Line([string]$text, [bool]$bold = $false) {
    $sel.Font.Bold = [int]$bold
    if ($text) { $sel.TypeText($text) }
    $sel.TypeParagraph()
    $sel.Font.Bold = 0
}

# A bold section header (so you always know which section you're looking at).
function Add-Header([string]$text) {
    $sel.Font.Size = 11
    Add-Line $text $true
    $sel.Font.Size = 9
}

# Insert a real Word table at the end of the document. $Headers is a string[];
# $Rows is an array of rows, each row a string[] of the same length as $Headers.
# The header row is bold; the table has borders and fits to the page width.
# Green heatmap: shade a cell by the percentage it contains (near-white at 0%,
# deep green at 100%), white text on the darkest cells. No %, no shading.
function Set-HeatShade($cell, [string]$text) {
    if ($text -notmatch '(\d+(?:\.\d+)?)\s*%') { return }
    $t = [double]$matches[1] / 100.0
    if ($t -lt 0) { $t = 0.0 } elseif ($t -gt 1) { $t = 1.0 }
    $R = [int][math]::Round(235 * (1 - $t))
    $G = [int][math]::Round(247 - 138 * $t)
    $B = [int][math]::Round(235 - 191 * $t)
    $cell.Shading.BackgroundPatternColor = $R + ($G * 256) + ($B * 65536)   # VBA RGB order
    if ($t -gt 0.55) { $cell.Range.Font.Color = 16777215 }                  # wdColorWhite
}

# $HeatCols = 1-based column numbers whose cells get the green probability heatmap.
function Add-Table([string[]]$Headers, $Rows, [int[]]$HeatCols = @()) {
    $rowsArr = @($Rows)
    $nCols = $Headers.Count
    if ($rowsArr.Count -eq 0) { Add-Line "(none)"; return }
    $nRows = $rowsArr.Count + 1

    $rng = $doc.Content
    $rng.Collapse(0)                       # wdCollapseEnd — append at doc end
    $table = $doc.Tables.Add($rng, $nRows, $nCols)
    $table.Borders.Enable = $true
    $table.Range.Font.Name = "Consolas"
    $table.Range.Font.Size = 8
    $table.Range.ParagraphFormat.SpaceAfter = 0

    for ($c = 0; $c -lt $nCols; $c++) {
        $cell = $table.Cell(1, $c + 1)
        $cell.Range.Text = [string]$Headers[$c]
        $cell.Range.Font.Bold = 1
    }
    for ($r = 0; $r -lt $rowsArr.Count; $r++) {
        $cells = @($rowsArr[$r])
        for ($c = 0; $c -lt $nCols; $c++) {
            $v = if ($c -lt $cells.Count -and $null -ne $cells[$c]) { [string]$cells[$c] } else { "" }
            $cell = $table.Cell($r + 2, $c + 1)
            $cell.Range.Text = $v
            if ($HeatCols -contains ($c + 1)) { Set-HeatShade $cell $v }
        }
    }
    $table.AutoFitBehavior(2)              # wdAutoFitWindow — fit to page width

    # Move the cursor past the table so subsequent content appends after it.
    $sel.Start = $doc.Content.End
    $sel.End   = $doc.Content.End
    $sel.TypeParagraph()
}

# American-odds formatting with an explicit sign (+150 / -120).
function Fmt-Odds($x) {
    if ($null -eq $x -or $x -eq "") { return "" }
    $n = [int]$x
    if ($n -gt 0) { return "+$n" } else { return "$n" }
}

Add-Header "CHANCES MAKE CHAMPIONS — DAILY EDGE"
Add-Line ("Slate date: {0}   ·   Generated: {1}" -f $Date, (Get-Date -Format "yyyy-MM-dd HH:mm"))
Add-Line "Data-only tool. Pick6 single legs are structurally -EV (shown as skips/near-misses); moneyline are honest leans, not guaranteed winners."

# --- Per-market plays (one table per market) ----------------------------------
foreach ($r in $results) {
    Add-Line ""
    $prov = $r.Edge.provenance
    Add-Header ("{0} ({1})  —  Real +EV plays: {2}  ·  {3}  ·  as of {4}" -f $r.Label, $r.Key, $r.Edge.count, $prov.product, $prov.data_as_of)
    if ($prov.stale) { Add-Line ("WARNING: {0}" -f $prov.warning) }

    if ($r.Slip.players.Count -gt 0) {
        if ($r.Key -eq "ml") {
            $rows = foreach ($p in $r.Slip.players) {
                ,@($p.rank, $p.team, $p.opponent, $p.pick, "$($p.model_pct)%", "$($p.edge_pct)%")
            }
            Add-Table @("#","Team","Opp","Pick","Model","Lean") $rows @(5)
        } else {
            $rows = foreach ($p in $r.Slip.players) {
                ,@($p.rank, $p.name, $p.team, $p.opponent, $p.pick, "$($p.model_pct)%", "$($p.edge_pct)%")
            }
            Add-Table @("#","Player","Team","Opp","Pick","Model","Edge") $rows @(6)
        }
    } else {
        Add-Line "(no plays available today)"
    }
}

# --- Player Watch (HR board) --------------------------------------------------
Add-Line ""
Add-Header ("PLAYER WATCH — top {0} HR chances" -f $playerWatch.count)
if ($playerWatch.rows.Count -gt 0) {
    $rows = foreach ($x in $playerWatch.rows) {
        $nm = if ($x.is_lean) { "$($x.name) *" } else { $x.name }
        ,@($x.rank, $nm, $x.team, $x.pitcher, "$($x.hr_pct)%", $x.venue, ("{0:+0;-0;0}" -f [int]$x.env_pct) + "%", $x.form)
    }
    Add-Table @("#","Player (*=CMC lean)","Team","vs SP","HR%","Venue","Env","Form") $rows @(5)
} else { Add-Line "(no home-run board available today)" }

# --- Moneyline Board ----------------------------------------------------------
Add-Line ""
Add-Header ("MONEYLINE BOARD — {0} games" -f $moneylineBoard.count)
if ($moneylineBoard.rows.Count -gt 0) {
    $rows = foreach ($x in $moneylineBoard.rows) {
        $lean = if ($x.lean_side) { "$($x.lean_side) +$($x.lean_pct)%" } else { "—" }
        ,@($x.rank, $x.away, (Fmt-Odds $x.away_price), $x.home, (Fmt-Odds $x.home_price),
           "$($x.model_home_pct)%", "$($x.model_away_pct)%", $lean)
    }
    Add-Table @("#","Away","Away ML","Home","Home ML","Mdl Home","Mdl Away","Lean") $rows @(6,7)
} else { Add-Line "(no moneyline board available today)" }

# --- Strikeout Watch (full 1+..10+ ladder) ------------------------------------
Add-Line ""
Add-Header ("STRIKEOUT WATCH — all {0} probable starters (alt-K ladder, ranked by P(9+ K))" -f $strikeoutWatch.count)
if ($strikeoutWatch.rows.Count -gt 0) {
    $rows = foreach ($x in $strikeoutWatch.rows) {
        $ladder = for ($j = 1; $j -le 10; $j++) { "$($x."p$j")%" }
        ,(@($x.rank, $x.name, $x.team, $x.opponent, $x.k_rate, [math]::Round([double]$x.batters_faced), $x.k_mean) + $ladder)
    }
    $hdr = @("#","Pitcher","Team","Opp","K Rate","BF","Proj") + (1..10 | ForEach-Object { "$_+" })
    Add-Table $hdr $rows (8..17)
} else { Add-Line "(no probable starters available yet)" }

# --- Hits & Total Bases -------------------------------------------------------
Add-Line ""
Add-Header ("HITS & TOTAL BASES — top {0} hitters" -f $hitsTbWatch.count)
if ($hitsTbWatch.rows.Count -gt 0) {
    $rows = foreach ($x in $hitsTbWatch.rows) {
        ,@($x.rank, $x.name, $x.team, $x.opponent, "$($x.p_hit)%", "$($x.p_tb2)%", $x.hit_mean, $x.tb_mean, $x.form)
    }
    Add-Table @("#","Player","Team","Opp","1+ Hit","2+ TB","Hit Mean","TB Mean","Form") $rows @(5,6)
} else { Add-Line "(no hits/TB board available today)" }

# --- Moneyline line shopping --------------------------------------------------
Add-Line ""
Add-Header ("MONEYLINE LINE SHOPPING — {0} games (best price per side across books)" -f $lineShop.games.Count)
if ($lineShop.games.Count -gt 0) {
    $rows = foreach ($g in $lineShop.games) {
        $h = $g.sides.home; $a = $g.sides.away
        ,@(("{0}@{1}" -f $g.away, $g.home), (Fmt-Odds $h.best_price), $h.best_book, $h.edge,
           (Fmt-Odds $a.best_price), $a.best_book, $a.edge)
    }
    Add-Table @("Matchup","Home Best","Home Book","Home Val","Away Best","Away Book","Away Val") $rows
} else { Add-Line "(no line-shop games today)" }

# --- Prop shop (Pick6 vs sportsbook) ------------------------------------------
Add-Line ""
Add-Header ("PROP SHOP — Pick6 vs sportsbook ({0} compared, {1} +EV)" -f $propShop.summary.compared, $propShop.summary.plus_ev)
if ($propShop.legs.Count -gt 0) {
    $rows = foreach ($l in $propShop.legs) {
        ,@($l.player, $l.market, "$($l.line)+", "x$($l.pick6_multiplier)", $l.pick6_breakeven,
           $l.book_consensus_over, $l.value, $l.verdict, $l.best_book)
    }
    Add-Table @("Player","Market","Line","Pick6","Breakeven","Book Fair","Value","Verdict","Best Book") $rows
} else { Add-Line "(no comparable book props — run with -PropEvents to pull sportsbook props)" }

# --- Closing line value -------------------------------------------------------
Add-Line ""
Add-Header "CLOSING LINE VALUE — moneyline leans vs the close"
if ($clv.summary.graded -gt 0) {
    $s = $clv.summary
    Add-Table @("Graded","Beat Close","Beat Rate","Avg CLV (pts)") @(
        ,@($s.graded, $s.beat_close, $s.beat_close_rate, $s.avg_clv_pts)
    )
} else { Add-Line "(no graded leans yet — CLV fills in once closing lines are captured over the day)" }

# --- PrizePicks Confidence (per-market subtables) -----------------------------
Add-Line ""
Add-Header "PRIZEPICKS CONFIDENCE — model probability per pick (favored side)"
foreach ($mk in $ppMarkets.Keys) {
    $b = $ppConfidence[$mk]
    Add-Line ""
    Add-Line ("{0} ({1}) — {2} legs" -f $ppMarkets[$mk], $mk, ($(if ($b) { $b.count } else { 0 }))) $true
    if ($b -and $b.rows.Count -gt 0) {
        $rows = foreach ($x in $b.rows) {
            ,@($x.rank, $x.name, $x.team, $x.opponent, $x.side.ToUpper(), $x.line, "$($x.model_pct)%")
        }
        Add-Table @("#","Player","Team","Opp","Side","Line","Model") $rows @(7)
    } else { Add-Line "(no PrizePicks props for this market today)" }
}

# --- PrizePicks Tiers (goblin / standard / demon ladder) ----------------------
Add-Line ""
Add-Header "PRIZEPICKS TIERS — goblin (safer/lower line) / standard / demon (swing/higher line); model % to go OVER. No payout/EV — PrizePicks doesn't publish tier multipliers."
foreach ($mk in $ppMarkets.Keys) {
    $b = $ppTiers[$mk]
    Add-Line ""
    Add-Line ("{0} ({1}) — {2} players" -f $ppMarkets[$mk], $mk, ($(if ($b) { $b.count } else { 0 }))) $true
    if ($b -and $b.rows.Count -gt 0) {
        $rows = foreach ($x in $b.rows) {
            $cell = {
                param($t)
                if ($x.tiers.$t) { "{0} ({1}%)" -f $x.tiers.$t.line, $x.tiers.$t.model_pct } else { "—" }
            }
            ,@($x.name, $x.team, $x.opponent, (& $cell "goblin"), (& $cell "standard"), (& $cell "demon"))
        }
        Add-Table @("Player","Team","Opp","Goblin","Standard","Demon") $rows @(4,5,6)
    } else { Add-Line "(no PrizePicks tier props for this market today)" }
}

# --- Appendix: ChatGPT image prompts ------------------------------------------
$sel.InsertBreak(7)                        # wdPageBreak
Add-Header "IMAGE PROMPTS (paste into ChatGPT to generate the poster art)"
foreach ($r in $results) {
    Add-Line ""
    Add-Header ("{0} — image prompt" -f $r.Label)
    foreach ($line in ($r.Slip.prompt -split "`n")) { Add-Line $line }
}
foreach ($b in @(
    @{ t = "PLAYER WATCH";        p = $playerWatch.prompt },
    @{ t = "MONEYLINE BOARD";     p = $moneylineBoard.prompt },
    @{ t = "STRIKEOUT WATCH";     p = $strikeoutWatch.prompt },
    @{ t = "HITS & TOTAL BASES";  p = $hitsTbWatch.prompt }
)) {
    Add-Line ""
    Add-Header ("{0} — image prompt" -f $b.t)
    foreach ($line in ($b.p -split "`n")) { Add-Line $line }
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
