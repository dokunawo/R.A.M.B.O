# EV Brain (Home Runs) — Design

**Date:** 2026-06-26
**Status:** Approved (brainstorming complete, pending implementation plan)
**Component:** `rambo-backend/brains/ev/` — the modeling layer that turns ingested MLB
data into ranked +EV betting picks.

## Purpose
The ingestion layer collects MLB data and DraftKings Pick6 props. The **EV Brain**
reads that data (via `MlbRepo`), computes each player's true probability of hitting a
prop, compares it to the Pick6 multiplier, and outputs the **ranked +EV plays** for one
market. v1 covers **Home Runs**. It is output-only — it suggests, never places (any
future bet-placement routes through the existing Sentinel gate).

The operator wants **five separate markets, each its own ranked list → its own CMC
card**: Home Runs, H+R+RBI, Stolen Bases, Strikeouts (a *pitcher* prop), and Moneyline.
The engine is built **market-pluggable** so the others drop in later with no pipeline
change; v1 implements the HR market fully.

## Core idea — Pick6 EV is multiplier-based
For a "1+ HR" prop at multiplier `m`, with model probability `P` that the player homers:
- **edge = P × m − 1**; it is +EV whenever **P > 1/m**.
- Example: 1+ HR at **2.9×** → break-even 1/2.9 = **34.5%**. Model says 40% → edge
  `0.40 × 2.9 − 1 = +0.16` (a play). Model says 30% → edge −0.13 (skip).

That single formula is the engine. Everything else computes `P` honestly and ranks by edge.

## The HR model (transparent, ported math)
1. **Batter HR rate per PA** from season stats: `homeRuns / plateAppearances`.
2. **Handedness split:** use the batter's vs-RHP or vs-LHP HR rate by the opposing
   probable pitcher's hand; fall back to overall rate if the pitcher/hand is unknown.
3. **Park factor:** multiply by the home park's HR index (static table, ported).
4. **Game probability:** `P(1+ HR) = 1 − (1 − rate)^expectedPA`, expectedPA ≈ 4.2.
5. **edge = P × multiplier − 1**, rank descending; keep edge > 0 (configurable threshold).

v1 limitation (documented sharpeners for later): no pitcher HR-allowed rate, weather,
or Statcast (barrel%/xHR). Hand-split + park already beat a flat rate.

## Architecture / components
```
MlbRepo ─▶ features ─▶ HR model ─▶ edge vs multiplier ─▶ rank ─▶ explainer ─▶ Daily Edge picks (JSON → card)
```
- `brains/ev/parks.py` — static HR park-factor table (by team abbr).
- `brains/ev/hr_model.py` — pure functions `hr_probability(...)`, `edge(p, payout)`. No I/O.
- `brains/ev/market.py` — `MarketModel` protocol: `market_key`, `candidates(repo, date)`,
  `probability(features)`; plus a registry. v1 registers `HRMarket`.
- `brains/ev/features.py` — assembles per-prop features from `MlbRepo`: batter HR rate +
  splits, the player's game that day, opposing probable pitcher hand, home park.
- `brains/ev/explainer.py` — one Anthropic (Haiku) call per market-slate writes all
  rationales; templated fallback on failure.
- `brains/ev/engine.py` — `daily_edge(date, market) -> list[Pick]`: candidates → features →
  P → edge → rank → explain.
- `api/betting.py` — `GET /betting/daily-edge?market=hr&date=YYYY-MM-DD` returns the picks
  JSON the card fetches. Mounted on `main.py` (guarded, like the ingest router).

**`Pick` — maps 1:1 to a CMC card square** (field names match the operator's card code):
- `initials` — badge (e.g. `"PCA"`)
- `name` — player (e.g. `"P. CROW-ARMSTRONG"`)
- `team`, `opponent`, `hand` — render the matchup line `"CHC // vs MIL // R"`
- `pick` — bet label, e.g. `"1+ HOME RUN — OVER"`
- `model_p` — model probability, shown as `MODEL 72%`
- `multiplier` + `breakeven` — **Pick6 has no sportsbook "BK%"**; the card's second slot
  shows the multiplier (`2.9×`) and/or break-even % (`1/multiplier`). model_p vs breakeven
  is the visual story (replaces the mock's `BK 65%`).
- `edge` — the neon-green `+7.0%`
- `tags` — `["EDGE"]` in v1 (always); `HOT` (recent form) / `MEATBALL` (vulnerable pitcher)
  are future once those signals exist.
- `glow` — badge ring color; per-market card so cosmetic (rotate or edge-tier).
- `headshot_url` — MLB image CDN by `mlb_id` (the "contact picture").
- `support` — a supporting stat (e.g. season HR total).
- `rationale` — the explainer "why".

**Card chrome (for the follow-on frontend rebuild):** header `DAILY EDGE — <MARKET> // MLB`,
date, `R.A.M.B.O`; footer is **rank-only** (drop the mock's Kelly/bank/"suggested total")
→ `N PLAYS // MLB // <market>`; branding crown + `CMC`. Styling (operator's CSS, use
verbatim): brush font **Metal Mania**; gold `#d6a21e`, white `#f2f2f2`, glowing neon green
`#39ff5a`; dark gold-radial background.

## The one data gap — migration 003
The model needs the **opposing probable pitcher** (for the hand split) and the **home
park** per prop's game. `games` currently stores neither the probable pitchers nor team
abbreviations, though the schedule pull already hydrates `probablePitcher`. This build adds:
- **`db/migrations/003_game_pitchers.sql`** — add `home_probable_pitcher_id`,
  `away_probable_pitcher_id`, `home_team_abbr`, `away_team_abbr` to `games`.
- **normalize tweak** — `map_scoreboard` extracts those four fields.

Then: resolved prop → player's `current_team_id` → their game that day → home/away →
opposing probable pitcher → `players.throws` for the hand; park from the home team abbr.
No new paid pulls.

## Read-repo additions (`MlbRepo`, read-only)
- `hr_props(date)` — resolved Pick6 HR props for the slate (mlb_id, line, multiplier).
- `player_hr_rates(mlb_id, season)` — overall + vs-L/vs-R HR rate from season stats JSON.
- `player_game(mlb_id, date)` + `probable_pitcher_hand(game_pk, batter_team_id)` — the
  game/opponent/pitcher-hand lookups.

## Error handling
- Prop with no resolved `mlb_id` or no season stats → skipped (logged).
- Game/pitcher unresolvable → fall back to overall HR rate (no hand split), still ranked.
- LLM call fails → templated rationale; numbers always return.

## Testing (all network-free)
- Pure math (`hr_probability`, `edge`) unit-tested with hand-computed values (ported).
- `features` + `engine` tested against a seeded SQLite DB.
- Explainer mocked.
- Migration 003 applies; `map_scoreboard` extracts the new fields.

## Scope
**v1 IN:** HR market end-to-end (model + features + engine), rank-only (no stakes),
per-slate Haiku explainer, the `/betting/daily-edge` endpoint, migration 003 + normalize tweak.
**OUT (later):** H+R+RBI / SB / Strikeouts / moneyline `MarketModel`s (framework-ready).
Strikeouts is a **pitcher** prop, so it needs pitcher season stats — a small ingestion add
(`statsapi` stats with `group="pitching"`) plus a pitcher-K probability model. Also out:
the CMC card frontend rebuild (design already locked); pitcher-HR-allowed / weather /
Statcast sharpeners; calibration tracking (predicted vs actual); bet placement (Sentinel-gated).
