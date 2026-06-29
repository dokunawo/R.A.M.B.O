# Alt-K Board Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reformulate the strikeout projection as opponent-adjusted Expected K Rate × Expected Batters Faced (Binomial ladder P(1+…10+)), surface the full ladder on the board, and prove the probabilities are calibrated with a free leak-free backtest.

**Architecture:** A pure-Python Binomial K-distribution module + a shared `k_projection` that pulls point-in-time pitcher K/BF and opponent K% from existing game logs. The live board and a calibration backtest both call `k_projection`, so they validate the identical model.

**Tech Stack:** Python 3 (pure stdlib — `math` only), SQLite, FastAPI, pytest.

## Global Constraints

- **Zero new dependencies** — pure stdlib (`math.comb`).
- Point-in-time leak guard: as-of reads use strictly `< before_date`, season-scoped via `strftime('%Y', …)`.
- `MlbRepo` is read-only.
- `LG_K_PCT = 0.22`; opponent modifier clamped `[0.85, 1.20]`; expected K rate clamped `[0.05, 0.45]`; expected batters faced clamped `[15, 30]`.
- Ladder default `max_j = 10`; thresholds graded in backtest = `(6, 7, 8, 9, 10)`.
- Reuse the recency blend `brains.ev.features._blend` (weights season vs last-15).
- Pitching game-log stat fields: `stats["stat"]["strikeOuts"]`, `["battersFaced"]`. Hitting: `["strikeOuts"]`, `["plateAppearances"]`. `players.current_team_id` maps player→team. `player_game_logs` carries `opponent_team_id`.
- Tests run from `rambo-backend/` with `./.venv/Scripts/python.exe -m pytest` (fall back to `python`); use `get_connection(str(tmp_path/"t.db"))` + `apply_migrations(conn, "db/migrations")`.
- Commit messages use Bash heredoc; co-author line `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Branch: `feat/altk-board-phase1` (already created).

---

### Task 1: Binomial K-distribution math

**Files:**
- Create: `brains/ev/k_model.py`
- Test: `tests/test_k_model.py`

**Interfaces:**
- Consumes: stdlib `math` only.
- Produces:
  - `binom_prob_over(n: int, p: float, j: int) -> float` — P(X ≥ j), X~Binomial(n,p). Guards: n≤0→0.0; j≤0→1.0; j>n→0.0; result clamped [0,1].
  - `ladder(n: int, p: float, max_j: int = 10) -> dict[int, float]` — `{1: P(1+), …, max_j: P(max_j+)}`.
  - `LG_K_PCT = 0.22`
  - `opponent_modifier(opp_k_pct: float | None) -> float` — `1.0` if None else `clamp(opp_k_pct / LG_K_PCT, 0.85, 1.20)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_k_model.py
import math
from brains.ev.k_model import binom_prob_over, ladder, opponent_modifier, LG_K_PCT


def test_binom_prob_over_known_values():
    # X ~ Binomial(4, 0.25): P(X>=1) = 1 - 0.75^4
    assert math.isclose(binom_prob_over(4, 0.25, 1), 1 - 0.75 ** 4, rel_tol=1e-9)
    # P(X>=4) = 0.25^4
    assert math.isclose(binom_prob_over(4, 0.25, 4), 0.25 ** 4, rel_tol=1e-9)


def test_binom_prob_over_guards():
    assert binom_prob_over(0, 0.3, 1) == 0.0      # n<=0
    assert binom_prob_over(5, 0.3, 0) == 1.0      # j<=0 -> certain
    assert binom_prob_over(5, 0.3, 6) == 0.0      # j>n
    p = binom_prob_over(24, 0.25, 8)
    assert 0.0 <= p <= 1.0


def test_ladder_is_monotone_decreasing():
    lad = ladder(24, 0.25, max_j=10)
    assert set(lad.keys()) == set(range(1, 11))
    vals = [lad[j] for j in range(1, 11)]
    assert all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1))
    assert vals[0] <= 1.0


def test_opponent_modifier_clamp_and_none():
    assert opponent_modifier(None) == 1.0
    assert opponent_modifier(LG_K_PCT) == 1.0                 # league avg -> neutral
    assert opponent_modifier(0.40) == 1.20                    # high-K lineup -> capped boost
    assert opponent_modifier(0.05) == 0.85                    # contact lineup -> capped fade
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_k_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brains.ev.k_model'`

- [ ] **Step 3: Write minimal implementation**

Create `brains/ev/k_model.py`:

```python
"""Strikeout distribution model: Binomial(n = expected batters faced, p = expected
per-batter K rate). Gives the full P(1+ … max_j+ K) ladder. Pure Python."""
from __future__ import annotations

import math


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def binom_prob_over(n: int, p: float, j: int) -> float:
    """P(X >= j) for X ~ Binomial(n, p)."""
    if n <= 0:
        return 0.0
    if j <= 0:
        return 1.0
    if j > n:
        return 0.0
    p = _clamp(p, 0.0, 1.0)
    total = sum(math.comb(n, k) * p ** k * (1 - p) ** (n - k)
                for k in range(j, n + 1))
    return _clamp(total, 0.0, 1.0)


def ladder(n: int, p: float, max_j: int = 10) -> dict[int, float]:
    """{1: P(1+ K), …, max_j: P(max_j+ K)}."""
    return {j: binom_prob_over(n, p, j) for j in range(1, max_j + 1)}


LG_K_PCT = 0.22  # league-average batter strikeout rate (K / PA)


def opponent_modifier(opp_k_pct: float | None) -> float:
    """Opposing lineup's K% relative to league, clamped. Neutral (1.0) if unknown."""
    if opp_k_pct is None:
        return 1.0
    return _clamp(opp_k_pct / LG_K_PCT, 0.85, 1.20)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_k_model.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/brains/ev/k_model.py rambo-backend/tests/test_k_model.py
git commit -m "$(cat <<'EOF'
feat(betting): binomial K-distribution model + opponent modifier

Full P(1+..max_j+ K) ladder from Binomial(batters_faced, k_rate); league
K% baseline + clamped opponent modifier. Pure Python.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Point-in-time repo reads (opponent K%, pitcher K/BF)

**Files:**
- Modify: `repositories/mlb_repo.py` (add two methods near `team_runs_asof` / `pitcher_era_asof`)
- Test: `tests/test_k_repo_asof.py`

**Interfaces:**
- Consumes: `player_game_logs` (`stats` JSON, `stat_group`, `game_date`, `mlb_id`), `players.current_team_id`.
- Produces:
  - `MlbRepo.team_k_pct_asof(team_id: int, season: int, before_date: str) -> float | None` — `SUM(strikeOuts)/SUM(plateAppearances)` over hitting logs of players on `team_id`, `game_date < before_date`, season-scoped; `None` if total PA is 0.
  - `MlbRepo.pitcher_k_aggregate(mlb_id: int, season: int, before_date: str, limit: int | None = None) -> dict | None` — `{"k": float, "bf": float, "starts": int}` summed over pitching logs `game_date < before_date` (season-scoped), newest-first, optionally limited to the last `limit` starts. `None` if no rows.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_k_repo_asof.py
import json
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _player(conn, mlb_id, team_id):
    conn.execute("INSERT INTO players (mlb_id, full_name, current_team_id) "
                 "VALUES (?,?,?)", (mlb_id, f"P{mlb_id}", team_id))


def _hit_log(conn, mlb_id, date, so, pa):
    stats = json.dumps({"stat": {"strikeOuts": so, "plateAppearances": pa}})
    conn.execute(
        "INSERT INTO player_game_logs (mlb_id, game_pk, game_date, stat_group, "
        "stats, source, scraped_at) VALUES (?,?,?,?,?,?,?)",
        (mlb_id, 0, date, "hitting", stats, "mlb/statsapi:stats", "2026-06-28T00:00:00Z"))


def _pit_log(conn, mlb_id, date, k, bf):
    stats = json.dumps({"stat": {"strikeOuts": k, "battersFaced": bf}})
    conn.execute(
        "INSERT INTO player_game_logs (mlb_id, game_pk, game_date, stat_group, "
        "stats, source, scraped_at) VALUES (?,?,?,?,?,?,?)",
        (mlb_id, 0, date, "pitching", stats, "mlb/statsapi:stats", "2026-06-28T00:00:00Z"))


def test_team_k_pct_asof_strict_before_and_team(tmp_path):
    conn = _conn(tmp_path)
    _player(conn, 1, 100); _player(conn, 2, 100); _player(conn, 9, 999)  # 9 on other team
    _hit_log(conn, 1, "2026-05-01", 2, 5)
    _hit_log(conn, 2, "2026-05-02", 1, 5)
    _hit_log(conn, 9, "2026-05-02", 5, 5)            # different team — excluded
    _hit_log(conn, 1, "2026-05-10", 9, 9)            # on/after before_date — excluded
    repo = MlbRepo(conn)
    # before 05-10: team 100 has (2+1) K over (5+5) PA = 0.3
    assert abs(repo.team_k_pct_asof(100, 2026, "2026-05-10") - 0.3) < 1e-9


def test_team_k_pct_asof_none_without_pa(tmp_path):
    conn = _conn(tmp_path)
    assert MlbRepo(_conn(tmp_path)).team_k_pct_asof(100, 2026, "2026-05-01") is None


def test_pitcher_k_aggregate_all_and_limited(tmp_path):
    conn = _conn(tmp_path)
    _pit_log(conn, 50, "2026-04-01", 6, 24)
    _pit_log(conn, 50, "2026-04-08", 8, 25)
    _pit_log(conn, 50, "2026-04-15", 10, 26)
    _pit_log(conn, 50, "2026-05-01", 99, 99)         # on/after before_date — excluded
    repo = MlbRepo(conn)
    allagg = repo.pitcher_k_aggregate(50, 2026, "2026-05-01")
    assert allagg == {"k": 24.0, "bf": 75.0, "starts": 3}
    last2 = repo.pitcher_k_aggregate(50, 2026, "2026-05-01", limit=2)
    assert last2 == {"k": 18.0, "bf": 51.0, "starts": 2}   # the two most recent
    assert repo.pitcher_k_aggregate(50, 2026, "2026-03-01") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_k_repo_asof.py -v`
Expected: FAIL — `AttributeError: 'MlbRepo' object has no attribute 'team_k_pct_asof'`

- [ ] **Step 3: Write minimal implementation**

Add to `repositories/mlb_repo.py` (after `pitcher_era_asof`):

```python
    def team_k_pct_asof(self, team_id: int, season: int,
                        before_date: str) -> Optional[float]:
        """Opposing-lineup K rate (SUM strikeOuts / SUM plateAppearances) over the
        team's hitters' game logs strictly before `before_date`. Leak-free; None if
        no plate appearances yet."""
        import json
        rows = self.conn.execute(
            "SELECT gl.stats AS stats FROM player_game_logs gl "
            "JOIN players p ON p.mlb_id = gl.mlb_id "
            "WHERE p.current_team_id=? AND gl.stat_group='hitting' "
            "AND gl.game_date < ? "
            "AND CAST(strftime('%Y', gl.game_date) AS INTEGER)=?",
            (team_id, before_date, season)).fetchall()
        so = pa = 0.0
        for r in rows:
            stat = (json.loads(r["stats"]).get("stat") or {})
            try:
                so += float(stat.get("strikeOuts") or 0)
                pa += float(stat.get("plateAppearances") or 0)
            except (TypeError, ValueError):
                continue
        return so / pa if pa > 0 else None

    def pitcher_k_aggregate(self, mlb_id: int, season: int, before_date: str,
                            limit: Optional[int] = None) -> Optional[dict]:
        """Summed strikeOuts/battersFaced and start count over a pitcher's game logs
        strictly before `before_date` (season-scoped), newest-first. `limit` caps to
        the last N starts. None if no rows."""
        import json
        q = ("SELECT stats FROM player_game_logs "
             "WHERE mlb_id=? AND stat_group='pitching' AND game_date < ? "
             "AND CAST(strftime('%Y', game_date) AS INTEGER)=? "
             "ORDER BY game_date DESC")
        params: list = [mlb_id, before_date, season]
        if limit is not None:
            q += " LIMIT ?"; params.append(int(limit))
        rows = self.conn.execute(q, params).fetchall()
        if not rows:
            return None
        k = bf = 0.0
        for r in rows:
            stat = (json.loads(r["stats"]).get("stat") or {})
            try:
                k += float(stat.get("strikeOuts") or 0)
                bf += float(stat.get("battersFaced") or 0)
            except (TypeError, ValueError):
                continue
        return {"k": k, "bf": bf, "starts": len(rows)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_k_repo_asof.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/repositories/mlb_repo.py rambo-backend/tests/test_k_repo_asof.py
git commit -m "$(cat <<'EOF'
feat(betting): point-in-time opponent K% + pitcher K/BF reads

team_k_pct_asof and pitcher_k_aggregate (strict < before_date, season-
scoped) for the opponent-adjusted strikeout model + its backtest.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `k_projection` — the shared scorer

**Files:**
- Modify: `brains/ev/k_model.py` (add `k_projection`)
- Test: `tests/test_k_projection.py`

**Interfaces:**
- Consumes: `MlbRepo.pitcher_k_aggregate`, `MlbRepo.team_k_pct_asof` (Task 2); `binom_prob_over`/`ladder`/`opponent_modifier` (Task 1); `brains.ev.features._blend`.
- Produces: `k_model.k_projection(repo, date: str, starter: dict, before_date: str | None = None, max_j: int = 10) -> dict | None`. `starter` carries `mlb_id`, `name`, `team_abbr`, `opponent_abbr`, `opponent_team_id`. `before_date` defaults to `date`. Returns `{mlb_id, name, team_abbr, opponent_abbr, k_rate, batters_faced, k_mean, ladder}` (ladder = `{1..max_j: prob}`), or `None` when the pitcher has no usable sample.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_k_projection.py
import json
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev.k_model import k_projection


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _pit_log(conn, mlb_id, date, k, bf):
    stats = json.dumps({"stat": {"strikeOuts": k, "battersFaced": bf}})
    conn.execute(
        "INSERT INTO player_game_logs (mlb_id, game_pk, game_date, stat_group, "
        "stats, source, scraped_at) VALUES (?,?,?,?,?,?,?)",
        (mlb_id, 0, date, "pitching", stats, "mlb/statsapi:stats", "2026-06-28T00:00:00Z"))


def _hit_log(conn, mlb_id, team_id, date, so, pa):
    conn.execute("INSERT OR IGNORE INTO players (mlb_id, full_name, current_team_id) "
                 "VALUES (?,?,?)", (mlb_id, f"H{mlb_id}", team_id))
    stats = json.dumps({"stat": {"strikeOuts": so, "plateAppearances": pa}})
    conn.execute(
        "INSERT INTO player_game_logs (mlb_id, game_pk, game_date, stat_group, "
        "stats, source, scraped_at) VALUES (?,?,?,?,?,?,?)",
        (mlb_id, 0, date, "hitting", stats, "mlb/statsapi:stats", "2026-06-28T00:00:00Z"))


def _starter(opp_team=None):
    return {"mlb_id": 50, "name": "Ace", "team_abbr": "AAA",
            "opponent_abbr": "BBB", "opponent_team_id": opp_team}


def test_k_projection_basic(tmp_path):
    conn = _conn(tmp_path)
    for d in ("2026-04-01", "2026-04-08", "2026-04-15"):
        _pit_log(conn, 50, d, 7, 25)            # ~0.28 K rate, 25 BF
    repo = MlbRepo(conn)
    proj = k_projection(repo, "2026-05-01", _starter())
    assert proj is not None
    assert 0.20 < proj["k_rate"] < 0.35
    assert 20 <= proj["batters_faced"] <= 30
    assert set(proj["ladder"].keys()) == set(range(1, 11))
    assert proj["k_mean"] > 0


def test_k_projection_opponent_boost_raises_ladder(tmp_path):
    conn = _conn(tmp_path)
    for d in ("2026-04-01", "2026-04-08", "2026-04-15"):
        _pit_log(conn, 50, d, 7, 25)
    # opposing team 200 strikes out a lot (high K%)
    for mid in (201, 202):
        for d in ("2026-04-02", "2026-04-09"):
            _hit_log(conn, mid, 200, d, 3, 5)   # 0.6 K% -> capped boost
    repo = MlbRepo(conn)
    base = k_projection(repo, "2026-05-01", _starter(opp_team=None))
    boosted = k_projection(repo, "2026-05-01", _starter(opp_team=200))
    assert boosted["k_rate"] > base["k_rate"]
    assert boosted["ladder"][9] > base["ladder"][9]


def test_k_projection_none_without_sample(tmp_path):
    conn = _conn(tmp_path)
    assert k_projection(MlbRepo(conn), "2026-05-01", _starter()) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_k_projection.py -v`
Expected: FAIL — `ImportError: cannot import name 'k_projection'`

- [ ] **Step 3: Write minimal implementation**

Add to `brains/ev/k_model.py`:

```python
def k_projection(repo, date: str, starter: dict, before_date: str | None = None,
                 max_j: int = 10) -> dict | None:
    """Opponent-adjusted strikeout distribution for one probable starter, as-of
    `before_date` (defaults to `date` — leak-free for both the live board and the
    backtest). Binomial(round(expected BF), expected K rate). None if no sample."""
    from brains.ev.features import _blend
    bd = before_date or date
    season = int(date[:4])
    mid = starter["mlb_id"]
    season_agg = repo.pitcher_k_aggregate(mid, season, bd)
    if not season_agg or season_agg["bf"] <= 0 or season_agg["starts"] <= 0:
        return None
    recent_agg = repo.pitcher_k_aggregate(mid, season, bd, limit=15)
    season_rate = season_agg["k"] / season_agg["bf"]
    recent_rate = (recent_agg["k"] / recent_agg["bf"]
                   if recent_agg and recent_agg["bf"] > 0 else None)
    base_rate = _blend(recent_rate, season_rate)

    season_bf = season_agg["bf"] / season_agg["starts"]
    recent_bf = (recent_agg["bf"] / recent_agg["starts"]
                 if recent_agg and recent_agg["starts"] > 0 else None)
    exp_bf = _blend(recent_bf, season_bf)
    if base_rate is None or exp_bf is None:
        return None
    exp_bf = _clamp(exp_bf, 15.0, 30.0)

    mod = opponent_modifier(repo.team_k_pct_asof(starter.get("opponent_team_id"),
                                                 season, bd)
                            if starter.get("opponent_team_id") else None)
    k_rate = _clamp(base_rate * mod, 0.05, 0.45)
    n = round(exp_bf)
    return {
        "mlb_id": mid, "name": starter.get("name") or "",
        "team_abbr": starter.get("team_abbr") or "",
        "opponent_abbr": starter.get("opponent_abbr") or "",
        "k_rate": k_rate, "batters_faced": exp_bf, "k_mean": n * k_rate,
        "ladder": ladder(n, k_rate, max_j),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_k_projection.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/brains/ev/k_model.py rambo-backend/tests/test_k_projection.py
git commit -m "$(cat <<'EOF'
feat(betting): k_projection — opponent-adjusted rate x batters-faced

Shared scorer for the board + backtest: blended K rate x opponent
modifier, expected BF, Binomial ladder. Leak-free via before_date.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Board integration (full ladder)

**Files:**
- Modify: `brains/ev/watch.py` (`strikeout_watch` + its row/line/prompt helpers)
- Test: `tests/test_strikeout_watch.py` (extend)

**Interfaces:**
- Consumes: `k_model.k_projection` (Task 3); existing `repo.probable_starters`, `repo.game`, `repo.player_season`.
- Produces: `strikeout_watch(date, repo=None, *, count=STRIKEOUT_WATCH_SIZE, as_of=None, book=None) -> dict` with rows now carrying `k_rate`, `batters_faced`, `k_mean`, and `p1..p10` (the ladder flattened). Ranking by P(9+).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_strikeout_watch.py` (reuse the file's existing seeding helpers; this test seeds the minimum needed):

```python
def test_strikeout_watch_rows_carry_full_ladder(tmp_path):
    import json
    from db.migrate import get_connection, apply_migrations
    from repositories.mlb_repo import MlbRepo
    from brains.ev.watch import strikeout_watch
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    now = "2026-06-28T00:00:00Z"
    # a probable starter with enough starts + a K/BF history
    conn.execute("INSERT INTO players (mlb_id, full_name, current_team_id) VALUES (50,'ACE',1)")
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
                 "home_team_abbr, away_team_abbr, home_probable_pitcher_id, scraped_at) "
                 "VALUES (900,'2026-06-29',1,2,'AAA','BBB',50,?)", (now,))
    season = json.dumps({"season": {"gamesStarted": 12}})
    conn.execute("INSERT INTO player_season_stats (mlb_id, season, stat_group, stats, "
                 "source, as_of_date, scraped_at) VALUES (50,2026,'pitching',?,?,?,?)",
                 (season, "mlb/statsapi:stats", "2026-06-28", now))
    for d in ("2026-06-01", "2026-06-08", "2026-06-15", "2026-06-22"):
        st = json.dumps({"stat": {"strikeOuts": 8, "battersFaced": 25}})
        conn.execute("INSERT INTO player_game_logs (mlb_id, game_pk, game_date, "
                     "stat_group, stats, source, scraped_at) VALUES (50,0,?,?,?,?,?)",
                     (d, "pitching", st, "mlb/statsapi:stats", now))
    board = strikeout_watch("2026-06-29", repo=MlbRepo(conn))
    assert board["count"] >= 1
    row = board["rows"][0]
    for j in range(1, 11):
        assert f"p{j}" in row and 0 <= row[f"p{j}"] <= 100
    assert "k_rate" in row and "batters_faced" in row
    # ladder is monotone non-increasing across thresholds
    probs = [row[f"p{j}"] for j in range(1, 11)]
    assert all(probs[i] >= probs[i + 1] for i in range(len(probs) - 1))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_strikeout_watch.py::test_strikeout_watch_rows_carry_full_ladder -v`
Expected: FAIL — rows have `p8/p9/p10` only, not `p1..p10` / missing `k_rate`.

- [ ] **Step 3: Write minimal implementation**

In `brains/ev/watch.py`, replace the strikeout-watch section (the `_sw_row`, `_sw_line`, `strikeout_watch` block, lines ~160–249). Add `from brains.ev.k_model import k_projection` to the imports. New code:

```python
# ── Strikeout Watch (alt-K board: full P(1+..10+) ladder per probable starter) ──
def _sw_row(rank: int, proj: dict) -> dict:
    row = {
        "rank": rank, "name": (proj["name"] or "").upper(),
        "team": proj["team_abbr"], "opponent": proj["opponent_abbr"],
        "k_rate": round(proj["k_rate"], 3),
        "batters_faced": round(proj["batters_faced"], 1),
        "k_mean": round(proj["k_mean"], 1),
    }
    for j, p in proj["ladder"].items():
        row[f"p{j}"] = round(p * 100)
    return row


def _sw_line(r: dict) -> str:
    head = f"{r['rank']}. {r['name']}"
    if r["team"] or r["opponent"]:
        head += f" ({r['team']} vs {r['opponent']})"
    ladder = " · ".join(f"{j}+ {r[f'p{j}']}%" for j in range(1, 11) if f"p{j}" in r)
    return " — ".join([head, ladder,
                       f"rate {r['k_rate']} · {r['batters_faced']} BF · proj {r['k_mean']} K"])


def _sw_prompt(rows: list[dict], as_of, book) -> str:
    stamp = " · ".join(x for x in ("Strikeout model (alt-K)",
                                   f"as of {as_of}" if as_of else None, book) if x)
    banner = f"[{stamp}]\n\n" if stamp else ""
    body = "\n".join(_sw_line(r) for r in rows) or "(no probable starters available yet)"
    return banner + (
        'Create a premium sports-betting "strikeout watch" graphic for the brand '
        '"Chances Make Champions" (CMC).\n\n'
        "STYLE: cinematic, black background with gold and amber smoke, floating gold "
        "dust, a gold crown, gritty brush/graffiti lettering, neon-gold accents. "
        'Big brush title at the top: "STRIKEOUT WATCH". Moody, high-end, premium.\n\n'
        f"LAYOUT: a clean numbered list of {len(rows)} starting pitchers. Each row "
        "shows the pitcher (team vs opponent), the full ladder of 1+ through 10+ "
        "strikeout probabilities, the expected K rate, batters faced, and projected K "
        "total. Even spacing.\n\n"
        "KEY: N+ % = our model's probability of at least N strikeouts (Binomial on the "
        "pitcher's K rate x batters faced, opponent-adjusted) — pick your alt-strikeout "
        "line from the arms at the top. These are probabilities, NOT guarantees.\n\n"
        "CRITICAL: reproduce ALL text below EXACTLY as written — do not change, "
        "abbreviate, reorder, add, or invent any name, team, number, %, or stat.\n\n"
        f"PITCHERS:\n{body}"
    )


def _opp_team_id(repo, game_pk: int, pitcher_team_abbr: str) -> int | None:
    """The opposing team's id for a probable starter (the side the pitcher is NOT on)."""
    g = repo.game(game_pk) or {}
    if g.get("home_team_abbr") == pitcher_team_abbr:
        return g.get("away_team_id")
    if g.get("away_team_abbr") == pitcher_team_abbr:
        return g.get("home_team_id")
    return None


def strikeout_watch(date: str, repo=None, *, count: int = STRIKEOUT_WATCH_SIZE,
                    as_of: str | None = None, book: str | None = None) -> dict:
    """Top-`count` probable starters by P(9+ K) — the alt-K board, now with the full
    P(1+..10+) ladder from the opponent-adjusted rate x batters-faced model."""
    import json as _json
    repo, conn = _open(repo)
    try:
        season = int(date[:4])
        min_starts = int(os.environ.get("RAMBO_K_MIN_STARTS", "5"))
        scored, seen = [], set()
        for s in repo.probable_starters(date):
            mid = s["mlb_id"]
            if mid in seen:
                continue
            seen.add(mid)
            rows_season = repo.player_season(mid, season, "pitching")
            try:
                gs = float((_json.loads(rows_season[0]["stats"]).get("season") or {}).get("gamesStarted") or 0)
            except Exception:
                gs = 0
            if gs < min_starts:
                continue
            starter = {
                "mlb_id": mid, "name": s.get("name") or "",
                "team_abbr": s.get("team_abbr", ""), "opponent_abbr": s.get("opponent_abbr", ""),
                "opponent_team_id": _opp_team_id(repo, s.get("game_pk"), s.get("team_abbr", "")),
            }
            proj = k_projection(repo, date, starter)
            if proj is None or proj["k_mean"] <= 0:
                continue
            scored.append(proj)
        scored.sort(key=lambda p: p["ladder"].get(9, 0.0), reverse=True)
        rows = [_sw_row(i + 1, p) for i, p in enumerate(scored[:count])]
        return {"title": "STRIKEOUT WATCH", "product": "Strikeout model (alt-K)",
                "count": len(rows), "rows": rows,
                "prompt": _sw_prompt(rows, as_of, book)}
    finally:
        if conn is not None:
            conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_strikeout_watch.py -v`
Expected: PASS — the new full-ladder test plus the file's pre-existing strikeout tests (adjust any pre-existing test that asserted the old `p8/p9/p10`-only shape: those keys still exist as `p8/p9/p10`, so they should still pass; if a pre-existing test asserts the exact row key set, update it to allow the new keys).

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/brains/ev/watch.py rambo-backend/tests/test_strikeout_watch.py
git commit -m "$(cat <<'EOF'
feat(betting): alt-K board shows full P(1+..10+) ladder

strikeout_watch now scores via k_projection (opponent-adjusted rate x
batters-faced) and emits the full ladder + k_rate/BF per arm.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Calibration backtest

**Files:**
- Create: `brains/ev/k_backtest.py`
- Create: `scripts/k_backtest.py`
- Test: `tests/test_k_backtest.py`

**Interfaces:**
- Consumes: `k_model.k_projection` (Task 3), `brains.ev.backtest.evaluate` (existing), `MlbRepo` (`conn`).
- Produces: `k_backtest.run(repo, start: str, end: str, thresholds=(6,7,8,9,10)) -> dict` → `{"n_starts": int, "skipped": int, <j>: <evaluate metrics>}`. CLI `scripts/k_backtest.py START END` prints it.

A pitching game log carries the start's `opponent_team_id` and `game_date`; the actual K count is `stats["stat"]["strikeOuts"]`. The projection is built as-of `game_date` (strict `<` inside the reads = leak-free).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_k_backtest.py
import json
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev import k_backtest


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _pit_log(conn, mlb_id, date, k, bf, opp_team):
    stats = json.dumps({"stat": {"strikeOuts": k, "battersFaced": bf}})
    conn.execute(
        "INSERT INTO player_game_logs (mlb_id, game_pk, game_date, stat_group, "
        "opponent_team_id, stats, source, scraped_at) VALUES (?,?,?,?,?,?,?,?)",
        (mlb_id, 0, date, "pitching", opp_team, stats, "mlb/statsapi:stats",
         "2026-06-28T00:00:00Z"))


def test_k_backtest_grades_thresholds_leakfree(tmp_path):
    conn = _conn(tmp_path)
    # history (so as-of projection is buildable) + graded starts in May
    for d in ("2026-04-02", "2026-04-09", "2026-04-16", "2026-04-23"):
        _pit_log(conn, 50, d, 8, 25, 200)
    _pit_log(conn, 50, "2026-05-05", 11, 26, 200)   # actual 11 K -> hits 6..10
    _pit_log(conn, 50, "2026-05-12", 3, 24, 200)    # actual 3 K -> misses 6..10
    repo = MlbRepo(conn)
    out = k_backtest.run(repo, "2026-05-01", "2026-05-31", thresholds=(6, 9))
    assert out["n_starts"] == 2
    assert set(out.keys()) >= {6, 9, "n_starts", "skipped"}
    # the 11-K start wins both thresholds; the 3-K start loses both
    assert out[6]["n"] == 2 and out[9]["n"] == 2
    assert 0.0 <= out[6]["win_rate"] <= 1.0


def test_k_backtest_skips_starts_without_history(tmp_path):
    conn = _conn(tmp_path)
    _pit_log(conn, 50, "2026-04-01", 7, 25, 200)    # first start: no prior -> projection None
    repo = MlbRepo(conn)
    out = k_backtest.run(repo, "2026-04-01", "2026-04-30", thresholds=(6,))
    assert out["n_starts"] == 0 and out["skipped"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_k_backtest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brains.ev.k_backtest'`

- [ ] **Step 3: Write minimal implementation**

Create `brains/ev/k_backtest.py`:

```python
"""Leak-free calibration backtest for the strikeout model. For each historical start
it builds k_projection as-of the start date and grades P(j+ K) against the real K
count from the game log. No odds — pure calibration (Brier / log-loss / bins)."""
from __future__ import annotations

import json

from brains.ev.k_model import k_projection
from brains.ev import backtest


def run(repo, start: str, end: str, thresholds=(6, 7, 8, 9, 10)) -> dict:
    conn = repo.conn
    rows = conn.execute(
        "SELECT mlb_id, game_date, opponent_team_id, stats FROM player_game_logs "
        "WHERE stat_group='pitching' AND game_date BETWEEN ? AND ? "
        "ORDER BY game_date, mlb_id", (start, end)).fetchall()
    records = {j: [] for j in thresholds}
    n_starts = skipped = 0
    for r in rows:
        stat = (json.loads(r["stats"]).get("stat") or {})
        actual = stat.get("strikeOuts")
        if actual is None:
            skipped += 1
            continue
        date = r["game_date"]
        starter = {"mlb_id": r["mlb_id"], "name": "", "team_abbr": "",
                   "opponent_abbr": "", "opponent_team_id": r["opponent_team_id"]}
        proj = k_projection(repo, date, starter)   # before_date defaults to date -> leak-free
        if proj is None:
            skipped += 1
            continue
        n_starts += 1
        for j in thresholds:
            records[j].append({"p": proj["ladder"].get(j, 0.0),
                               "win": 1 if int(actual) >= j else 0})
    out: dict = {"n_starts": n_starts, "skipped": skipped}
    for j in thresholds:
        out[j] = backtest.evaluate(records[j])
    return out
```

Create `scripts/k_backtest.py`:

```python
"""CLI: leak-free strikeout-model calibration backtest.
Usage: python scripts/k_backtest.py START END"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.migrate import get_connection
from repositories.mlb_repo import MlbRepo
from brains.ev.k_backtest import run


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python scripts/k_backtest.py START_DATE END_DATE", file=sys.stderr)
        return 2
    db = os.environ.get("RAMBO_DB_PATH", "data/mlb_ingest.db")
    conn = get_connection(db)
    try:
        print(json.dumps(run(MlbRepo(conn), sys.argv[1], sys.argv[2]), indent=2))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_k_backtest.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/brains/ev/k_backtest.py rambo-backend/scripts/k_backtest.py rambo-backend/tests/test_k_backtest.py
git commit -m "$(cat <<'EOF'
feat(betting): leak-free strikeout calibration backtest

Grades P(j+ K) as-of each historical start vs the real K count, per
threshold, via the shared k_projection. Free, no odds.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Live run + full-suite gate

**Files:** none (operational verification).

**Interfaces:** consumes everything above against the real `data/mlb_ingest.db` (season game logs already present).

- [ ] **Step 1: Run the calibration backtest over a populated window**

```bash
cd rambo-backend && ./.venv/Scripts/python.exe scripts/k_backtest.py 2026-05-01 2026-06-20
```
Expected: JSON with `n_starts` in the hundreds and, per threshold (6–10), `n`, `brier`, `log_loss`, and `calibration` bins populated. Record whether predicted vs actual track within each bin (e.g. when it says ~40% for 8+, does ~40% actually hit?). A large gap = miscalibration to report, not hide.

- [ ] **Step 2: Render the live board and eyeball the ladder**

```bash
cd rambo-backend && ./.venv/Scripts/python.exe -c "from brains.ev.watch import strikeout_watch; import json; b=strikeout_watch('2026-06-29'); print('rows', b['count']); [print(r['rank'], r['name'], 'rate', r['k_rate'], 'BF', r['batters_faced'], 'p6', r.get('p6'), 'p8', r.get('p8'), 'p10', r.get('p10')) for r in b['rows'][:5]]"
```
Expected: ranked starters with a monotone-decreasing ladder (p1 ≥ p2 ≥ … ≥ p10) and plausible rates (~0.18–0.30) / BF (~22–26). Note any arm with an implausible rate (would indicate a sample/clamp issue).

- [ ] **Step 3: Run the full backend test suite (gate)**

Run: `cd rambo-backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: all prior tests still pass plus the new ones. No regressions.

- [ ] **Step 4: Commit the recorded calibration result + push**

```bash
git commit --allow-empty -m "$(cat <<'EOF'
chore(betting): record alt-K calibration backtest result

<paste per-threshold brier/log_loss + a one-line calibration read here>

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
git push -u origin feat/altk-board-phase1
```

---

## Notes for the implementer

- `k_projection`'s `before_date` defaults to the game's own date, and every underlying read uses strict `<` — so the same function is leak-free in the backtest and current in the live board. Do not pass a future `before_date`.
- The opponent modifier is deliberately bounded `[0.85, 1.20]` and the rate `[0.05, 0.45]`; do not widen these to chase a board look — they prevent thin-sample blowups.
- A pitching game log without `opponent_team_id` simply gets a neutral opponent modifier (1.0) — acceptable; the backtest still grades it.
- Do not tune `LG_K_PCT`, the clamps, or the blend weight to the May calibration result — report the calibration honestly (per spec §1/§8). A miscalibrated finding is a valid result that informs Phase 2.
