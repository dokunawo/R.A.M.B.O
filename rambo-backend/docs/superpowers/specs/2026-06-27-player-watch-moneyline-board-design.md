# Player Watch + Moneyline Board — Design Spec

**Date:** 2026-06-27
**Status:** Approved (design), pending implementation plan
**Brand:** Chances Make Champions (CMC) — black/gold/crown, consistent with existing slip prompts

## 1. Goal

Add two new daily "board" outputs to the CMC betting tool, each delivered as a
ready-to-paste **ChatGPT image prompt** (same delivery model as the existing
per-market slips):

1. **Player Watch** — the top 11 home-run chances for the slate, styled like a
   "YARDWATCH"-class card: rank, player, team, matchup, HR%, ballpark + weather,
   HR environment, plus power/form tags.
2. **Moneyline Board** — every game on the slate with both teams' book odds, our
   model win %, and our suggested side + lean, so a user can mix-and-match their
   own moneyline/parlay while seeing our read on each game.

Both reuse existing EV-brain data and math. **No new data sources.**

## 2. Honesty constraint (load-bearing)

The reference card shows **pitch-mix usage tags** and **BvP** (batter-vs-pitcher).
Neither is ingested, and an image prompt that *asks* for them would make ChatGPT
fabricate numbers — violating CMC's honest-data principle. Decision: **omit both**
and fill those visual slots with REAL data we already have (Statcast power +
season/L15 form). The prompts must never instruct ChatGPT to invent stats.

## 3. Architecture

Mirrors the existing slip pattern (`brains/ev/slip.py` → `api/betting.py` →
`cmc-daily.ps1`).

- **`brains/ev/watch.py`** (new module)
  - `player_watch(date, *, count=11, as_of=None, book=None) -> dict`
  - `moneyline_board(date, *, as_of=None, book=None) -> dict`
  - each returns `{title, product, count, rows, prompt, ...}` (shape parallel to
    `slip.build_slip`)
- **`api/betting.py`** (extend)
  - `GET /betting/player-watch?date=` → `{date, **watch, provenance}`
  - `GET /betting/moneyline-board?date=` → `{date, **board, provenance}`
  - both reuse the existing `_provenance()` helper (data-as-of + stale guard)
- **`cmc-daily.ps1`** (extend) — print both prompts to console + add both as
  Consolas-9 sections in the Word doc.

Both endpoints are data-only reads (Sentinel boundary — no bet capability), like
the rest of `api/betting.py`.

## 4. Player Watch

### 4.1 Data assembly
Run the existing HR market via `daily_edge(date, "hr", threshold=-1.0)` to get a
ranked candidate list (threshold -1 so we can fill 11 rows even though HR legs are
−EV). Take the top 11 by `model_p`, one row per player. Enrich each via `MlbRepo`
+ the HR feature pipeline (no new queries beyond what already exists):

| Field | Source |
|---|---|
| rank | enumerate(1..11) |
| name, team, opponent | HR `Pick` |
| batter hand (R/L/S) | `players.bats` (new tiny repo getter `player_bats(mlb_id)`) |
| vs pitcher (full name) | `player_game_context` → `opp_pitcher_id` → `players.full_name` (new getter `player_name(mlb_id)`) |
| HR % | `Pick.model_p` |
| ballpark name | `games.venue_name` (via game context) |
| temp (°F) | `game_weather(game_pk).temp` |
| HR env: park % | `parks.hr_factor(home_abbr)` → `(factor-1)*100` as `+18%` |
| HR env: wind | `game_weather(game_pk).wind` (e.g. "10mph OUT to LCF"); omit if absent |
| power tags | `player_statcast`: barrel% + hard-hit%, each flagged green (≥ league avg) / red (< league avg) using the same baselines as `features._power_modifier` |
| form | season HR + L15 HR (`HRFeatures.season_hr`, `recent_hr`) |

Implementation note: rather than re-deriving, `player_watch` will build
`HRFeatures` (already carries park_factor, season_hr, recent_hr, temp_park) and
do a small number of extra repo reads for the display-only fields (bats, pitcher
name, venue_name, temp, wind, raw barrel/hard-hit). Missing optional fields
(weather not posted, statcast absent) are simply omitted from that row's line —
never faked.

### 4.2 Prompt shape
A single string, same envelope as `slip._build_prompt`:
- Provenance banner: `[DK Pick6 · as of <ts> · DraftKings Pick6]`
- STYLE block: cinematic black + gold/amber smoke, gold crown, brush/graffiti
  lettering — big brush title **"PLAYER WATCH"**, CMC branding.
- LAYOUT block: numbered list of 11 rows; each row shows player (team · hand · vs
  pitcher), the big **HR%**, ballpark + temp, HR env (park % + wind), power tags,
  form.
- CRITICAL clause: reproduce ALL text exactly — do not change, abbreviate,
  reorder, or invent any name, number, team, or %.
- KEY line: "Green tag = above league average, red = below. % = model HR
  probability. No pitch-mix or BvP shown — figures are model/Statcast based."
- ROWS: the 11 assembled lines. Example row:
  `1. BYRON BUXTON (MIN · R · vs Michael Lorenzen) — HR 31.0% — Target Field 81°F — env +3% · 12mph IN from RCF — barrel 14%↑ / hardhit 48%↑ — 22 HR (4 L15)`

### 4.3 Constants
Add to `watch.py`: `PLAYER_WATCH_SIZE = 11`, title "PLAYER WATCH", reuse
`slip.PRODUCT["hr"]`.

## 5. Moneyline Board

### 5.1 Data assembly
For **every** game from `repo.moneyline_slate(date)` (already excludes in-game
books / price=0), compute both sides using the SAME math the `ml` market uses
(`devig_two_way`, `expected_runs`, `winprob_from_runs`, `matchup_winprob`,
`market_anchored_prob`, `pythag_winpct`). For each game emit:

| Field | Source |
|---|---|
| away abbr + price, home abbr + price | `moneyline_slate` |
| de-vigged book % (each side) | `devig_two_way` |
| model win % (each side) | pitcher-adjusted run model, falling back to Pythagorean |
| anchored % + lean side | `market_anchored_prob`; lean = anchored − book on the favored disagreement, bounded as today |
| our pick | the side with the positive lean; "no lean" if within tolerance |

This is a refactor-friendly extraction: factor the per-game computation currently
inlined in `MoneylineMarket.raw_picks` into a shared helper
(`moneyline_model.evaluate_game(...)` or similar) returning both-side numbers, so
`moneyline_board` and the `ml` market both call it (no duplicated math).

### 5.2 Ordering (no bias)
Rows are listed in **strict slate order, NOT ranked by lean** — the dedicated `ml`
slip already surfaces our best plays, so the board stays a neutral menu. Order key:
alphabetical by away-team abbr, then home-team abbr (deterministic). True
first-pitch order is deferred: the `games` table stores `official_date` +
`day_night` but no start timestamp, so game-time sorting would need ingesting the
schedule `gameDate` into a new column (see §7).

### 5.3 Prompt shape
Same envelope. Title **"MONEYLINE BOARD"**, provenance
`[Moneyline (de-vig book lean) · as of <ts> · DraftKings]`. One row per game in
the order above:
`1. ARI (+130) @ ATL (-150) — model: ATL 58% / ARI 42% — CMC lean: ATL +1.2%`
Neutral example: `2. BOS (+105) @ NYY (-115) — model: NYY 51% / BOS 49% — no lean`
CRITICAL + KEY clauses as above ("leans are bounded disagreements with the
de-vigged book, not guarantees; build your own card from any side").

### 5.4 Existing moneyline output also re-ordered (user request)
The current `ml` results (the `daily-edge?market=ml` list and the `ml` slip
prompt) are today ranked by lean magnitude. Per the operator, switch the **`ml`
market's presentation order to the same alphabetical slate order** so the daily
moneyline reads in a consistent, unbiased sequence. This is an ordering change
only — the +EV/threshold filtering and the lean math are unchanged. Concretely:
`build_slip`'s `ml` branch and `daily_edge` for `ml` sort by matchup (away abbr,
home abbr) instead of by `edge`. Other markets (hr/hrr/sb/k) keep their
probability ranking.

## 6. cmc-daily.ps1 integration

After the existing 5-market loop, fetch the two boards and:
- print each `prompt` to the console under a `##### PLAYER WATCH #####` /
  `##### MONEYLINE BOARD #####` header;
- append each to the Word doc as a bold header + Consolas-9 prompt block, matching
  the current formatting (zero paragraph spacing).
Both use the existing UTF-8-safe `Get-Json` helper. They read already-pulled data,
so they cost nothing extra and work under `-SkipPrep`.

## 7. Out of scope (YAGNI)

- Rendering our own PNG (user chose the ChatGPT-prompt flow).
- Ingesting pitch-mix arsenal or BvP (possible future follow-up; explicitly
  deferred — and BvP was judged low-value previously).
- Run line / totals on the Moneyline Board (moneyline only).
- True first-pitch game-time ordering (deferred — needs ingesting schedule
  `gameDate` into a new `games` column; alphabetical slate order used for now).
- Any bet-placement capability (Sentinel boundary).

## 8. Testing

Unit tests in `rambo-backend/tests/`:
- `test_watch_player.py` — given a stub repo with known HR features + weather +
  statcast + bats + pitcher name, `player_watch` returns 11 ordered rows and a
  prompt containing each player's exact text; missing optional fields are omitted
  (never "None"/faked).
- `test_watch_moneyline.py` — `moneyline_board` returns one row per slate game with
  both-side odds + model %, rows in alphabetical slate order (away abbr, home
  abbr), the lean side matches the `ml` market's pick for the same game (shared
  helper consistency), and neutral games render "no lean".
- `test_ev_moneyline.py` (extend) — assert the `ml` slip / `daily_edge` output is
  ordered alphabetically by matchup, not by lean.
- API smoke: both endpoints return 200 with `prompt` + `provenance`.

## 9. Honesty / provenance recap

- Real data only; optional fields omitted when absent, never fabricated.
- Both prompts carry the data-as-of stamp + stale guard via `_provenance`.
- Framing stays CMC-honest: HR% is a model probability (HR props are −EV as
  singles); moneyline numbers are bounded leans, not locks.
