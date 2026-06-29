# Predictive Moneyline Model — Design

**Date:** 2026-06-29
**Status:** Approved (design), pending implementation plan
**Thread:** Beat the closed-form moneyline baseline (May 2026: ROI −0.70, Brier 0.1227, log-loss 0.4085) with a learned, calibrated model — measured through the existing walk-forward backtest harness.

## 1. Goal

Build a **well-calibrated, learned** moneyline win-probability model that beats the broken closed-form baseline and predicts honestly. Success is defined by calibration improvement + beating the baseline ROI, **not** by a promise of positive EV (MLB closing lines are near-efficient; genuine +EV is a truthfully-reported stretch goal).

## 2. Why the baseline failed (motivation)

The closed-form `market_anchored_prob` clamps the model to `[0.35, 0.67]` then blends 80% toward the de-vigged book. For any heavy underdog the 0.35 floor lifts the anchored estimate *above* the book line, so the model systematically "finds value" on underdogs and bets them. The May backtest (n=332) confirmed it: 15.7% win rate, ROI −0.70, predicted win rates running ~6× actual in the low bins, CLV ≈ 0. The learned model removes the clamp and the fixed anchor and learns weights from real outcomes instead.

## 3. Decisions (settled)

- **Success bar:** well-calibrated model that beats the baseline; `brier < 0.1227`, `log_loss < 0.4085`, `roi > −0.70`. +EV reported honestly if it appears, never required.
- **Engine:** hand-rolled logistic regression in pure Python — **zero new dependencies** (no numpy/sklearn). Interpretable coefficients, hard to overfit on ~3 months of data, fits the project's transparent/minimal-dep ethos.
- **Evaluation:** both the baseline and the learned model run through the **same** `walkforward` harness over the **same** window, graded identically.

## 4. Components

### 4.1 Features (point-in-time, leak-free)

Predict **P(home win)**. Three features, all from the existing `_asof` repo reads:

1. `run_diff` = `(home RS/G − home RA/G) − (away RS/G − away RA/G)`, as-of the game date.
2. `era_diff` = `away_starter_ERA − home_starter_ERA` as-of (positive favors home; missing ERA → league-avg 4.20).
3. `pythag_diff` = `pythag_winpct(home RS, home RA) − pythag_winpct(away RS, away RA)`, as-of.

Home-field advantage is captured by the model **intercept**, so no explicit home feature. Features are **standardized** (z-scored using the training set's per-feature mean/std) before fitting. Small feature set is deliberate — guards against overfitting the limited dataset.

`features.game_feature_vector(repo, season, game, before_date) -> list[float] | None` builds one game's vector (None if the as-of team-run data is missing). `features.training_set(repo, season, before_date) -> (X, y)` builds the labeled training matrix (see 4.2).

### 4.2 Walk-forward training (leak-free)

A model predicting game day **D** trains only on games finished strictly before **D**.

- `training_set(repo, season, before_date)` walks every final game with `official_date < before_date`, builds each game's features *as-of its own date* (point-in-time), and labels it `1` if the home team won else `0`. Returns `(X, y)`.
- **Expanding window with periodic refit:** pure-Python gradient descent is refit on a **cadence** (default **weekly**, i.e. refit when ≥7 days since the last fit) and reused between refits. Cadence is a constructor parameter (`refit_days`, default 7).

### 4.3 Logistic regression module — `brains/ev/ml/logreg.py`

Pure Python, self-contained, knows nothing about baseball:

- `LogisticRegression(l2: float = 0.0, lr: float = 0.1, epochs: int = 500)`
- `fit(X: list[list[float]], y: list[int]) -> self` — compute per-feature mean/std and standardize, then batch gradient descent on the L2-regularized log-loss; store standardization, weights, intercept. A feature with zero variance uses std=1 (no-op standardization) to avoid division by zero.
- `predict_proba(x: list[float]) -> float` — standardize with stored stats, apply sigmoid, clamp to `[1e-6, 1 − 1e-6]`.
- `coefficients() -> dict[str, float]` — named weights + intercept for transparency.

### 4.4 Predictors (pluggable) — `brains/ev/ml/predictor.py`

A predictor exposes:
- `prepare(repo, season, before_date) -> None` — refit if cadence elapsed (no-op for the closed-form model).
- `predict_home(repo, season, game, before_date) -> float | None` — P(home win), or None when features are missing.

Two implementations:
- `AnchoredPredictor` — wraps the existing `evaluate_game_asof`; `predict_home` returns its `model_home`. `prepare` is a no-op. This is the baseline, now expressed as a predictor.
- `LogRegPredictor(refit_days=7, l2=1.0)` — `prepare` rebuilds `training_set(before_date)` and refits the `LogisticRegression` when ≥`refit_days` since the last fit (or on first call); `predict_home` builds the game's feature vector and returns `predict_proba`. Holds the fitted model + last-fit date as instance state.

### 4.5 Harness generalization — `brains/ev/walkforward.py`

`run(repo, start, end, predictor=None)` — `predictor` defaults to `AnchoredPredictor` (preserves current behavior and the shipped test). Per game-day D: call `predictor.prepare(repo, season, D)` once, then for each final game build `p_home = predictor.predict_home(...)`. The existing pick rule (bet the side where model prob > de-vigged book prob), price-window lookup, record assembly, and `backtest.evaluate()` grading are unchanged. The `evaluate_game_asof` call currently inline in `run` moves behind `AnchoredPredictor` so the harness only talks to the predictor interface.

### 4.6 Comparison surface

- CLI: `scripts/backtest_compare.py START END` runs both predictors over the window and prints the two metric blocks plus a one-line verdict (beat baseline ROI/Brier/log-loss? yes/no per metric).
- API: extend `GET /betting/backtest` with an optional `model` query param (`anchored` default | `logreg`) returning that model's metrics, so the dashboard can request either.

## 5. Data Flow

```
final games (Mar 25 → D-1) ──▶ training_set(before_date)
                                  │ each game's as-of features + outcome label
                                  ▼
LogRegPredictor.prepare(D) ─ refit weekly ─▶ LogisticRegression.fit
                                  │
walkforward.run(start,end,predictor)         │
  └ per game-day D:                           │
      predictor.prepare(D)  ◀─────────────────┘
      p_home = predictor.predict_home(game, D)
      pick value side vs de-vig book → record{p,win,odds,close}
  └ backtest.evaluate(records) ─▶ {roi, brier, log_loss, avg_clv, calibration}
scripts/backtest_compare ─▶ baseline vs logreg, side by side + verdict
```

## 6. Error Handling

- Missing as-of features for a game → feature vector is None → skipped (existing `skipped_features` path).
- Empty training set (very early dates) → `prepare` leaves the model unfit; `predict_home` returns None → game skipped, counted.
- Zero-variance feature column → std=1 fallback (no divide-by-zero).
- All numeric ops are pure Python; no external failure modes.

## 7. Testing

- `test_logreg.py` — synthetic separable data drives log-loss down and recovers each weight's sign; standardization round-trip; zero-variance column safe; `predict_proba` clamped.
- `test_ml_features.py` — `game_feature_vector` values correct for a seeded game; `training_set` leak guard (a training row for date D never reflects D's result; labels match final scores); None on missing data.
- `test_predictor.py` — `LogRegPredictor.prepare` refits on cadence and reuses between; `AnchoredPredictor.predict_home` matches `evaluate_game_asof`'s `model_home`; both satisfy the interface.
- `test_walkforward.py` (existing) — unchanged behavior for the default predictor (no regression); add a case passing an explicit `AnchoredPredictor`.
- Grading math already covered by `test_backtest.py`.

## 8. Honest Limitations

- Three features over ~3 months is a small model on limited data; it may beat the baseline yet still be −EV. The backtest reports that plainly.
- The closing line is near-efficient; positive CLV is unlikely and is never assumed.
- Weekly refit trades a little freshness for speed; tightening the cadence is a one-line change if warranted.
- This is not a market-anchored model — it is a standalone learned estimate. Blending it with the book (ensemble) is a deliberate future thread, not part of v1.

## 9. File Manifest

| File | Change |
|---|---|
| `brains/ev/ml/__init__.py` | new (package) |
| `brains/ev/ml/logreg.py` | new — `LogisticRegression` |
| `brains/ev/ml/features.py` | new — `game_feature_vector`, `training_set` |
| `brains/ev/ml/predictor.py` | new — `AnchoredPredictor`, `LogRegPredictor` |
| `brains/ev/walkforward.py` | modify — `run(..., predictor=None)`; move inline `evaluate_game_asof` behind `AnchoredPredictor` |
| `api/betting.py` | modify — `GET /betting/backtest` optional `model` param |
| `scripts/backtest_compare.py` | new — side-by-side CLI |
| `tests/test_logreg.py`, `tests/test_ml_features.py`, `tests/test_predictor.py` | new |
| `tests/test_walkforward.py` | modify — explicit-predictor case, no-regression |
