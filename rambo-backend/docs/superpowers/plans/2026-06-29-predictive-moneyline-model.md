# Predictive Moneyline Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A hand-rolled, zero-dependency logistic-regression moneyline model, walk-forward trained on point-in-time features and graded through the existing backtest harness, to beat the −0.70 closed-form baseline.

**Architecture:** A pure-Python `LogisticRegression`, a leak-free feature/training-set builder over the existing `_asof` repo reads, and two interchangeable `Predictor` objects (closed-form baseline + learned model) plugged into a generalized `walkforward.run`. Both models grade identically against the same window.

**Tech Stack:** Python 3 (pure stdlib — no numpy/sklearn), SQLite, FastAPI, pytest.

## Global Constraints

- **Zero new dependencies** — pure-Python only; no numpy/sklearn/scipy/pandas.
- Point-in-time leak guard: a game's features are built as-of its own `official_date`, which the `_asof` reads exclude via strict `<`. Training games are strictly before the prediction date.
- DB path from `RAMBO_DB_PATH` (default `data/mlb_ingest.db`); tests use `get_connection(str(tmp_path/"t.db"))` + `apply_migrations(conn, "db/migrations")`.
- `MlbRepo` is read-only.
- Predictor interface (exact): `prepare(self, repo, season: int, before_date: str) -> None` and `predict_home(self, repo, season: int, game: dict, before_date: str) -> float | None`.
- Feature order is fixed: `["run_diff", "era_diff", "pythag_diff"]`. League-average ERA fallback = 4.20.
- Run tests from `rambo-backend/` with `./.venv/Scripts/python.exe -m pytest` (fall back to `python` if the venv python is absent).
- Commit messages use Bash heredoc; co-author line `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Branch: `feat/predictive-moneyline-model` (already created).

---

### Task 1: Pure-Python logistic regression

**Files:**
- Create: `brains/ev/ml/__init__.py` (empty)
- Create: `brains/ev/ml/logreg.py`
- Test: `tests/test_logreg.py`

**Interfaces:**
- Consumes: nothing (pure stdlib).
- Produces: `LogisticRegression(l2: float = 0.0, lr: float = 0.1, epochs: int = 500, feature_names: list[str] | None = None)` with `.fit(X, y) -> self`, `.predict_proba(x) -> float`, `.coefficients() -> dict[str, float]`. `X` is `list[list[float]]`, `y` is `list[int]`, `x` is `list[float]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_logreg.py
import math
from brains.ev.ml.logreg import LogisticRegression


def test_recovers_separable_signal_and_drives_loss_down():
    # y depends positively on feature 0, negatively on feature 1
    X = [[2.0, -1.0], [1.5, -0.5], [1.0, 0.0], [-1.0, 1.0], [-1.5, 0.5], [-2.0, 1.0]]
    y = [1, 1, 1, 0, 0, 0]
    m = LogisticRegression(l2=0.0, lr=0.5, epochs=2000,
                           feature_names=["a", "b"]).fit(X, y)
    # predictions separate the classes
    assert m.predict_proba([2.0, -1.0]) > 0.6
    assert m.predict_proba([-2.0, 1.0]) < 0.4
    coef = m.coefficients()
    assert coef["a"] > 0 and coef["b"] < 0          # signs recovered
    assert "intercept" in coef


def test_predict_proba_is_clamped():
    X = [[10.0], [-10.0]]
    y = [1, 0]
    m = LogisticRegression(lr=1.0, epochs=3000).fit(X, y)
    p_hi = m.predict_proba([1000.0])
    p_lo = m.predict_proba([-1000.0])
    assert 0.0 < p_lo <= 1e-6 + 1e-9
    assert 1.0 - 1e-6 - 1e-9 <= p_hi < 1.0


def test_zero_variance_feature_does_not_crash():
    X = [[1.0, 5.0], [1.0, -5.0], [1.0, 5.0], [1.0, -5.0]]  # col 0 constant
    y = [1, 0, 1, 0]
    m = LogisticRegression(epochs=500).fit(X, y)
    p = m.predict_proba([1.0, 5.0])
    assert 0.0 < p < 1.0 and not math.isnan(p)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_logreg.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brains.ev.ml'`

- [ ] **Step 3: Write minimal implementation**

Create `brains/ev/ml/__init__.py` (empty file).

Create `brains/ev/ml/logreg.py`:

```python
"""Pure-Python logistic regression — zero dependencies. Standardizes features on
the training set, fits L2-regularized log-loss by batch gradient descent, and
predicts a clamped probability. Knows nothing about baseball; just the math."""
from __future__ import annotations

import math


def _sigmoid(z: float) -> float:
    # overflow-safe logistic
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


class LogisticRegression:
    def __init__(self, l2: float = 0.0, lr: float = 0.1, epochs: int = 500,
                 feature_names: list[str] | None = None) -> None:
        self.l2 = l2
        self.lr = lr
        self.epochs = epochs
        self.feature_names = feature_names
        self.mean: list[float] = []
        self.std: list[float] = []
        self.w: list[float] = []
        self.b: float = 0.0

    def _standardize(self, x: list[float]) -> list[float]:
        return [(x[j] - self.mean[j]) / self.std[j] for j in range(len(x))]

    def fit(self, X: list[list[float]], y: list[int]) -> "LogisticRegression":
        n = len(X)
        d = len(X[0]) if n else 0
        # per-feature mean/std (population); zero variance -> std 1 (no-op scale)
        self.mean = [sum(row[j] for row in X) / n for j in range(d)]
        self.std = []
        for j in range(d):
            var = sum((row[j] - self.mean[j]) ** 2 for row in X) / n
            self.std.append(math.sqrt(var) if var > 1e-12 else 1.0)
        Xs = [self._standardize(row) for row in X]
        self.w = [0.0] * d
        self.b = 0.0
        for _ in range(self.epochs):
            gw = [0.0] * d
            gb = 0.0
            for i in range(n):
                p = _sigmoid(sum(self.w[j] * Xs[i][j] for j in range(d)) + self.b)
                err = p - y[i]
                for j in range(d):
                    gw[j] += err * Xs[i][j]
                gb += err
            for j in range(d):
                self.w[j] -= self.lr * (gw[j] / n + self.l2 * self.w[j])
            self.b -= self.lr * (gb / n)
        return self

    def predict_proba(self, x: list[float]) -> float:
        xs = self._standardize(x)
        z = sum(self.w[j] * xs[j] for j in range(len(xs))) + self.b
        return min(1.0 - 1e-6, max(1e-6, _sigmoid(z)))

    def coefficients(self) -> dict[str, float]:
        names = self.feature_names or [f"x{j}" for j in range(len(self.w))]
        out = {names[j]: self.w[j] for j in range(len(self.w))}
        out["intercept"] = self.b
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_logreg.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/brains/ev/ml/__init__.py rambo-backend/brains/ev/ml/logreg.py rambo-backend/tests/test_logreg.py
git commit -m "$(cat <<'EOF'
feat(betting): pure-Python logistic regression (zero deps)

Standardize + L2 gradient descent + clamped predict_proba, for the
learned moneyline model. No numpy/sklearn.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Feature & training-set builder

**Files:**
- Modify: `repositories/mlb_repo.py` (add `training_games`)
- Create: `brains/ev/ml/features.py`
- Test: `tests/test_ml_features.py`

**Interfaces:**
- Consumes: `MlbRepo.team_runs_asof`, `MlbRepo.pitcher_era_asof` (shipped), `moneyline_model.pythag_winpct` (existing).
- Produces:
  - `MlbRepo.training_games(season: int, before_date: str) -> list[dict]` — full final-game rows (`game_pk`, `official_date`, `home_team_id`, `away_team_id`, `home_probable_pitcher_id`, `away_probable_pitcher_id`, `home_score`, `away_score`) with `official_date < before_date`, both scores present, matching season; ordered by date.
  - `features.LG_ERA = 4.20`
  - `features.game_feature_vector(repo, season: int, game: dict, before_date: str) -> list[float] | None` — `[run_diff, era_diff, pythag_diff]`, or None if as-of team runs missing. `game` must carry `home_team_id`, `away_team_id`, `home_probable_pitcher_id`, `away_probable_pitcher_id`.
  - `features.FEATURE_NAMES = ["run_diff", "era_diff", "pythag_diff"]`
  - `features.training_set(repo, season: int, before_date: str) -> tuple[list[list[float]], list[int]]` — features (as-of each game's own date) + labels (1 if home won) for all `training_games` with a buildable vector.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ml_features.py
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev.ml import features


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _final(conn, pk, date, home_id, away_id, hs, as_, hp=None, ap=None):
    conn.execute(
        "INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
        "home_team_abbr, away_team_abbr, home_probable_pitcher_id, "
        "away_probable_pitcher_id, home_score, away_score, scraped_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (pk, date, home_id, away_id, "HHH", "AAA", hp, ap, hs, as_,
         "2026-06-28T00:00:00Z"))


def test_feature_vector_signs(tmp_path):
    conn = _conn(tmp_path)
    # team 1 strong (scores 8 allows 2), team 2 weak (scores 2 allows 8), in April
    for d in ("2026-04-01", "2026-04-05", "2026-04-10"):
        _final(conn, hash(d) % 90000, d, 1, 2, 8, 2)
    repo = MlbRepo(conn)
    game = {"home_team_id": 1, "away_team_id": 2,
            "home_probable_pitcher_id": None, "away_probable_pitcher_id": None}
    vec = features.game_feature_vector(repo, 2026, game, "2026-05-01")
    assert vec is not None
    run_diff, era_diff, pythag_diff = vec
    assert run_diff > 0           # home outscores opponents by far more
    assert era_diff == 0.0        # both pitchers unknown -> 4.20 fallback both sides
    assert pythag_diff > 0        # home has better pythag


def test_feature_vector_none_without_prior(tmp_path):
    conn = _conn(tmp_path)
    repo = MlbRepo(conn)
    game = {"home_team_id": 1, "away_team_id": 2,
            "home_probable_pitcher_id": None, "away_probable_pitcher_id": None}
    assert features.game_feature_vector(repo, 2026, game, "2026-04-01") is None


def test_training_set_leak_guard_and_labels(tmp_path):
    conn = _conn(tmp_path)
    # history so feature vectors are buildable
    for d in ("2026-04-01", "2026-04-03", "2026-04-05"):
        _final(conn, hash("h" + d) % 90000, d, 1, 2, 6, 3)
        _final(conn, hash("k" + d) % 90000 + 1, d, 2, 1, 3, 6)
    # a labeled game on 04-20 (home team 1 wins) and one on the cutoff 05-01 (excluded)
    _final(conn, 70001, "2026-04-20", 1, 2, 7, 1)
    _final(conn, 70002, "2026-05-01", 1, 2, 0, 9)
    repo = MlbRepo(conn)
    X, y = features.training_set(repo, 2026, "2026-05-01")
    # the 05-01 game is excluded (official_date < before_date is strict)
    pks = repo.training_games(2026, "2026-05-01")
    assert all(g["official_date"] < "2026-05-01" for g in pks)
    # every label is 1/0 and matches a home win/loss; the 04-20 blowout is a home win
    assert set(y) <= {0, 1}
    assert len(X) == len(y) and len(y) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_ml_features.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brains.ev.ml.features'`

- [ ] **Step 3: Write minimal implementation**

Add to `repositories/mlb_repo.py` (after `final_games`):

```python
    def training_games(self, season: int, before_date: str) -> list[dict]:
        """Full final-game rows strictly before `before_date` (same season) for
        model training — includes probable-pitcher ids and final scores."""
        return _dicts(self.conn.execute(
            "SELECT game_pk, official_date, home_team_id, away_team_id, "
            "home_probable_pitcher_id, away_probable_pitcher_id, "
            "home_score, away_score FROM games "
            "WHERE official_date < ? "
            "AND CAST(strftime('%Y', official_date) AS INTEGER)=? "
            "AND home_score IS NOT NULL AND away_score IS NOT NULL "
            "ORDER BY official_date, game_pk", (before_date, season)))
```

Create `brains/ev/ml/features.py`:

```python
"""Point-in-time features for the learned moneyline model. A game's features are
built as-of its own date via the leak-free _asof reads, so training rows never see
their own outcome. Three features: run differential, starter-ERA differential,
Pythagorean win% differential — all home-minus-away."""
from __future__ import annotations

from brains.ev.moneyline_model import pythag_winpct

LG_ERA = 4.20
FEATURE_NAMES = ["run_diff", "era_diff", "pythag_diff"]


def game_feature_vector(repo, season: int, game: dict,
                        before_date: str) -> list[float] | None:
    """[run_diff, era_diff, pythag_diff] for one game, or None if as-of team-run
    data is missing. era_diff = away_era - home_era (positive favors home)."""
    hr = repo.team_runs_asof(game["home_team_id"], season, before_date)
    ar = repo.team_runs_asof(game["away_team_id"], season, before_date)
    if not hr or not ar:
        return None
    hg, ag = hr["games_played"], ar["games_played"]
    if hg <= 0 or ag <= 0:
        return None
    run_diff = ((hr["runs_scored"] - hr["runs_allowed"]) / hg
                - (ar["runs_scored"] - ar["runs_allowed"]) / ag)
    home_era = repo.pitcher_era_asof(game["home_probable_pitcher_id"], season,
                                     before_date) or LG_ERA
    away_era = repo.pitcher_era_asof(game["away_probable_pitcher_id"], season,
                                     before_date) or LG_ERA
    era_diff = away_era - home_era
    pythag_diff = (pythag_winpct(hr["runs_scored"], hr["runs_allowed"])
                   - pythag_winpct(ar["runs_scored"], ar["runs_allowed"]))
    return [run_diff, era_diff, pythag_diff]


def training_set(repo, season: int,
                 before_date: str) -> tuple[list[list[float]], list[int]]:
    """Labeled training matrix from all final games strictly before `before_date`.
    Each game's features are as-of ITS OWN date (leak-free); label = 1 if home won."""
    X: list[list[float]] = []
    y: list[int] = []
    for g in repo.training_games(season, before_date):
        vec = game_feature_vector(repo, season, g, g["official_date"])
        if vec is None:
            continue
        X.append(vec)
        y.append(1 if g["home_score"] > g["away_score"] else 0)
    return X, y
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_ml_features.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/repositories/mlb_repo.py rambo-backend/brains/ev/ml/features.py rambo-backend/tests/test_ml_features.py
git commit -m "$(cat <<'EOF'
feat(betting): point-in-time features + training-set builder

run/era/pythag differentials as-of each game's own date; training_games
repo read; labels from final scores. Leak-free by construction.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Predictors (baseline + learned)

**Files:**
- Create: `brains/ev/ml/predictor.py`
- Test: `tests/test_predictor.py`

**Interfaces:**
- Consumes: `moneyline_model.evaluate_game_asof` (shipped), `features.game_feature_vector` / `training_set` / `FEATURE_NAMES` (Task 2), `logreg.LogisticRegression` (Task 1).
- Produces:
  - `AnchoredPredictor()` with `prepare(repo, season, before_date)` (no-op) and `predict_home(repo, season, game, before_date) -> float | None` (returns `evaluate_game_asof(...)["model_home"]`, or None).
  - `LogRegPredictor(refit_days: int = 7, l2: float = 1.0, lr: float = 0.3, epochs: int = 800)` with the same interface; `prepare` refits the `LogisticRegression` on `training_set` when ≥`refit_days` since the last fit (or unfit); `predict_home` returns `predict_proba` of the game's feature vector, or None if unfit or features missing. Exposes `.model` (the fitted `LogisticRegression` or None) and `.last_fit_date`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_predictor.py
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev.ml.predictor import AnchoredPredictor, LogRegPredictor


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _final(conn, pk, date, home_id, away_id, hs, as_):
    conn.execute(
        "INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
        "home_team_abbr, away_team_abbr, home_score, away_score, scraped_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (pk, date, home_id, away_id, "HHH", "AAA", hs, as_, "2026-06-28T00:00:00Z"))


def _history(conn):
    # alternating results so both classes appear; teams 1 (strong) vs 2 (weak)
    i = 0
    for d in ("2026-04-01", "2026-04-03", "2026-04-05", "2026-04-07", "2026-04-09"):
        _final(conn, 1000 + i, d, 1, 2, 7, 2); i += 1
        _final(conn, 1000 + i, d, 2, 1, 1, 6); i += 1


def test_logreg_predictor_refits_on_cadence(tmp_path):
    conn = _conn(tmp_path)
    _history(conn)
    repo = MlbRepo(conn)
    p = LogRegPredictor(refit_days=7)
    p.prepare(repo, 2026, "2026-04-15")
    first = p.model
    assert first is not None and p.last_fit_date == "2026-04-15"
    # within 7 days -> no refit (same model object)
    p.prepare(repo, 2026, "2026-04-18")
    assert p.model is first and p.last_fit_date == "2026-04-15"
    # >=7 days later -> refit (new model object)
    p.prepare(repo, 2026, "2026-04-25")
    assert p.model is not first and p.last_fit_date == "2026-04-25"


def test_logreg_predictor_predicts_probability(tmp_path):
    conn = _conn(tmp_path)
    _history(conn)
    repo = MlbRepo(conn)
    p = LogRegPredictor(refit_days=7)
    p.prepare(repo, 2026, "2026-04-15")
    game = {"home_team_id": 1, "away_team_id": 2,
            "home_probable_pitcher_id": None, "away_probable_pitcher_id": None}
    prob = p.predict_home(repo, 2026, game, "2026-04-15")
    assert prob is not None and 0.0 < prob < 1.0


def test_logreg_predictor_none_when_unfit(tmp_path):
    conn = _conn(tmp_path)
    repo = MlbRepo(conn)            # no history -> empty training set -> unfit
    p = LogRegPredictor()
    p.prepare(repo, 2026, "2026-04-01")
    game = {"home_team_id": 1, "away_team_id": 2,
            "home_probable_pitcher_id": None, "away_probable_pitcher_id": None}
    assert p.model is None
    assert p.predict_home(repo, 2026, game, "2026-04-01") is None


def test_anchored_predictor_matches_evaluate_game_asof(tmp_path):
    conn = _conn(tmp_path)
    for d in ("2026-04-01", "2026-04-05", "2026-04-10"):
        _final(conn, hash(d) % 90000, d, 1, 2, 8, 2)
    repo = MlbRepo(conn)
    from brains.ev.moneyline_model import evaluate_game_asof
    s = {"game_pk": 999, "home_team_id": 1, "away_team_id": 2,
         "home_probable_pitcher_id": None, "away_probable_pitcher_id": None,
         "home_team_abbr": "HHH", "away_team_abbr": "AAA",
         "home_price": -120, "away_price": 100}
    p = AnchoredPredictor()
    p.prepare(repo, 2026, "2026-05-01")
    got = p.predict_home(repo, 2026, s, "2026-05-01")
    ev = evaluate_game_asof(repo, 2026, s, "2026-05-01")
    assert got == ev["model_home"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_predictor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brains.ev.ml.predictor'`

- [ ] **Step 3: Write minimal implementation**

Create `brains/ev/ml/predictor.py`:

```python
"""Interchangeable moneyline predictors for the walk-forward harness. Both expose
prepare()/predict_home(); the harness only talks to this interface, so the closed-form
baseline and the learned model are graded identically."""
from __future__ import annotations

import datetime as _dt

from brains.ev.moneyline_model import evaluate_game_asof
from brains.ev.ml import features
from brains.ev.ml.logreg import LogisticRegression


class AnchoredPredictor:
    """The shipped closed-form market-anchored model, as a predictor (the baseline)."""

    def prepare(self, repo, season: int, before_date: str) -> None:
        return None

    def predict_home(self, repo, season: int, game: dict,
                     before_date: str) -> float | None:
        ev = evaluate_game_asof(repo, season, game, before_date)
        return ev["model_home"] if ev else None


class LogRegPredictor:
    """Learned logistic-regression model, refit on a weekly cadence (expanding
    window). Holds the fitted model + last-fit date as state."""

    def __init__(self, refit_days: int = 7, l2: float = 1.0, lr: float = 0.3,
                 epochs: int = 800) -> None:
        self.refit_days = refit_days
        self.l2 = l2
        self.lr = lr
        self.epochs = epochs
        self.model: LogisticRegression | None = None
        self.last_fit_date: str | None = None

    def _due(self, before_date: str) -> bool:
        if self.model is None or self.last_fit_date is None:
            return True
        d0 = _dt.date.fromisoformat(self.last_fit_date)
        d1 = _dt.date.fromisoformat(before_date)
        return (d1 - d0).days >= self.refit_days

    def prepare(self, repo, season: int, before_date: str) -> None:
        if not self._due(before_date):
            return
        X, y = features.training_set(repo, season, before_date)
        if not X:
            return
        self.model = LogisticRegression(
            l2=self.l2, lr=self.lr, epochs=self.epochs,
            feature_names=features.FEATURE_NAMES).fit(X, y)
        self.last_fit_date = before_date

    def predict_home(self, repo, season: int, game: dict,
                     before_date: str) -> float | None:
        if self.model is None:
            return None
        vec = features.game_feature_vector(repo, season, game, before_date)
        if vec is None:
            return None
        return self.model.predict_proba(vec)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_predictor.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/brains/ev/ml/predictor.py rambo-backend/tests/test_predictor.py
git commit -m "$(cat <<'EOF'
feat(betting): Anchored + LogReg predictors

One interface (prepare/predict_home); LogReg refits weekly on an expanding
window. Lets baseline and learned model grade identically.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Generalize the harness to take a predictor

**Files:**
- Modify: `brains/ev/walkforward.py` (`run` signature + body; move `evaluate_game_asof` use behind the predictor)
- Test: `tests/test_walkforward.py` (add an explicit-predictor case; existing tests must still pass)

**Interfaces:**
- Consumes: `predictor.AnchoredPredictor` (Task 3), `moneyline_model.devig_two_way` (existing). `pick_record` and `_prices_at` are unchanged.
- Produces: `run(repo, start, end, predictor=None) -> dict` — `predictor` defaults to `AnchoredPredictor()`; same return shape as before (`n`, `skipped_features`, `skipped_odds`, `early`, `close`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_walkforward.py`:

```python
def test_run_accepts_explicit_predictor(tmp_path):
    from db.migrate import get_connection, apply_migrations
    from repositories.mlb_repo import MlbRepo
    from brains.ev.walkforward import run
    from brains.ev.ml.predictor import AnchoredPredictor
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    # empty range -> n=0 but must return the full shape and not raise
    out = run(MlbRepo(conn), "2026-05-01", "2026-05-02", predictor=AnchoredPredictor())
    assert out["n"] == 0
    assert "early" in out and "close" in out
    assert out["skipped_features"] == 0 and out["skipped_odds"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_walkforward.py::test_run_accepts_explicit_predictor -v`
Expected: FAIL — `TypeError: run() got an unexpected keyword argument 'predictor'`

- [ ] **Step 3: Write minimal implementation**

Replace the module top imports and the `run` function in `brains/ev/walkforward.py`. Change the import block at the top (lines 6-11) to:

```python
from __future__ import annotations

import sqlite3

from brains.ev import backtest
```

(`evaluate_game_asof` is no longer imported here — it lives behind `AnchoredPredictor`.) Leave `pick_record` and `_prices_at` exactly as they are. Replace `run` with:

```python
def run(repo, start: str, end: str, predictor=None) -> dict:
    """Grade every final game in [start,end] using `predictor` (default: the
    closed-form AnchoredPredictor). Returns side-by-side early/close metrics plus
    coverage counters."""
    import datetime as _dt
    from brains.ev.moneyline_model import devig_two_way
    from brains.ev.ml.predictor import AnchoredPredictor
    if predictor is None:
        predictor = AnchoredPredictor()
    conn = repo.conn
    records: list[dict] = []
    skipped_features = skipped_odds = 0
    for g in repo.final_games(start, end):
        date = g["official_date"]
        season = int(date[:4])
        slate = {s["game_pk"]: s for s in repo.moneyline_slate(date)}
        s = slate.get(g["game_pk"])
        if not s:
            skipped_odds += 1
            continue
        predictor.prepare(repo, season, date)
        p_home = predictor.predict_home(repo, season, s, date)
        if p_home is None:
            skipped_features += 1
            continue
        book_home, book_away = devig_two_way(s["home_price"], s["away_price"])
        ev = {"model_home": p_home, "model_away": 1.0 - p_home,
              "book_home": book_home, "book_away": book_away}
        dt = s.get("game_datetime")
        if not dt:
            skipped_odds += 1
            continue
        t = _dt.datetime.fromisoformat(dt)
        early = _prices_at(conn, g["game_pk"],
                           (t - _dt.timedelta(hours=6)).isoformat().replace("+00:00", "Z"),
                           (t - _dt.timedelta(hours=2)).isoformat().replace("+00:00", "Z"))
        close = _prices_at(conn, g["game_pk"],
                           (t - _dt.timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
                           t.isoformat().replace("+00:00", "Z"))
        if not early or not close:
            skipped_odds += 1
            continue
        win_home = g["home_score"] > g["away_score"]
        rec = pick_record(ev, win_home, early, close)
        if rec is None:
            continue
        records.append(rec)

    early_records = [{"p": r["p"], "win": r["win"], "odds": r["odds_early"],
                      "close": r["odds_close"]} for r in records]
    close_records = [{"p": r["p"], "win": r["win"], "odds": r["odds_close"]}
                     for r in records]
    return {
        "n": len(records),
        "skipped_features": skipped_features,
        "skipped_odds": skipped_odds,
        "early": backtest.evaluate(early_records),
        "close": backtest.evaluate(close_records),
    }
```

- [ ] **Step 4: Run the full walkforward test file to verify no regression**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_walkforward.py -v`
Expected: PASS — the new `test_run_accepts_explicit_predictor` plus all pre-existing `pick_record` / `_prices_at` tests still green.

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/brains/ev/walkforward.py rambo-backend/tests/test_walkforward.py
git commit -m "$(cat <<'EOF'
refactor(betting): walkforward.run takes a pluggable predictor

Default AnchoredPredictor preserves behavior; the harness now talks only
to the predictor interface so baseline and learned model grade the same.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Comparison surface (API param + CLI)

**Files:**
- Modify: `api/betting.py` (`/backtest` optional `model` param)
- Create: `scripts/backtest_compare.py`
- Test: `tests/test_backtest_api.py` (add a `model=logreg` case)

**Interfaces:**
- Consumes: `walkforward.run` (Task 4), `predictor.AnchoredPredictor` / `LogRegPredictor` (Task 3), `MlbRepo`, `get_connection`.
- Produces: `GET /betting/backtest?start=&end=&model=anchored|logreg` returns that model's metrics. `scripts/backtest_compare.py START END` prints both models' metrics + a verdict line.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_backtest_api.py`:

```python
def test_backtest_endpoint_logreg_model_empty_ok(tmp_path, monkeypatch):
    db = str(tmp_path / "t.db")
    _seed(db)
    monkeypatch.setenv("RAMBO_DB_PATH", db)
    import importlib
    import api.betting as betting
    importlib.reload(betting)
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(betting.router)
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.get("/betting/backtest",
                   params={"start": "2026-05-01", "end": "2026-05-02", "model": "logreg"})
    assert r.status_code == 200
    assert r.json()["n"] == 0
```

(The existing `_seed` helper and default-model test in this file remain unchanged.)

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_backtest_api.py::test_backtest_endpoint_logreg_model_empty_ok -v`
Expected: FAIL — the route ignores `model` / returns 422 for the unknown param, or the import path for predictors is missing.

- [ ] **Step 3: Write minimal implementation**

Replace the `/backtest` route in `api/betting.py` (from Task 6 of the prior plan) with:

```python
@router.get("/backtest")
def backtest_endpoint(start: str, end: str, model: str = "anchored") -> dict:
    """Walk-forward moneyline backtest over [start,end] for `model`
    ('anchored' = closed-form baseline | 'logreg' = learned). Data-only — grades
    historical picks, never places bets."""
    from db.migrate import get_connection
    from repositories.mlb_repo import MlbRepo
    from brains.ev.walkforward import run
    from brains.ev.ml.predictor import AnchoredPredictor, LogRegPredictor
    predictor = LogRegPredictor() if model == "logreg" else AnchoredPredictor()
    conn = get_connection(_DB)
    try:
        return run(MlbRepo(conn), start, end, predictor=predictor)
    finally:
        conn.close()
```

Create `scripts/backtest_compare.py`:

```python
"""CLI: run BOTH the closed-form baseline and the learned model over a window and
print their metrics side by side, with a one-line verdict on whether the learned
model beat the baseline. Usage: python scripts/backtest_compare.py START END"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.migrate import get_connection
from repositories.mlb_repo import MlbRepo
from brains.ev.walkforward import run
from brains.ev.ml.predictor import AnchoredPredictor, LogRegPredictor


def _verdict(base: dict, learned: dict) -> str:
    b, l = base["early"], learned["early"]
    parts = []
    for k in ("roi", "brier", "log_loss"):
        bv, lv = b.get(k), l.get(k)
        if bv is None or lv is None:
            parts.append(f"{k}: n/a")
            continue
        better = lv > bv if k == "roi" else lv < bv   # higher ROI good; lower error good
        parts.append(f"{k}: {lv} vs {bv} {'BEAT' if better else 'worse'}")
    return " | ".join(parts)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python scripts/backtest_compare.py START_DATE END_DATE",
              file=sys.stderr)
        return 2
    start, end = sys.argv[1], sys.argv[2]
    db = os.environ.get("RAMBO_DB_PATH", "data/mlb_ingest.db")
    conn = get_connection(db)
    try:
        repo = MlbRepo(conn)
        base = run(repo, start, end, predictor=AnchoredPredictor())
        learned = run(repo, start, end, predictor=LogRegPredictor())
    finally:
        conn.close()
    print(json.dumps({"baseline": base, "logreg": learned}, indent=2))
    print("\nVERDICT (early line):", _verdict(base, learned))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_backtest_api.py -v`
Expected: PASS — both the existing default-model test and the new `logreg` case.

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/api/betting.py rambo-backend/scripts/backtest_compare.py rambo-backend/tests/test_backtest_api.py
git commit -m "$(cat <<'EOF'
feat(betting): model param on /backtest + side-by-side compare CLI

GET /betting/backtest?model=anchored|logreg; backtest_compare prints both
with a beat-the-baseline verdict.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Live comparison run + full-suite gate

**Files:** none (operational verification).

**Interfaces:** consumes everything above against the real `data/mlb_ingest.db` (May 2026 finals + odds already backfilled).

- [ ] **Step 1: Run the side-by-side comparison over May**

```bash
cd rambo-backend && ./.venv/Scripts/python.exe scripts/backtest_compare.py 2026-05-01 2026-05-31
```
Expected: JSON with a `baseline` block (should reproduce ~roi −0.70, brier 0.1227, log_loss 0.4085) and a `logreg` block, plus a VERDICT line. Record whether logreg beat the baseline on roi / brier / log_loss. If `logreg` n is much lower than baseline n, inspect `skipped_features` (early-May dates need prior-game history — already backfilled from 2026-03-25, so coverage should be comparable).

- [ ] **Step 2: Sanity-check the learned coefficients**

```bash
cd rambo-backend && ./.venv/Scripts/python.exe -c "from db.migrate import get_connection; from repositories.mlb_repo import MlbRepo; from brains.ev.ml.predictor import LogRegPredictor; p=LogRegPredictor(); p.prepare(MlbRepo(get_connection('data/mlb_ingest.db')), 2026, '2026-05-31'); print(p.model.coefficients() if p.model else 'UNFIT')"
```
Expected: a coefficients dict. Sign sanity: `run_diff` and `pythag_diff` should be positive (better team → higher home win prob); `era_diff` positive (better home starter → higher home win prob); `intercept` slightly positive (home-field advantage). Note any sign that disagrees — it would indicate a feature-orientation bug.

- [ ] **Step 3: Run the full backend test suite (gate)**

Run: `cd rambo-backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: all prior tests still pass plus the new ones (≈577 + new). No regressions.

- [ ] **Step 4: Commit the recorded result + push**

```bash
git commit --allow-empty -m "$(cat <<'EOF'
chore(betting): record learned-model May backtest vs baseline

<paste the VERDICT line + coefficients here>

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
git push -u origin feat/predictive-moneyline-model
```

---

## Notes for the implementer

- **Performance:** `training_set` rebuilds every prior game's feature vector on each refit (~4 as-of SQL reads/game). With weekly refits over a month this is a few tens of thousands of reads — seconds-to-minutes, acceptable for a backtest tool. Do NOT add caching speculatively (YAGNI); only revisit if a run is painfully slow.
- **`before_date` semantics are identical for train and predict:** a game on date D is always featurized as-of D (the `_asof` reads exclude D via strict `<`). Training games use their own `official_date`; predicted games use the slate date, which is the game's date. No special-casing needed.
- **Do not re-tune** `l2`/`lr`/`epochs` to chase a better May number — that is fitting the test set. The defaults (l2=1.0, lr=0.3, epochs=800) are reasonable; if the model is wildly miscalibrated, raise it in the report rather than hand-tuning to the May result.
- **The verdict can legitimately be "did not beat baseline."** Report it honestly (per spec §1/§8); a faithful negative result still closes the question.
