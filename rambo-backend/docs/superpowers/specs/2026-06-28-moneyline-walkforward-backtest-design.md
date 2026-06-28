# Moneyline Walk-Forward Backtest — Design

**Date:** 2026-06-28
**Status:** Approved (design), pending implementation plan
**Thread:** Closes the "backtested predictive moneyline model" active thread — point-in-time features + walk-forward validation.

## 1. Goal

Validate whether the transparent moneyline run-model (`brains/ev/moneyline_model.py`) has real predictive signal, and measure its ROI and CLV against the **actual historical book lines** it would have faced. This is the leak-free, walk-forward backtest the harness (`brains/ev/backtest.py`) was built to score.

## 2. Data Reality (verified 2026-06-28)

Queried `data/mlb_ingest.db`:

| Data | State | Consequence |
|---|---|---|
| `player_game_logs` (hitting + pitching) | Full 2026 season from opening day 2026-03-25 | Point-in-time team R/RA and starter ERA are reconstructable as-of any date |
| `games` final scores | Only 34 finals stored, but `ingestion/backfill.py` pulls the whole season free from statsapi | Outcomes to grade against — run the backfill first |
| `odds_lines` moneyline snapshots | Only 2 live days (06-26 → 06-28) | No *stored* history, BUT The Odds API $30 plan includes the Historical Odds endpoint → real historical lines are fetchable |

**Decision:** historical odds are available via The Odds API historical endpoint, so the backtest grades against real book lines (real ROI + CLV), not synthetic/self-referential numbers.

## 3. Scope (settled)

- **Depth:** two snapshots per game — an early line (~4h out, once starters are confirmed) and a closing line (first pitch). The harness grades ROI at **both** entry points side by side, so the "bet early vs bet late" question is answered empirically rather than by intuition. CLV is measured as the early→close move.
- **Entry-timing rationale:** for the *team* moneyline the dominant late-breaking risk is a probable starter being scratched (the model's biggest input is opposing-starter ERA); position-player lineups move player props far more than the team line. Meanwhile the closing line is the sharpest, and CLV is ~0 by definition if you only bet at the close — so the disciplined entry is "once starters are confirmed, but before the line sharpens." The two-price grade lets the season's data confirm or refute that for this model.
- **Out of scope:** retraining / ML model fitting (the model is closed-form, parameter-free). "Walk-forward" here means *strictly-prior features per date*, which is the leak guard — there is no training loop.

## 4. Components

### 4.1 Point-in-time feature layer (leak-free core)

The current `evaluate_game` reads season-to-date aggregates (`repo.team_runs(season)`, `repo.pitcher_era(season)`) that include games *after* the prediction date — leakage. Add as-of siblings in `repositories/mlb_repo.py`, placed next to their leaky counterparts so the two paths are visibly paired:

- `team_runs_asof(team_id, season, before_date) -> {runs_scored, runs_allowed, games_played} | None`
  Aggregated from `games` final scores where `official_date < before_date`.
- `pitcher_era_asof(mlb_id, season, before_date) -> float | None`
  ERA computed from `player_game_logs` (pitching: summed earned runs, innings) where `game_date < before_date`.

**Invariant:** strictly `<`, never `<=`. On the morning of game day D you do not have D's result.

`moneyline_model.evaluate_game_asof(repo, season, game, before_date)` mirrors `evaluate_game` but calls the `_asof` reads. It keeps the market-anchoring path (anchors to the historical de-vigged **early** line for that date) — anchoring is honest here because we have the real past line. The picked side is fixed at the early line; ROI is then computed against both the early and closing prices for that same side.

### 4.2 Historical odds ingestion

The Odds API historical response is `{timestamp, previous_timestamp, next_timestamp, data: [event...]}` where each event in `data` has the identical shape to the live endpoint. Therefore the existing `_normalize_the_odds_api` normalizer (matches event → `game_pk` by team names + commence date) is reused verbatim.

- `the_odds_api_client.fetch_moneyline_historical(snapshot_iso, *, client=None) -> RunResult`
  GET `/v4/historical/sports/baseball_mlb/odds?date={snapshot_iso}&regions=us&markets=h2h&oddsFormat=american`.
  Unwraps `.data`; stamps each event's `_captured_at` from the response `timestamp` (the real snapshot time the API served, which can differ from the requested instant). Returns the standard `RunResult` → lands via the existing source/normalize/`odds_lines` path. Logs `x-requests-remaining`.

- `ingestion/odds_backfill.py` — `backfill_odds(conn, start, end) -> dict`
  For each game-day in `[start, end]`: read `final_games`, derive two snapshot timestamps per game from `commence_time` — **early** = `commence_time − 4h` (starters typically confirmed by then), **closing** = `commence_time − 5min`. Dedup snapshot timestamps across the day's slate so a single historical call retrieves the whole slate at that instant (cost ≈ 2 calls/day, not 2/game). Spend-capped and idempotent (odds UPSERT on the existing key). The exact historical credit multiplier is confirmed from `x-requests-remaining` on the first real call before any bulk run.

  *Note on snapshot granularity:* one historical call returns the slate at one timestamp. Games with different first-pitch times yield different morning/closing instants; the dedup is per distinct timestamp, so a typical day with a few staggered start times costs a handful of calls, still well inside the 20K/mo quota.

### 4.3 Walk-forward harness + surface

- `brains/ev/walkforward.py` — `run(repo, start, end) -> dict`
  For each game-day D in `[start, end]`, for each `final_game` on D:
  1. `evaluate_game_asof(repo, season, game, before_date=D)` using strictly-prior features.
  2. Anchor to D's de-vigged **early** line; pick the side the model leans (model prob > anchored book prob). The pick is fixed at the early line and *not* re-decided at the close.
  3. Emit a record carrying both prices: `p` = model prob for the picked side, `win` = did that side win (from final score), `odds_early` / `odds_close` = early and closing American prices for that side.
  Grade through `backtest.evaluate()` **twice on the same picks** — once with `odds = odds_early` (also passing `close = odds_close` for CLV) and once with `odds = odds_close` — producing a side-by-side result `{early: {...}, close: {...}}`. Calibration / Brier / log-loss are identical across both (same `p`, same `win`); only ROI and the price differ, isolating the entry-timing effect.
  Skips games missing as-of features or either odds snapshot (counted in the result so coverage is transparent).

- **Surface:**
  - CLI: `scripts/walkforward.py` (and a `cmc-*` PowerShell step consistent with `cmc-daily.ps1`).
  - API: `GET /edge/backtest?start=&end=` in `api/betting.py` returning the metrics JSON for the dashboard.
  - A Haiku one-paragraph plain-English read of the metrics, reusing the `explainer.py` pattern.

## 5. Data Flow

```
backfill.py  ──pull season finals──▶ games (scores)
odds_backfill.py ─historical snapshots─▶ odds_lines (early + closing)
                                            │
walkforward.run(start,end)                  │
  └ per game-day D:                          │
      evaluate_game_asof(before_date=D) ◀─ mlb_repo._asof reads (game logs < D)
      anchor to early de-vig line ◀──────────┘
      pick side → record{p,win,odds_early,odds_close}
  └ evaluate(early) + evaluate(close) ─▶ {early:{roi,clv,…}, close:{roi,…}}
       └ explainer (Haiku) ─▶ plain-English read
  └ /edge/backtest  ·  scripts/walkforward.py
```

## 6. Error Handling

- Missing as-of features (early-season dates with too few prior games) → skip game, increment a `skipped_features` counter.
- Missing odds snapshot (historical call returned no line for that game) → skip game, increment `skipped_odds`.
- One bad date or event never aborts the run (per-item try/except, matching `backfill.py` and the existing clients).
- Credit exhaustion: `fetch_moneyline_historical` surfaces `x-requests-remaining`; `backfill_odds` stops and reports if the header hits zero.

## 7. Testing

- `test_walkforward.py` — leak guard (a feature as-of date D never reflects game D's result), record assembly (correct side/win + both `odds_early`/`odds_close` mapped to the picked side), side-by-side early-vs-close result shape, coverage counters.
- `test_odds_backfill.py` — snapshot timestamp derivation (early/closing offsets), per-day slate dedup, idempotent re-run.
- `_asof` repo tests — `team_runs_asof` / `pitcher_era_asof` respect the strict `<` boundary.
- Grading math already covered by `test_backtest.py` (unchanged).

## 8. Honest Limitations (documented, not hidden)

- The model is closed-form and market-anchored; the backtest measures whether anchored leans beat the line, not a learned edge. A genuinely learned model is a future thread.
- Historical odds coverage depends on The Odds API's snapshot availability for each timestamp; gaps reduce N and are reported, never silently filled.
- CLV uses the early→closing move on the *same picked side*; it is a directional signal, not a guaranteed realizable number.
- The early-vs-close ROI comparison is a same-pick price study (the side is chosen once at the early line), not a separate close-time model run — it isolates entry timing, not a different decision rule.

## 9. File Manifest

| File | Change |
|---|---|
| `repositories/mlb_repo.py` | + `team_runs_asof`, `pitcher_era_asof` |
| `brains/ev/moneyline_model.py` | + `evaluate_game_asof` |
| `ingestion/the_odds_api_client.py` | + `fetch_moneyline_historical` |
| `ingestion/odds_backfill.py` | new — `backfill_odds` |
| `brains/ev/walkforward.py` | new — `run` |
| `api/betting.py` | + `GET /edge/backtest` |
| `scripts/walkforward.py` | new — CLI entry |
| `tests/test_walkforward.py`, `tests/test_odds_backfill.py` | new |
| `tests/test_mlb_repo.py` (or existing repo test) | + `_asof` boundary tests |
