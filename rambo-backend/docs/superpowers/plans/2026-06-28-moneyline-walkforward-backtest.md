# Moneyline Walk-Forward Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a leak-free, walk-forward backtest of the moneyline run-model that grades calibration, ROI, and CLV against the real historical book lines it would have faced.

**Architecture:** Add point-in-time (`_asof`) feature reads to `MlbRepo`, an `evaluate_game_asof` that uses them, a historical-odds ingestion path that reuses the existing Odds API normalizer, and a `walkforward.run` harness that assembles graded records and scores them through the existing `backtest.evaluate()` at two entry prices (early + close).

**Tech Stack:** Python 3, SQLite, FastAPI, httpx, pytest. The Odds API historical endpoint. Anthropic Haiku for the plain-English read.

## Global Constraints

- DB path from `RAMBO_DB_PATH` env (default `data/mlb_ingest.db`); tests use `tmp_path` + `apply_migrations(conn, "db/migrations")`.
- All repo reads are read-only; `MlbRepo` never writes.
- Point-in-time invariant: as-of reads use strictly `<` the target date, never `<=`.
- Ingestion clients return a `RunResult` and land via the existing source/normalize path; per-item try/except so one bad date/event never aborts a run.
- Historical Odds API calls log `x-requests-remaining`; bulk backfill stops and reports if quota hits zero. Confirm the historical credit multiplier from that header on the first real call before any bulk run.
- Innings summed via `outs/3` from pitching game logs (never parse the "6.1" `inningsPitched` string).
- Commit messages use Bash heredoc; co-author line `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Branch: `feat/moneyline-walkforward-backtest` (already created).

---

### Task 1: Point-in-time repo reads (`team_runs_asof`, `pitcher_era_asof`)

**Files:**
- Modify: `repositories/mlb_repo.py` (add two methods next to `team_runs` / `pitcher_era`)
- Test: `tests/test_mlb_repo_asof.py` (create)

**Interfaces:**
- Consumes: existing `games` table (final scores), `player_game_logs` (pitching JSON at `stats["stat"]`).
- Produces:
  - `MlbRepo.team_runs_asof(team_id: int, season: int, before_date: str) -> dict | None` → `{"runs_scored": float, "runs_allowed": float, "games_played": int}` from final games with `official_date < before_date`; `None` if no prior games.
  - `MlbRepo.pitcher_era_asof(mlb_id: int | None, season: int, before_date: str) -> float | None` → `9 * sum(earnedRuns) / (sum(outs)/3)` over pitching logs with `game_date < before_date`; `None` if no prior innings or `mlb_id is None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mlb_repo_asof.py
import json
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _game(conn, pk, date, home_id, away_id, hs, as_):
    conn.execute(
        "INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
        "home_team_abbr, away_team_abbr, home_score, away_score, scraped_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (pk, date, home_id, away_id, "AAA", "BBB", hs, as_, "2026-06-28T00:00:00Z"))


def test_team_runs_asof_excludes_target_date_and_after(tmp_path):
    conn = _conn(tmp_path)
    # team 147 home: scores 5 (allows 3) on 06-01, scores 2 (allows 4) on 06-02
    _game(conn, 1, "2026-06-01", 147, 200, 5, 3)
    _game(conn, 2, "2026-06-02", 147, 200, 2, 4)
    _game(conn, 3, "2026-06-03", 147, 200, 9, 9)  # must NOT count for before='2026-06-03'
    repo = MlbRepo(conn)
    r = repo.team_runs_asof(147, 2026, "2026-06-03")
    assert r == {"runs_scored": 7.0, "runs_allowed": 7.0, "games_played": 2}


def test_team_runs_asof_counts_away_games(tmp_path):
    conn = _conn(tmp_path)
    _game(conn, 1, "2026-06-01", 200, 147, 3, 8)  # 147 away: scored 8, allowed 3
    repo = MlbRepo(conn)
    r = repo.team_runs_asof(147, 2026, "2026-06-02")
    assert r == {"runs_scored": 8.0, "runs_allowed": 3.0, "games_played": 1}


def test_team_runs_asof_none_when_no_prior(tmp_path):
    conn = _conn(tmp_path)
    _game(conn, 1, "2026-06-05", 147, 200, 5, 3)
    assert MlbRepo(conn).team_runs_asof(147, 2026, "2026-06-05") is None


def _plog(conn, mlb_id, date, er, outs):
    stats = json.dumps({"stat": {"earnedRuns": er, "outs": outs, "inningsPitched": "x"}})
    conn.execute(
        "INSERT INTO player_game_logs (mlb_id, game_pk, game_date, stat_group, "
        "stats, source, scraped_at) VALUES (?,?,?,?,?,?,?)",
        (mlb_id, 0, date, "pitching", stats, "mlb/statsapi:stats", "2026-06-28T00:00:00Z"))


def test_pitcher_era_asof_strict_before(tmp_path):
    conn = _conn(tmp_path)
    _plog(conn, 500, "2026-06-01", 2, 18)   # 6.0 IP, 2 ER
    _plog(conn, 500, "2026-06-02", 1, 9)    # 3.0 IP, 1 ER  -> total 3 ER / 9 IP
    _plog(conn, 500, "2026-06-03", 9, 3)    # must NOT count for before='2026-06-03'
    era = MlbRepo(conn).pitcher_era_asof(500, 2026, "2026-06-03")
    assert abs(era - (9 * 3 / 9.0)) < 1e-9  # 3.00


def test_pitcher_era_asof_none_paths(tmp_path):
    conn = _conn(tmp_path)
    assert MlbRepo(conn).pitcher_era_asof(None, 2026, "2026-06-03") is None
    assert MlbRepo(conn).pitcher_era_asof(500, 2026, "2026-06-03") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rambo-backend && python -m pytest tests/test_mlb_repo_asof.py -v`
Expected: FAIL — `AttributeError: 'MlbRepo' object has no attribute 'team_runs_asof'`

- [ ] **Step 3: Write minimal implementation**

Add to `repositories/mlb_repo.py`, immediately after `team_runs` and `pitcher_era` respectively:

```python
    def team_runs_asof(self, team_id: int, season: int,
                       before_date: str) -> Optional[dict]:
        """Runs scored/allowed and games played from FINAL games strictly before
        `before_date` — the leak-free counterpart to team_runs(). None if the team
        has no completed games yet this season."""
        row = self.conn.execute(
            """SELECT
                 SUM(CASE WHEN home_team_id=? THEN home_score ELSE away_score END) AS rs,
                 SUM(CASE WHEN home_team_id=? THEN away_score ELSE home_score END) AS ra,
                 COUNT(*) AS gp
               FROM games
               WHERE official_date < ?
                 AND home_score IS NOT NULL AND away_score IS NOT NULL
                 AND (home_team_id=? OR away_team_id=?)
                 AND CAST(strftime('%Y', official_date) AS INTEGER)=?""",
            (team_id, team_id, before_date, team_id, team_id, season)).fetchone()
        if not row or not row["gp"]:
            return None
        return {"runs_scored": float(row["rs"]), "runs_allowed": float(row["ra"]),
                "games_played": int(row["gp"])}

    def pitcher_era_asof(self, mlb_id: Optional[int], season: int,
                         before_date: str) -> Optional[float]:
        """ERA from pitching game logs strictly before `before_date` — leak-free
        counterpart to pitcher_era(). Innings via outs/3 (never the '6.1' string).
        None if no prior innings."""
        if mlb_id is None:
            return None
        import json
        rows = self.conn.execute(
            "SELECT stats FROM player_game_logs WHERE mlb_id=? AND stat_group='pitching' "
            "AND game_date < ?", (mlb_id, before_date)).fetchall()
        er_total = 0.0
        outs_total = 0
        for r in rows:
            stat = (json.loads(r["stats"]).get("stat") or {})
            try:
                er_total += float(stat.get("earnedRuns") or 0)
                outs_total += int(stat.get("outs") or 0)
            except (TypeError, ValueError):
                continue
        if outs_total <= 0:
            return None
        return 9.0 * er_total / (outs_total / 3.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd rambo-backend && python -m pytest tests/test_mlb_repo_asof.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/repositories/mlb_repo.py rambo-backend/tests/test_mlb_repo_asof.py
git commit -m "$(cat <<'EOF'
feat(betting): point-in-time team_runs_asof + pitcher_era_asof

Leak-free as-of reads (strictly < target date) for the walk-forward
backtest. Innings via outs/3, never the inningsPitched string.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `evaluate_game_asof` in the moneyline model

**Files:**
- Modify: `brains/ev/moneyline_model.py` (add `evaluate_game_asof` after `evaluate_game`)
- Test: `tests/test_moneyline_asof.py` (create)

**Interfaces:**
- Consumes: `MlbRepo.team_runs_asof`, `MlbRepo.pitcher_era_asof` (Task 1); existing `expected_runs`, `winprob_from_runs`, `matchup_winprob`, `pythag_winpct`, `devig_two_way`, `market_anchored_prob`.
- Produces: `moneyline_model.evaluate_game_asof(repo, season: int, g: dict, before_date: str) -> dict | None`. Same return dict shape as `evaluate_game` (`model_home`, `model_away`, `book_home`, `book_away`, `diff`, abbrs, prices), or `None` when as-of team runs are missing. `g` must carry `home_team_id`, `away_team_id`, `home_probable_pitcher_id`, `away_probable_pitcher_id`, `home_team_abbr`, `away_team_abbr`, `home_price`, `away_price`, `game_pk`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_moneyline_asof.py
import json
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev.moneyline_model import evaluate_game_asof


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _final(conn, pk, date, home_id, away_id, hs, as_):
    conn.execute(
        "INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
        "home_team_abbr, away_team_abbr, home_score, away_score, scraped_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (pk, date, home_id, away_id, "NYY", "BOS", hs, as_, "2026-06-28T00:00:00Z"))


def test_evaluate_game_asof_uses_prior_only(tmp_path):
    conn = _conn(tmp_path)
    # strong home team (147): wins big in May; weak away team (111)
    for d in ("2026-05-01", "2026-05-05", "2026-05-10"):
        _final(conn, hash(d) % 100000, d, 147, 111, 8, 2)
    repo = MlbRepo(conn)
    g = {"game_pk": 999, "home_team_id": 147, "away_team_id": 111,
         "home_probable_pitcher_id": None, "away_probable_pitcher_id": None,
         "home_team_abbr": "NYY", "away_team_abbr": "BOS",
         "home_price": -120, "away_price": 100}
    out = evaluate_game_asof(repo, 2026, g, "2026-06-01")
    assert out is not None
    assert out["model_home"] > 0.5            # model leans the strong home team
    assert abs(out["model_home"] + out["model_away"] - 1.0) < 1e-9
    assert out["diff"] == out["model_home"] - out["book_home"]


def test_evaluate_game_asof_none_without_prior(tmp_path):
    conn = _conn(tmp_path)
    repo = MlbRepo(conn)
    g = {"game_pk": 1, "home_team_id": 147, "away_team_id": 111,
         "home_probable_pitcher_id": None, "away_probable_pitcher_id": None,
         "home_team_abbr": "NYY", "away_team_abbr": "BOS",
         "home_price": -110, "away_price": -110}
    assert evaluate_game_asof(repo, 2026, g, "2026-04-01") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rambo-backend && python -m pytest tests/test_moneyline_asof.py -v`
Expected: FAIL — `ImportError: cannot import name 'evaluate_game_asof'`

- [ ] **Step 3: Write minimal implementation**

Add to `brains/ev/moneyline_model.py` after `evaluate_game`:

```python
def evaluate_game_asof(repo, season: int, g: dict, before_date: str) -> dict | None:
    """Point-in-time twin of evaluate_game: builds team-run and starter-ERA
    features from data STRICTLY BEFORE `before_date` (no leakage), anchors to the
    given de-vigged line, and returns the same dict shape. None when as-of team
    run data is missing. Used by the walk-forward backtest."""
    hr = repo.team_runs_asof(g["home_team_id"], season, before_date)
    ar = repo.team_runs_asof(g["away_team_id"], season, before_date)
    if not hr or not ar:
        return None
    home_era = repo.pitcher_era_asof(g["home_probable_pitcher_id"], season, before_date)
    away_era = repo.pitcher_era_asof(g["away_probable_pitcher_id"], season, before_date)
    hg, ag = hr["games_played"], ar["games_played"]
    if home_era and away_era and hg and ag:
        exp_home = expected_runs(hr["runs_scored"] / hg, away_era)
        exp_away = expected_runs(ar["runs_scored"] / ag, home_era)
        model_home = winprob_from_runs(exp_home, exp_away)
    else:
        model_home = matchup_winprob(
            pythag_winpct(hr["runs_scored"], hr["runs_allowed"]),
            pythag_winpct(ar["runs_scored"], ar["runs_allowed"]))
    book_home, book_away = devig_two_way(g["home_price"], g["away_price"])
    anchored_home = market_anchored_prob(model_home, book_home)
    return {
        "game_pk": g["game_pk"],
        "home_abbr": g["home_team_abbr"], "away_abbr": g["away_team_abbr"],
        "home_price": g["home_price"], "away_price": g["away_price"],
        "book_home": book_home, "book_away": book_away,
        "model_home": anchored_home, "model_away": 1.0 - anchored_home,
        "diff": anchored_home - book_home,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd rambo-backend && python -m pytest tests/test_moneyline_asof.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/brains/ev/moneyline_model.py rambo-backend/tests/test_moneyline_asof.py
git commit -m "$(cat <<'EOF'
feat(betting): evaluate_game_asof — point-in-time moneyline eval

Mirrors evaluate_game but sources features strictly before the game date
for the leak-free walk-forward backtest.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Historical Odds API fetch + source wiring

**Files:**
- Modify: `ingestion/the_odds_api_client.py` (add `fetch_moneyline_historical`)
- Modify: `ingestion/sources.py` (route a new `odds_api_historical` source)
- Test: `tests/test_odds_api_historical.py` (create)

**Interfaces:**
- Consumes: `config.the_odds_api` (`BASE`, `SPORT`, `REGIONS`, `MARKETS`, `ODDS_FORMAT`, `SOURCE_ID`, `api_key`); `RunResult`. The existing `_normalize_the_odds_api` (registered in `DISPATCH` under `SOURCE_ID`) — reused verbatim by landing under the same `actor_id`.
- Produces:
  - `the_odds_api_client.fetch_moneyline_historical(snapshot_iso: str, *, client=None) -> RunResult` — `actor_id == cfg.SOURCE_ID`, items = the historical `data` events, each stamped `_captured_at = response.timestamp`.
  - `sources.pull_source(conn, "odds_api_historical", {"snapshot": "<iso>"})` lands it raw.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_odds_api_historical.py
import httpx
from ingestion import the_odds_api_client as toa


class _FakeResp:
    def __init__(self, payload):
        self._p = payload
        self.headers = {"x-requests-remaining": "19990"}
    def raise_for_status(self):
        pass
    def json(self):
        return self._p


class _FakeClient:
    def __init__(self, payload):
        self._p = payload
        self.last_url = None
        self.last_params = None
    def get(self, url, params=None):
        self.last_url = url
        self.last_params = params
        return _FakeResp(self._p)
    def close(self):
        pass


def test_fetch_historical_unwraps_data_and_stamps_timestamp(monkeypatch):
    monkeypatch.setenv("THE_ODDS_API_KEY", "k")
    payload = {
        "timestamp": "2026-05-01T16:00:00Z",
        "previous_timestamp": "2026-05-01T15:55:00Z",
        "next_timestamp": "2026-05-01T16:05:00Z",
        "data": [
            {"id": "abc", "home_team": "New York Yankees",
             "away_team": "Boston Red Sox", "commence_time": "2026-05-01T23:05:00Z",
             "bookmakers": []},
        ],
    }
    client = _FakeClient(payload)
    run = toa.fetch_moneyline_historical("2026-05-01T16:00:00Z", client=client)
    assert "/historical/sports/baseball_mlb/odds" in client.last_url
    assert client.last_params["date"] == "2026-05-01T16:00:00Z"
    assert run.item_count == 1
    assert run.actor_id == toa.cfg.SOURCE_ID          # routes through existing normalizer
    assert run.items[0]["_captured_at"] == "2026-05-01T16:00:00Z"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rambo-backend && python -m pytest tests/test_odds_api_historical.py -v`
Expected: FAIL — `AttributeError: module 'ingestion.the_odds_api_client' has no attribute 'fetch_moneyline_historical'`

- [ ] **Step 3: Write minimal implementation**

Add to `ingestion/the_odds_api_client.py`:

```python
def fetch_moneyline_historical(snapshot_iso: str, *,
                               client: Optional[httpx.Client] = None) -> RunResult:
    """Historical MLB moneylines at a past instant. The Odds API wraps events in
    {timestamp, data:[...]}; we unwrap `data` and stamp each event's _captured_at
    from the response timestamp so the existing live normalizer handles them
    verbatim. Costs the historical credit multiplier — logs requests-remaining."""
    key = cfg.api_key()
    if not key:
        raise RuntimeError("THE_ODDS_API_KEY not set in .env")
    own = client is None
    client = client or httpx.Client(timeout=DEFAULT_TIMEOUT)
    try:
        url = f"{cfg.BASE}/historical/sports/{cfg.SPORT}/odds"
        params = {"apiKey": key, "regions": cfg.REGIONS, "markets": cfg.MARKETS,
                  "oddsFormat": cfg.ODDS_FORMAT, "date": snapshot_iso}
        resp = client.get(url, params=params)
        resp.raise_for_status()
        body = resp.json() or {}
        snap_ts = body.get("timestamp") or snapshot_iso
        events = body.get("data") or []
        for e in events:
            e["_captured_at"] = snap_ts
        remaining = resp.headers.get("x-requests-remaining")
        logger.info("the-odds-api historical %s: %d events (requests remaining: %s)",
                    snapshot_iso, len(events), remaining)
        run_id = f"{cfg.SOURCE_ID}:hist:{snap_ts}"
        return RunResult(actor_id=cfg.SOURCE_ID, run_id=run_id, dataset_id=run_id,
                         items=events, item_count=len(events), estimated_cost_usd=0.0)
    finally:
        if own:
            client.close()
```

Add to `ingestion/sources.py` — extend `OTHER_SOURCES` and add a branch:

```python
OTHER_SOURCES = {"odds_api", "odds_props", "statcast", "odds_api_historical"}
```

```python
    elif source == "odds_api_historical":
        from ingestion import the_odds_api_client as toa
        snap = params.get("snapshot")
        if not snap:
            raise ValueError("odds_api_historical source requires snapshot (ISO 8601)")
        run = toa.fetch_moneyline_historical(snap)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd rambo-backend && python -m pytest tests/test_odds_api_historical.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/ingestion/the_odds_api_client.py rambo-backend/ingestion/sources.py rambo-backend/tests/test_odds_api_historical.py
git commit -m "$(cat <<'EOF'
feat(betting): historical moneyline fetch via The Odds API

Unwraps the {timestamp,data} historical envelope and lands events under
the live SOURCE_ID so the existing normalizer maps them to game_pk.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Two-snapshot odds backfill

**Files:**
- Create: `ingestion/odds_backfill.py`
- Test: `tests/test_odds_backfill.py` (create)

**Interfaces:**
- Consumes: `MlbRepo.final_games` (provides `game_pk`, `official_date` — note: needs `game_datetime`, see Step 3 query), `sources.pull_source(conn, "odds_api_historical", {"snapshot": iso})`, `ingestion.normalize.normalize_pending`.
- Produces:
  - `odds_backfill.snapshot_times(commence_iso: str) -> tuple[str, str]` → (early, closing) ISO instants = commence−4h, commence−5min.
  - `odds_backfill.backfill_odds(conn, start: str, end: str, *, pull=None) -> dict` → `{"snapshots": int, "events": int, "skipped_no_datetime": int}`. `pull` defaults to `sources.pull_source`; injectable for tests. Dedups identical snapshot instants across the slate so each distinct instant is one call.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_odds_backfill.py
from db.migrate import get_connection, apply_migrations
from ingestion import odds_backfill


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def test_snapshot_times_offsets():
    early, close = odds_backfill.snapshot_times("2026-05-01T23:05:00+00:00")
    assert early == "2026-05-01T19:05:00+00:00"   # -4h
    assert close == "2026-05-01T23:00:00+00:00"   # -5min


def _final_dt(conn, pk, date, dt):
    conn.execute(
        "INSERT INTO games (game_pk, official_date, game_datetime, home_team_id, "
        "away_team_id, home_team_abbr, away_team_abbr, home_score, away_score, scraped_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (pk, date, dt, 1, 2, "AAA", "BBB", 4, 3, "2026-06-28T00:00:00Z"))


def test_backfill_dedups_snapshots_and_counts(tmp_path):
    conn = _conn(tmp_path)
    # two games at the SAME first pitch -> early/close instants shared -> 2 calls total
    _final_dt(conn, 10, "2026-05-01", "2026-05-01T23:05:00+00:00")
    _final_dt(conn, 11, "2026-05-01", "2026-05-01T23:05:00+00:00")
    calls = []

    def fake_pull(c, source, params):
        calls.append(params["snapshot"])
        return {"items": 2}

    out = odds_backfill.backfill_odds(conn, "2026-05-01", "2026-05-01", pull=fake_pull)
    assert sorted(set(calls)) == ["2026-05-01T19:05:00+00:00", "2026-05-01T23:00:00+00:00"]
    assert len(calls) == 2                      # deduped, not 4
    assert out["snapshots"] == 2


def test_backfill_skips_games_without_datetime(tmp_path):
    conn = _conn(tmp_path)
    conn.execute(
        "INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
        "home_team_abbr, away_team_abbr, home_score, away_score, scraped_at) "
        "VALUES (99,'2026-05-01',1,2,'AAA','BBB',4,3,'2026-06-28T00:00:00Z')")
    out = odds_backfill.backfill_odds(conn, "2026-05-01", "2026-05-01",
                                      pull=lambda *a, **k: {"items": 0})
    assert out["skipped_no_datetime"] == 1
    assert out["snapshots"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rambo-backend && python -m pytest tests/test_odds_backfill.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingestion.odds_backfill'`

- [ ] **Step 3: Write minimal implementation**

```python
# ingestion/odds_backfill.py
"""Backfill historical moneyline snapshots (The Odds API historical endpoint) so the
walk-forward backtest can grade ROI/CLV against the real lines. For each final game
we pull two instants — an early line (commence-4h, starters usually confirmed) and a
closing line (commence-5min). Snapshot instants are deduped across the slate so each
distinct instant is a single API call. Idempotent (odds_lines UPSERT on snapshot_key)."""
from __future__ import annotations

import datetime as _dt
import logging
import sqlite3

logger = logging.getLogger("rambo.ingestion.odds_backfill")

EARLY_BEFORE = _dt.timedelta(hours=4)
CLOSE_BEFORE = _dt.timedelta(minutes=5)


def snapshot_times(commence_iso: str) -> tuple[str, str]:
    """(early, closing) ISO instants for a game's commence time."""
    t = _dt.datetime.fromisoformat(commence_iso)
    return (t - EARLY_BEFORE).isoformat(), (t - CLOSE_BEFORE).isoformat()


def backfill_odds(conn: sqlite3.Connection, start: str, end: str, *, pull=None) -> dict:
    """Pull early+closing historical moneylines for every final game in [start,end].
    `pull` defaults to sources.pull_source (injectable for tests)."""
    if pull is None:
        from ingestion.sources import pull_source as pull
    rows = conn.execute(
        "SELECT game_pk, game_datetime FROM games "
        "WHERE official_date BETWEEN ? AND ? "
        "AND home_score IS NOT NULL AND away_score IS NOT NULL "
        "ORDER BY official_date, game_pk", (start, end)).fetchall()

    instants: set[str] = set()
    skipped = 0
    for r in rows:
        dt = r["game_datetime"] if isinstance(r, sqlite3.Row) else r[1]
        if not dt:
            skipped += 1
            continue
        early, close = snapshot_times(dt)
        instants.add(early)
        instants.add(close)

    events = 0
    for snap in sorted(instants):
        try:
            res = pull(conn, "odds_api_historical", {"snapshot": snap})
            events += int(res.get("items") or 0)
        except Exception as exc:                 # one bad instant shouldn't abort
            logger.warning("historical odds backfill failed for %s: %s", snap, exc)
    from ingestion.normalize import normalize_pending
    normalize_pending(conn)
    return {"snapshots": len(instants), "events": events,
            "skipped_no_datetime": skipped}
```

Note: `normalize_pending` is a no-op against the fake-pull tests (nothing landed), so the test assertions on `calls`/`snapshots` hold. The real path lands raw rows that `normalize_pending` then maps.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd rambo-backend && python -m pytest tests/test_odds_backfill.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/ingestion/odds_backfill.py rambo-backend/tests/test_odds_backfill.py
git commit -m "$(cat <<'EOF'
feat(betting): two-snapshot historical odds backfill

Early (commence-4h) + closing (commence-5min) moneyline snapshots per
final game, deduped across the slate to one call per distinct instant.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Walk-forward harness

**Files:**
- Create: `brains/ev/walkforward.py`
- Test: `tests/test_walkforward.py` (create)

**Interfaces:**
- Consumes: `MlbRepo` (`final_games`, `moneyline_slate`, `team_runs_asof`, `pitcher_era_asof`), `moneyline_model.evaluate_game_asof` (Task 2), `backtest.evaluate` (existing). For odds it reads `odds_lines` directly via two helper queries (early vs closing price per game/side).
- Produces:
  - `walkforward.pick_record(ev: dict, win_home: bool, early: dict, close: dict) -> dict | None` → `{p, win, odds_early, odds_close}` for the model's leaned side, or `None` if no lean / missing price. `early`/`close` are `{"home": price, "away": price}`.
  - `walkforward.run(repo, start: str, end: str) -> dict` → `{"early": <evaluate>, "close": <evaluate>, "n": int, "skipped_features": int, "skipped_odds": int}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_walkforward.py
from brains.ev.walkforward import pick_record


def _ev(model_home, book_home, gpk=1):
    return {"game_pk": gpk, "home_abbr": "NYY", "away_abbr": "BOS",
            "model_home": model_home, "model_away": 1 - model_home,
            "book_home": book_home, "book_away": 1 - book_home}


def test_pick_record_leans_home_maps_both_prices():
    ev = _ev(0.60, 0.52)                       # model > book on home -> bet home
    rec = pick_record(ev, win_home=True,
                      early={"home": -120, "away": 100},
                      close={"home": -140, "away": 120})
    assert rec["p"] == 0.60
    assert rec["win"] == 1
    assert rec["odds_early"] == -120
    assert rec["odds_close"] == -140


def test_pick_record_leans_away_uses_away_win_and_prices():
    ev = _ev(0.40, 0.50)                       # model < book on home -> value on away
    rec = pick_record(ev, win_home=False,      # away won
                      early={"home": -120, "away": 100},
                      close={"home": -130, "away": 110})
    assert rec["p"] == 0.60                     # model_away
    assert rec["win"] == 1                      # away won
    assert rec["odds_early"] == 100
    assert rec["odds_close"] == 110


def test_pick_record_none_when_no_lean():
    ev = _ev(0.52, 0.52)                        # no edge either way
    assert pick_record(ev, win_home=True,
                       early={"home": -110, "away": -110},
                       close={"home": -110, "away": -110}) is None


def test_pick_record_none_when_price_missing():
    ev = _ev(0.60, 0.52)
    assert pick_record(ev, win_home=True,
                       early={"home": None, "away": 100},
                       close={"home": -120, "away": 100}) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rambo-backend && python -m pytest tests/test_walkforward.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brains.ev.walkforward'`

- [ ] **Step 3: Write minimal implementation**

```python
# brains/ev/walkforward.py
"""Walk-forward moneyline backtest. For each final game in a date range, build a
point-in-time prediction (features strictly before game day), bet the side the model
leans vs the de-vigged early line, and grade the resulting records at BOTH the early
and closing price — so calibration is shared but ROI/CLV expose the entry-timing
effect. Scores through the existing backtest.evaluate()."""
from __future__ import annotations

import sqlite3

from brains.ev.moneyline_model import evaluate_game_asof
from brains.ev import backtest


def pick_record(ev: dict, win_home: bool, early: dict, close: dict) -> dict | None:
    """Build a graded record for the model's leaned side, or None when there's no
    lean or a needed price is missing. `early`/`close` map side -> American price."""
    if ev["model_home"] > ev["book_home"]:
        side, p, won = "home", ev["model_home"], win_home
    elif ev["model_away"] > ev["book_away"]:
        side, p, won = "away", ev["model_away"], not win_home
    else:
        return None
    oe, oc = early.get(side), close.get(side)
    if oe is None or oc is None:
        return None
    return {"p": p, "win": 1 if won else 0, "odds_early": oe, "odds_close": oc}


def _prices_at(conn: sqlite3.Connection, game_pk: int,
               lo: str, hi: str) -> dict | None:
    """home/away moneyline price from the latest snapshot within [lo,hi] (an
    early- or closing-window), pregame books only. None if the window is empty."""
    rows = conn.execute(
        """WITH ml AS (
               SELECT side, price,
                      ROW_NUMBER() OVER (PARTITION BY side ORDER BY captured_at DESC) AS rn
               FROM odds_lines
               WHERE game_pk=? AND market='moneyline' AND price<>0
                 AND book NOT LIKE '%Live%' AND captured_at BETWEEN ? AND ?)
           SELECT side, price FROM ml WHERE rn=1""", (game_pk, lo, hi)).fetchall()
    out = {r["side"]: r["price"] for r in rows}
    return out if "home" in out and "away" in out else None


def run(repo, start: str, end: str) -> dict:
    """Grade every final game in [start,end]. Returns side-by-side early/close
    metrics plus coverage counters."""
    import datetime as _dt
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
        ev = evaluate_game_asof(repo, season, s, date)
        if ev is None:
            skipped_features += 1
            continue
        dt = s.get("game_datetime")
        if not dt:
            skipped_odds += 1
            continue
        t = _dt.datetime.fromisoformat(dt)
        early = _prices_at(conn, g["game_pk"],
                           (t - _dt.timedelta(hours=6)).isoformat(),
                           (t - _dt.timedelta(hours=2)).isoformat())
        close = _prices_at(conn, g["game_pk"],
                           (t - _dt.timedelta(minutes=30)).isoformat(), t.isoformat())
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

- [ ] **Step 4: Run test to verify it passes**

Run: `cd rambo-backend && python -m pytest tests/test_walkforward.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/brains/ev/walkforward.py rambo-backend/tests/test_walkforward.py
git commit -m "$(cat <<'EOF'
feat(betting): walk-forward moneyline backtest harness

Point-in-time picks graded at early + closing price side by side; shared
calibration, ROI/CLV expose entry timing. Scores via backtest.evaluate.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: API endpoint + CLI surface

**Files:**
- Modify: `api/betting.py` (add `GET /betting/backtest`)
- Create: `scripts/walkforward.py`
- Test: `tests/test_backtest_api.py` (create)

**Interfaces:**
- Consumes: `walkforward.run` (Task 5), `repositories.mlb_repo.MlbRepo`, `db.migrate.get_connection`, the existing `router` in `api/betting.py`.
- Produces: `GET /betting/backtest?start=YYYY-MM-DD&end=YYYY-MM-DD` → the `walkforward.run` dict. `scripts/walkforward.py` CLI: `python scripts/walkforward.py <start> <end>` prints the JSON.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_backtest_api.py
import os
from fastapi.testclient import TestClient
from db.migrate import get_connection, apply_migrations


def _seed(path):
    conn = get_connection(path)
    apply_migrations(conn, "db/migrations")
    conn.commit()
    conn.close()


def test_backtest_endpoint_empty_range_ok(tmp_path, monkeypatch):
    db = str(tmp_path / "t.db")
    _seed(db)
    monkeypatch.setenv("RAMBO_DB_PATH", db)
    # import after env is set so the module reads the test DB path
    import importlib
    import api.betting as betting
    importlib.reload(betting)
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(betting.router)
    client = TestClient(app)
    r = client.get("/betting/backtest", params={"start": "2026-05-01", "end": "2026-05-02"})
    assert r.status_code == 200
    body = r.json()
    assert body["n"] == 0
    assert "early" in body and "close" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rambo-backend && python -m pytest tests/test_backtest_api.py -v`
Expected: FAIL — 404 (route not yet defined)

- [ ] **Step 3: Write minimal implementation**

Add to `api/betting.py` (after the existing routes):

```python
@router.get("/backtest")
def backtest_endpoint(start: str, end: str) -> dict:
    """Walk-forward moneyline backtest over [start,end]: calibration + ROI/CLV at the
    early and closing line. Data-only; grades historical picks, never places bets."""
    from db.migrate import get_connection
    from repositories.mlb_repo import MlbRepo
    from brains.ev.walkforward import run
    conn = get_connection(_DB)
    try:
        return run(MlbRepo(conn), start, end)
    finally:
        conn.close()
```

Create `scripts/walkforward.py`:

```python
"""CLI: walk-forward moneyline backtest. Usage: python scripts/walkforward.py START END
Prints the metrics JSON (early + closing line, side by side)."""
from __future__ import annotations

import json
import os
import sys

# allow running from repo root or rambo-backend
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.migrate import get_connection
from repositories.mlb_repo import MlbRepo
from brains.ev.walkforward import run


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python scripts/walkforward.py START_DATE END_DATE", file=sys.stderr)
        return 2
    start, end = sys.argv[1], sys.argv[2]
    db = os.environ.get("RAMBO_DB_PATH", "data/mlb_ingest.db")
    conn = get_connection(db)
    try:
        print(json.dumps(run(MlbRepo(conn), start, end), indent=2))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd rambo-backend && python -m pytest tests/test_backtest_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/api/betting.py rambo-backend/scripts/walkforward.py rambo-backend/tests/test_backtest_api.py
git commit -m "$(cat <<'EOF'
feat(betting): /betting/backtest endpoint + walkforward CLI

Serves the walk-forward metrics (early vs close) for the /edge dashboard
and exposes a CLI runner. Data-only — grades history, places nothing.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Live integration smoke run + full-suite gate

**Files:** none (operational verification)

**Interfaces:** consumes everything above against the real `data/mlb_ingest.db`.

- [ ] **Step 1: Backfill a slice of season finals (free statsapi)**

```bash
cd rambo-backend && python -c "from db.migrate import get_connection; from ingestion.backfill import backfill_results; print(backfill_results(get_connection('data/mlb_ingest.db'), '2026-05-01', '2026-05-07'))"
```
Expected: a summary dict with `finals` > 0.

- [ ] **Step 2: Backfill historical odds for the same slice — CONFIRM CREDIT COST FIRST**

Run ONE day first and read the logged `requests remaining` to confirm the historical multiplier before the week:
```bash
cd rambo-backend && python -c "from db.migrate import get_connection; from ingestion.odds_backfill import backfill_odds; print(backfill_odds(get_connection('data/mlb_ingest.db'), '2026-05-01', '2026-05-01'))"
```
Expected: `{"snapshots": N, "events": M, ...}` with M > 0 and the log line showing remaining quota. If the per-call cost is higher than expected, stop and report before widening the range.

- [ ] **Step 3: Run the walk-forward backtest**

```bash
cd rambo-backend && python scripts/walkforward.py 2026-05-01 2026-05-07
```
Expected: JSON with `n` > 0 and populated `early`/`close` metric blocks (roi, brier, log_loss, avg_clv, calibration). If `n` is 0, inspect `skipped_features` / `skipped_odds` to see which gate is empty.

- [ ] **Step 4: Run the full backend test suite (gate)**

Run: `cd rambo-backend && python -m pytest -q`
Expected: all prior tests still pass plus the new ones (≈557 + new). No regressions.

- [ ] **Step 5: Commit any operational notes / push the branch**

```bash
git add -A && git commit -m "$(cat <<'EOF'
chore(betting): walk-forward backtest verified on May slice

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)" --allow-empty
git push -u origin feat/moneyline-walkforward-backtest
```

---

## Notes for the implementer

- The `_prices_at` windows in `walkforward.run` (early = commence−6h..−2h, close = −30min..0) are intentionally wider than the exact backfill instants (−4h, −5min) so a snapshot that the API served a few minutes off still lands in the right bucket. Keep them non-overlapping.
- `moneyline_slate(date)` already excludes in-game "Live" books and price=0 rows and carries `game_datetime` + probable pitcher ids — reuse it rather than re-querying `games`/`odds_lines` for the slate.
- If `moneyline_slate` returns a game the historical backfill couldn't price (no snapshot in window), that game increments `skipped_odds` — expected for dates before odds coverage begins.
- **Deferred (spec §4.3):** the Haiku one-paragraph plain-English read of the metrics is intentionally NOT in these tasks. The raw `evaluate()` blocks (roi/brier/log_loss/avg_clv/calibration) are self-explanatory for a first pass, and the metrics are deterministic numbers that don't need an LLM to be trustworthy. Add it as a fast-follow once we've seen real output and know which numbers Daniel wants narrated — wire `brains/ev/explainer.py`'s `complete`-injection pattern so it stays testable.
