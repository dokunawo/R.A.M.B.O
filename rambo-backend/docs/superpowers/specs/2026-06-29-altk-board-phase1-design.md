# Alt-K Board — Phase 1 (Model + Calibration) Design

**Date:** 2026-06-29
**Status:** Approved (design), pending implementation plan
**Thread:** Complete the FanDuel alt-strikeout board. Phase 1 = make the model accurate and trustworthy (opponent-adjusted rate × batters-faced, full 1+…10+ ladder) and prove its probabilities are calibrated. Phase 2 (FanDuel alt-K odds + per-threshold EV + parlay builder) is a separate later spec.

## 1. Goal

Reformulate the strikeout projection as **Expected K Rate (per batter) × Expected Batters Faced**, adjust the rate by the opposing lineup's strikeout tendency, surface the full **P(1+ … 10+ K)** ladder, and validate the probabilities with a free, leak-free calibration backtest before any betting layer is built on top.

## 2. Current state

`brains/ev/watch.py::strikeout_watch` already ranks probable starters by P(9+ K) using `poisson_prob_over` on a per-start K mean (season blended with last-15), with a min-starts filter, sanity clamp, poster prompt, `/betting/strikeout-watch` endpoint, and voice routing. Gaps Phase 1 closes: (a) no opponent adjustment, (b) only 8/9/10 shown, (c) Poisson on a single mean rather than rate×BF, (d) no calibration evidence.

Confirmed available: pitching game logs carry `strikeOuts` and `battersFaced`; hitting game logs carry `strikeOuts` and `plateAppearances`; `players.current_team_id` maps players to teams. No new ingestion is required.

## 3. Decisions (settled)

- **Model:** Binomial(n = round(expected BF), p = expected K rate). Binomial (not Poisson) because K ≤ batters faced, matching the desired table.
- **Opponent factor:** opposing lineup season-to-date K% ÷ league K%, clamped [0.85, 1.20], applied to the per-batter rate.
- **Ladder:** P(j+ K) for j = 1…10 (configurable max, default 10).
- **Backtest:** calibration-only against real strikeout outcomes from game logs (free, leak-free). No odds, no credits. ROI/CLV vs FanDuel is Phase 2, forward-only.
- **Shared scoring:** one `k_projection` function powers the live board and the backtest, so they validate the identical model.

## 4. Components

### 4.1 K distribution math — `brains/ev/k_model.py`

- `binom_prob_over(n: int, p: float, j: int) -> float` — P(X ≥ j) for X ~ Binomial(n, p), pure Python via `math.comb`. Guards: `n ≤ 0` → 0.0; `j ≤ 0` → 1.0; `j > n` → 0.0; clamp result to [0, 1].
- `ladder(n: int, p: float, max_j: int = 10) -> dict[int, float]` — `{1: P(1+), …, max_j: P(max_j+)}`.
- `LG_K_PCT = 0.22` (league batter K rate baseline).
- `opponent_modifier(opp_k_pct: float | None) -> float` — `clamp(opp_k_pct / LG_K_PCT, 0.85, 1.20)`; `1.0` when `opp_k_pct` is None.

### 4.2 Opponent K% read — `repositories/mlb_repo.py`

`team_k_pct_asof(team_id: int, season: int, before_date: str) -> float | None` — `SUM(strikeOuts) / SUM(plateAppearances)` over hitting `player_game_logs` for players whose `current_team_id = team_id`, `game_date < before_date` (strict), season-scoped via `strftime('%Y', game_date)`. `None` if total PA is 0. Leak-free by the strict `<` boundary, same discipline as `team_runs_asof`.

### 4.3 K projection — `brains/ev/k_model.py`

`k_projection(repo, date: str, starter: dict, before_date: str | None = None) -> dict | None` where `starter` carries `mlb_id`, `name`, `team_abbr`, `opponent_abbr`, and the opposing `opponent_team_id` (resolved by the caller from game context). `before_date` defaults to `date` (the start's own day — leak-free for both live and backtest). Returns `None` when the pitcher has no usable K-rate sample.

Computation:
1. **Base K rate** = season `SUM(strikeOuts)/SUM(battersFaced)` blended with the last-15 same ratio (reuse the existing `RAMBO_RECENT_WEIGHT` blend helper), both as-of `before_date`.
2. **Expected BF** = mean `battersFaced` per start (season blended with L15), clamped to [15, 30].
3. **Opponent modifier** from `team_k_pct_asof(opponent_team_id, season, before_date)` via `opponent_modifier`.
4. **Expected K rate** = `clamp(base_rate × modifier, 0.05, 0.45)`.
5. **n** = `round(expected_bf)`, **p** = expected K rate, **mean** = `n × p`.
6. `ladder = ladder(n, p, max_j)`.

Returns `{mlb_id, name, team_abbr, opponent_abbr, k_rate, batters_faced, k_mean, ladder}`.

A min-starts filter (existing `RAMBO_K_MIN_STARTS`, default 5) stays in the *board* caller, not in `k_projection` (the backtest grades all real starts).

### 4.4 Board integration — `brains/ev/watch.py`

`strikeout_watch` refactored to call `k_projection` per probable starter (resolving `opponent_team_id` from game context), rank by P(9+) (default; sort key configurable), and emit rows carrying `expected_k_rate`, `expected_bf`, `k_mean`, and the `p1…p10` ladder. The poster prompt and `/betting/strikeout-watch` endpoint render the richer table. Voice routing unchanged. The Poisson `poisson_prob_over` path is retired for this board (other boards that use it are untouched).

### 4.5 Calibration backtest — `brains/ev/k_backtest.py` + `scripts/k_backtest.py`

For each historical start (a pitching game log with a real `strikeOuts` count and a resolvable opponent) in `[start, end]`:
1. Build `k_projection` as-of the start date (leak-free, opponent-adjusted).
2. For each graded threshold j in `{6,7,8,9,10}`: record `{p: ladder[j], win: 1 if actual_K ≥ j else 0}`.
3. Per threshold, feed the records to the existing `backtest.evaluate()` → calibration bins + Brier + log-loss (ROI/CLV/odds fields omitted — no betting here).

`run(repo, start, end, thresholds=(6,7,8,9,10)) -> {threshold: metrics, "n_starts": int, "skipped": int}`. CLI `scripts/k_backtest.py START END` prints it. Answers: are the P(j+) calibrated?

## 5. Data Flow

```
hitting game logs ─┐
                   ├─ team_k_pct_asof(opp, before) ─ opponent_modifier ─┐
pitching game logs ─ base K rate + expected BF (as-of) ─────────────────┤
                                                                        ▼
                                              k_projection → Binomial(n,p) → ladder P(1+..10+)
                                                  │                        │
                              strikeout_watch board (live)        k_backtest (per-threshold
                              + /betting/strikeout-watch           calibration vs real K outcomes)
```

## 6. Error Handling

- No K-rate sample / zero BF → `k_projection` returns None → board skips (min-starts also filters), backtest counts in `skipped`.
- `team_k_pct_asof` None → modifier 1.0 (neutral), never crashes.
- Binomial guards cover degenerate n/j.
- All pure-Python + SQLite; no external failure modes.

## 7. Testing

- `test_k_model.py` — `binom_prob_over` vs known values (e.g. n=4,p=0.25 ladder), monotone-decreasing ladder, guards (j>n→0, j≤0→1); `opponent_modifier` clamp + None→1.0; `k_projection` end-to-end on a seeded pitcher (rate×BF, opponent boost vs fade changes the ladder).
- `test_team_k_pct_asof.py` — strict `<` leak guard + season filter + None on no PA, via seeded hitting logs + players.
- `test_k_backtest.py` — leak guard (a start's projection never sees its own K), per-threshold record assembly (win = actual_K ≥ j), `skipped` accounting.
- `test_strikeout_watch` (existing/extended) — rows carry the full `p1…p10` ladder + `expected_k_rate`/`expected_bf`; ranking unchanged shape.
- Full suite (589 +) stays green.

## 8. Honest Limitations

- Independence/!: this phase models a single pitcher's K distribution; parlay combination is Phase 2.
- Opponent K% uses `current_team_id` (mild imperfection across mid-season trades) and season-to-date rate (stable enough; the as-of guard keeps the backtest honest).
- Binomial assumes per-batter independence and a constant rate within a start — a simplification, but appropriate at this granularity.
- Expected BF doesn't model early hooks / blowouts; clamped to a sane band.
- Calibration backtest validates probabilities, not profitability — that needs Phase 2's FanDuel odds.

## 9. File Manifest

| File | Change |
|---|---|
| `brains/ev/k_model.py` | new — `binom_prob_over`, `ladder`, `LG_K_PCT`, `opponent_modifier`, `k_projection` |
| `repositories/mlb_repo.py` | + `team_k_pct_asof` |
| `brains/ev/watch.py` | modify — `strikeout_watch` calls `k_projection`, emits full ladder |
| `brains/ev/k_backtest.py` | new — `run` per-threshold calibration |
| `scripts/k_backtest.py` | new — CLI |
| `api/betting.py` | docstring/shape note for the richer `/betting/strikeout-watch` rows (no new route) |
| `tests/test_k_model.py`, `tests/test_team_k_pct_asof.py`, `tests/test_k_backtest.py` | new |
| `tests/test_strikeout_watch.py` | modify — full-ladder row assertions |
