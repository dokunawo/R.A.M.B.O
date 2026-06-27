# Player Watch + Moneyline Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two daily CMC "board" outputs — Player Watch (top-11 HR chances) and Moneyline Board (every slate game) — each delivered as a ready-to-paste ChatGPT image prompt, plus put the existing moneyline output in game-time order.

**Architecture:** Reuse the existing EV-brain + slip pattern. Capture the schedule's `gameDate` into a new `games.game_datetime` column; extract a shared per-game moneyline evaluator; add a `brains/ev/watch.py` module with `player_watch()` / `moneyline_board()` builders; expose two new read endpoints; wire both prompts into `cmc-daily.ps1`. No new external data sources.

**Tech Stack:** Python 3.11/3.14, FastAPI, SQLite (STRICT tables), pytest. Windows PowerShell 5.1 for the daily script.

## Global Constraints

- Brand on both cards: **Chances Make Champions (CMC)**, black/gold/crown, consistent with existing slip prompts. Player Watch title `PLAYER WATCH`; moneyline card title `MONEYLINE BOARD`.
- **Honest data only:** never instruct ChatGPT to invent stats. Pitch-mix and BvP are omitted. Optional fields (weather, statcast, pitcher name) are omitted from a row when absent — never rendered as `None`/blank-faked.
- Data-only (Sentinel boundary): no bet-placement capability in any new code.
- Player Watch = **11 rows**, HR market only, ranked by HR% (`model_p`).
- Moneyline Board lists **every** slate game in **game-time order** (earliest `game_datetime` first; `away_team_abbr` tiebreaker; alphabetical fallback when timestamp is null). The existing `ml` daily-edge/slip output uses the same game-time order.
- Tests use real SQLite (`get_connection` + `apply_migrations` + direct INSERTs), mirroring `tests/test_ev_moneyline.py`. No mocks.
- Run all pytest from the `rambo-backend/` directory.

---

### Task 1: Capture game start time (`games.game_datetime`)

**Files:**
- Create: `rambo-backend/db/migrations/009_game_datetime.sql`
- Modify: `rambo-backend/ingestion/normalize.py` (the schedule mapper ~lines 226-248, and `_upsert_game` ~lines 109-133)
- Modify: `rambo-backend/repositories/mlb_repo.py` (`moneyline_slate` ~lines 199-225)
- Test: `rambo-backend/tests/test_watch_schedule_time.py`

**Interfaces:**
- Produces: `games.game_datetime` (TEXT, ISO UTC) persisted on schedule ingest; `MlbRepo.moneyline_slate(date)` rows now include key `"game_datetime"` and are returned in game-time order.

- [ ] **Step 1: Write the failing test**

```python
# rambo-backend/tests/test_watch_schedule_time.py
from db.migrate import get_connection, apply_migrations
from ingestion.raw_store import land_raw
from ingestion.normalize import normalize_pending
from ingestion.apify_client_wrapper import RunResult
from repositories.mlb_repo import MlbRepo


def _schedule_item(game_pk, home_abbr, away_abbr, game_dt):
    return {
        "gamePk": game_pk, "officialDate": "2026-06-27", "gameDate": game_dt,
        "season": "2026", "gameType": "R",
        "status": {"detailedState": "Scheduled"},
        "teams": {
            "home": {"team": {"id": 147, "name": "h", "abbreviation": home_abbr}},
            "away": {"team": {"id": 111, "name": "a", "abbreviation": away_abbr}},
        },
        "venue": {"id": 1, "name": "Park"},
    }


def test_game_datetime_persisted_and_slate_ordered(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    # two games, later one landed first to prove ordering is by time, not insert order
    items = [_schedule_item(2, "AAA", "BBB", "2026-06-27T23:10:00Z"),
             _schedule_item(1, "CCC", "DDD", "2026-06-27T17:05:00Z")]
    land_raw(conn, RunResult("mlb/statsapi:schedule", "r", "d", items, 2, 0.0))
    normalize_pending(conn)
    now = "2026-06-27T12:00:00Z"
    for pk in (1, 2):
        conn.execute("INSERT INTO odds_lines (game_pk, book, market, side, price, captured_at) "
                     "VALUES (?,?,'moneyline','home',-110,?)", (pk, "DraftKings", now))
        conn.execute("INSERT INTO odds_lines (game_pk, book, market, side, price, captured_at) "
                     "VALUES (?,?,'moneyline','away',-110,?)", (pk, "DraftKings", now))
    slate = MlbRepo(conn).moneyline_slate("2026-06-27")
    assert [g["game_pk"] for g in slate] == [1, 2]                 # earliest first
    assert slate[0]["game_datetime"] == "2026-06-27T17:05:00Z"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_watch_schedule_time.py -v`
Expected: FAIL — `game_datetime` column does not exist / KeyError.

- [ ] **Step 3: Create the migration**

```sql
-- rambo-backend/db/migrations/009_game_datetime.sql
-- First-pitch timestamp (statsapi schedule gameDate) for game-time ordering.
ALTER TABLE games ADD COLUMN game_datetime TEXT;
```

- [ ] **Step 4: Capture `gameDate` in the schedule mapper**

In `rambo-backend/ingestion/normalize.py`, inside the `_upsert_game(conn, {...})` call in the schedule normalize function (the dict that currently has `"official_date": _first(item, "officialDate", "gameDate")`), add this entry (e.g. right after `official_date`):

```python
        "game_datetime": _dig(item, "gameDate"),
```

- [ ] **Step 5: Add the column to `_upsert_game`'s INSERT + UPDATE**

In `_upsert_game`, add `game_datetime` to the column list, the VALUES list, and the `ON CONFLICT ... DO UPDATE SET` clause:

- Column list: change `(game_pk, official_date, season, game_type, status_detail,` to
  `(game_pk, official_date, game_datetime, season, game_type, status_detail,`
- VALUES list: change `(:game_pk,:official_date,:season,:game_type,:status_detail,` to
  `(:game_pk,:official_date,:game_datetime,:season,:game_type,:status_detail,`
- In `DO UPDATE SET`, add a line (after `status_detail=excluded.status_detail,`):
  `              game_datetime=excluded.game_datetime,`

- [ ] **Step 6: Return `game_datetime` + order the slate**

In `rambo-backend/repositories/mlb_repo.py`, in `moneyline_slate`, add `g.game_datetime,` to the SELECT column list (e.g. right after `g.game_pk,`) and replace the trailing `GROUP BY g.game_pk` with:

```sql
               GROUP BY g.game_pk
               ORDER BY g.game_datetime IS NULL, g.game_datetime, g.away_team_abbr
```

- [ ] **Step 7: Run test to verify it passes**

Run: `python -m pytest tests/test_watch_schedule_time.py -v`
Expected: PASS

- [ ] **Step 8: Run the moneyline suite to confirm no regression**

Run: `python -m pytest tests/test_ev_moneyline.py -v`
Expected: PASS (all existing tests).

- [ ] **Step 9: Commit**

```bash
git add rambo-backend/db/migrations/009_game_datetime.sql rambo-backend/ingestion/normalize.py rambo-backend/repositories/mlb_repo.py rambo-backend/tests/test_watch_schedule_time.py
git commit -m "feat(ev): capture games.game_datetime + order moneyline slate by first pitch"
```

---

### Task 2: Shared per-game moneyline evaluator

Extract the per-game math currently inlined in `MoneylineMarket.raw_picks` into a reusable `evaluate_game`, returning both sides, so the Moneyline Board and the `ml` market share one code path. Add `game_pk`/`game_datetime` to `Pick` for later ordering.

**Files:**
- Modify: `rambo-backend/brains/ev/types.py` (add two `Pick` fields)
- Modify: `rambo-backend/brains/ev/moneyline_model.py` (add `evaluate_game`)
- Modify: `rambo-backend/brains/ev/market.py` (`MoneylineMarket.raw_picks` ~lines 122-164)
- Test: `rambo-backend/tests/test_watch_moneyline.py`

**Interfaces:**
- Consumes: `MlbRepo.moneyline_slate` rows (now incl. `game_datetime`), `team_runs`, `pitcher_era`.
- Produces:
  - `Pick.game_pk: int = 0`, `Pick.game_datetime: str = ""`
  - `moneyline_model.evaluate_game(repo, season: int, g: dict) -> dict | None` returning keys:
    `game_pk, game_datetime, home_abbr, away_abbr, home_price, away_price,
     book_home, book_away, model_home, model_away, diff, home_support, away_support`
    where `model_*` are anchored win probs (sum to 1.0) and `diff = model_home - book_home`.

- [ ] **Step 1: Write the failing test**

```python
# rambo-backend/tests/test_watch_moneyline.py
import json
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev.moneyline_model import evaluate_game


def _game(conn, pk, dt, home_abbr, away_abbr, h_pid=None, a_pid=None):
    conn.execute(
        "INSERT INTO games (game_pk, official_date, game_datetime, home_team_id, "
        "away_team_id, home_team_abbr, away_team_abbr, home_probable_pitcher_id, "
        "away_probable_pitcher_id, scraped_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (pk, "2026-06-27", dt, 147, 111, home_abbr, away_abbr, h_pid, a_pid,
         "2026-06-27T00:00:00Z"))
    for side, price in (("home", -120), ("away", 100)):
        conn.execute("INSERT INTO odds_lines (game_pk, book, market, side, price, "
                     "captured_at) VALUES (?, 'DraftKings','moneyline',?,?,?)",
                     (pk, side, price, "2026-06-27T12:00:00Z"))


def test_evaluate_game_returns_both_sides(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    now = "2026-06-27T00:00:00Z"
    conn.execute("INSERT INTO team_season_stats VALUES (147,2026,800,600,162,'mlb',?)", (now,))
    conn.execute("INSERT INTO team_season_stats VALUES (111,2026,600,800,162,'mlb',?)", (now,))
    _game(conn, 1, "2026-06-27T17:05:00Z", "NYY", "BOS")
    g = MlbRepo(conn).moneyline_slate("2026-06-27")[0]
    ev = evaluate_game(MlbRepo(conn), 2026, g)
    assert ev["home_abbr"] == "NYY" and ev["away_abbr"] == "BOS"
    assert abs((ev["model_home"] + ev["model_away"]) - 1.0) < 1e-9
    assert ev["diff"] > 0                      # strong home team underrated by even-ish line
    assert ev["game_datetime"] == "2026-06-27T17:05:00Z"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_watch_moneyline.py -v`
Expected: FAIL — `cannot import name 'evaluate_game'`.

- [ ] **Step 3: Add `game_pk`/`game_datetime` to `Pick`**

In `rambo-backend/brains/ev/types.py`, add two fields at the END of the `Pick` dataclass (after `rationale: str = ""`), so existing positional construction is unaffected:

```python
    game_pk: int = 0
    game_datetime: str = ""
```

- [ ] **Step 4: Add `evaluate_game` to `moneyline_model.py`**

Append to `rambo-backend/brains/ev/moneyline_model.py`:

```python
def evaluate_game(repo, season: int, g: dict) -> dict | None:
    """Both-side model/book numbers for one `moneyline_slate` game, or None when
    team run data is missing. `diff = model_home - book_home` (signed lean toward
    home). model_home/model_away are market-anchored and sum to 1.0."""
    hr, ar = repo.team_runs(g["home_team_id"], season), repo.team_runs(g["away_team_id"], season)
    if not hr or not ar:
        return None
    home_era = repo.pitcher_era(g["home_probable_pitcher_id"], season)
    away_era = repo.pitcher_era(g["away_probable_pitcher_id"], season)
    hg, ag = hr["games_played"], ar["games_played"]
    if home_era and away_era and hg and ag:
        exp_home = expected_runs(hr["runs_scored"] / hg, away_era)
        exp_away = expected_runs(ar["runs_scored"] / ag, home_era)
        model_home = winprob_from_runs(exp_home, exp_away)
        home_support = f"vs {away_era:.2f} ERA SP"
        away_support = f"vs {home_era:.2f} ERA SP"
    else:
        model_home = matchup_winprob(
            pythag_winpct(hr["runs_scored"], hr["runs_allowed"]),
            pythag_winpct(ar["runs_scored"], ar["runs_allowed"]))
        home_support = away_support = "Pythag (no SP)"
    book_home, book_away = devig_two_way(g["home_price"], g["away_price"])
    anchored_home = market_anchored_prob(model_home, book_home)
    return {
        "game_pk": g["game_pk"], "game_datetime": g.get("game_datetime"),
        "home_abbr": g["home_team_abbr"], "away_abbr": g["away_team_abbr"],
        "home_price": g["home_price"], "away_price": g["away_price"],
        "book_home": book_home, "book_away": book_away,
        "model_home": anchored_home, "model_away": 1.0 - anchored_home,
        "diff": anchored_home - book_home,
        "home_support": home_support, "away_support": away_support,
    }
```

- [ ] **Step 5: Refactor `MoneylineMarket.raw_picks` to use it**

In `rambo-backend/brains/ev/market.py`, ensure `evaluate_game` is imported (extend the existing `from brains.ev.moneyline_model import (...)` block to include `evaluate_game`). Replace the body of `MoneylineMarket.raw_picks` (the loop over `repo.moneyline_slate(date)`) with:

```python
    def raw_picks(self, repo, date: str) -> list[Pick]:
        season = int(date[:4])
        picks: list[Pick] = []
        for g in repo.moneyline_slate(date):
            ev = evaluate_game(repo, season, g)
            if ev is None:
                continue
            if ev["diff"] >= 0:
                tid, abbr, opp = g["home_team_id"], ev["home_abbr"], ev["away_abbr"]
                mp, bp, price, support = (ev["model_home"], ev["book_home"],
                                          g["home_price"], ev["home_support"])
            else:
                tid, abbr, opp = g["away_team_id"], ev["away_abbr"], ev["home_abbr"]
                mp, bp, price, support = (ev["model_away"], ev["book_away"],
                                          g["away_price"], ev["away_support"])
            abbr = abbr or ""
            picks.append(Pick(
                market="ml", mlb_id=tid, name=abbr.upper(), initials=abbr.upper(),
                team=abbr, opponent=opp or "", hand="",
                pick=f"MONEYLINE LEAN ({price:+d})", line=0.0, multiplier=float(price),
                breakeven=round(bp, 4), model_p=round(mp, 4), edge=round(mp - bp, 4),
                support=support, tags=["LEAN"], glow="gold",
                headshot_url=_TEAM_LOGO.format(team_id=tid), rationale="",
                game_pk=ev["game_pk"], game_datetime=ev["game_datetime"] or "",
            ))
        return picks
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_watch_moneyline.py tests/test_ev_moneyline.py -v`
Expected: PASS — the new test plus all existing moneyline tests (proves the refactor preserved behavior).

- [ ] **Step 7: Commit**

```bash
git add rambo-backend/brains/ev/types.py rambo-backend/brains/ev/moneyline_model.py rambo-backend/brains/ev/market.py rambo-backend/tests/test_watch_moneyline.py
git commit -m "feat(ev): shared evaluate_game + Pick game_pk/game_datetime"
```

---

### Task 3: Game-time ordering for the `ml` output

Put the existing moneyline list (`daily_edge`) and slip (`build_slip`) in game-time order instead of lean-ranked. Other markets keep probability ranking.

**Files:**
- Modify: `rambo-backend/brains/ev/engine.py` (`daily_edge` sort ~line 23)
- Modify: `rambo-backend/brains/ev/slip.py` (`build_slip` ranking ~lines 41-51)
- Test: `rambo-backend/tests/test_ev_moneyline.py` (add one test)

**Interfaces:**
- Consumes: `Pick.game_datetime`, `Pick.team` (from Task 2).
- Produces: `daily_edge(date, "ml")` and `build_slip(picks, "ml")` ordered by `(game_datetime or "~", team)`.

- [ ] **Step 1: Write the failing test**

Append to `rambo-backend/tests/test_ev_moneyline.py`:

```python
def test_ml_output_in_game_time_order(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    now = "2026-06-27T00:00:00Z"
    conn.execute("INSERT INTO team_season_stats VALUES (147,2026,800,600,162,'mlb',?)", (now,))
    conn.execute("INSERT INTO team_season_stats VALUES (111,2026,600,800,162,'mlb',?)", (now,))
    # two games; the later-starting one inserted first
    for pk, dt, home, away in [(2, "2026-06-27T23:10:00Z", "LAD", "SDP"),
                               (1, "2026-06-27T17:05:00Z", "NYY", "BOS")]:
        conn.execute("INSERT INTO games (game_pk, official_date, game_datetime, "
                     "home_team_id, away_team_id, home_team_abbr, away_team_abbr, "
                     "scraped_at) VALUES (?,?,?,147,111,?,?,?)", (pk, "2026-06-27", dt, home, away, now))
        for side, price in (("home", -120), ("away", 100)):
            conn.execute("INSERT INTO odds_lines (game_pk, book, market, side, price, "
                         "captured_at) VALUES (?, 'DraftKings','moneyline',?,?,?)",
                         (pk, side, price, "2026-06-27T12:00:00Z"))
    from brains.ev.engine import daily_edge
    picks = daily_edge("2026-06-27", "ml", repo=MlbRepo(conn), threshold=-1.0)
    assert [p.game_pk for p in picks] == [1, 2]            # earliest first, not lean-ranked
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ev_moneyline.py::test_ml_output_in_game_time_order -v`
Expected: FAIL — picks come back lean-ranked (order [2,1] or by edge), not [1,2].

- [ ] **Step 3: Order `daily_edge` by game time for ml**

In `rambo-backend/brains/ev/engine.py`, replace `picks.sort(key=lambda pk: pk.edge, reverse=True)` with:

```python
        if market == "ml":
            picks.sort(key=lambda pk: (pk.game_datetime or "~", pk.team))
        else:
            picks.sort(key=lambda pk: pk.edge, reverse=True)
```

- [ ] **Step 4: Order `build_slip` by game time for ml**

In `rambo-backend/brains/ev/slip.py`, replace the ranking block (the `key = ...` line through the dedupe loop, lines ~41-51) with:

```python
    if market == "ml":
        ordered = sorted(picks, key=lambda p: (p.game_datetime or "~", p.team))
    else:
        ordered = sorted(picks, key=lambda p: p.model_p, reverse=True)
    # One play per player: prop ladders repeat a player; keep each player's first
    # (best-ranked / earliest) row before taking the top N.
    seen: set[int] = set()
    ranked: list[Pick] = []
    for p in ordered:
        if p.mlb_id in seen:
            continue
        seen.add(p.mlb_id)
        ranked.append(p)
    ranked = ranked[:requested]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_ev_moneyline.py tests/test_ev_slip.py -v`
Expected: PASS (new ordering test + existing slip tests).

- [ ] **Step 6: Commit**

```bash
git add rambo-backend/brains/ev/engine.py rambo-backend/brains/ev/slip.py rambo-backend/tests/test_ev_moneyline.py
git commit -m "feat(ev): ml daily-edge + slip ordered by game time"
```

---

### Task 4: Repo display getters (`player_bats`, `player_name`)

**Files:**
- Modify: `rambo-backend/repositories/mlb_repo.py` (add two getters near `pitcher_throws` ~line 124)
- Test: `rambo-backend/tests/test_watch_player.py`

**Interfaces:**
- Produces: `MlbRepo.player_bats(mlb_id) -> str | None`, `MlbRepo.player_name(mlb_id) -> str | None`.

- [ ] **Step 1: Write the failing test**

```python
# rambo-backend/tests/test_watch_player.py
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo


def test_player_bats_and_name(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    conn.execute("INSERT INTO players (mlb_id, full_name, bats, throws, updated_at) "
                 "VALUES (605141,'Mookie Betts','R','R','2026-06-27T00:00:00Z')")
    repo = MlbRepo(conn)
    assert repo.player_bats(605141) == "R"
    assert repo.player_name(605141) == "Mookie Betts"
    assert repo.player_bats(999) is None and repo.player_name(999) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_watch_player.py -v`
Expected: FAIL — `MlbRepo` has no attribute `player_bats`.

- [ ] **Step 3: Add the getters**

In `rambo-backend/repositories/mlb_repo.py`, after `pitcher_throws`, add:

```python
    def player_bats(self, mlb_id: int) -> Optional[str]:
        row = self.conn.execute(
            "SELECT bats FROM players WHERE mlb_id=?", (mlb_id,)).fetchone()
        return row["bats"] if row else None

    def player_name(self, mlb_id: int) -> Optional[str]:
        row = self.conn.execute(
            "SELECT full_name FROM players WHERE mlb_id=?", (mlb_id,)).fetchone()
        return row["full_name"] if row else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_watch_player.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/repositories/mlb_repo.py rambo-backend/tests/test_watch_player.py
git commit -m "feat(ev): MlbRepo player_bats + player_name getters"
```

---

### Task 5: `player_watch` builder + prompt

**Files:**
- Create: `rambo-backend/brains/ev/watch.py`
- Test: `rambo-backend/tests/test_watch_player.py` (extend)

**Interfaces:**
- Consumes: `daily_edge` (HR market), `MlbRepo` getters (`player_game_context`, `game`, `game_weather`, `player_statcast`, `player_bats`, `player_name`), `parks.hr_factor`, `features.{TEMP_PARKS, LG_BARREL, LG_HARD_HIT}`, `slip.PRODUCT`.
- Produces: `watch.PLAYER_WATCH_SIZE = 11`; `watch.player_watch(date, repo=None, *, count=PLAYER_WATCH_SIZE, as_of=None, book=None) -> dict` with keys `{title, product, count, rows, prompt}`; each row is a dict with `rank, name, team, bats, pitcher, hr_pct, venue, temp, env_pct, wind, barrel, hard_hit, form`.

- [ ] **Step 1: Write the failing test**

Append to `rambo-backend/tests/test_watch_player.py`:

```python
import json


def _seed_hr_player(conn, now):
    conn.execute("INSERT INTO players (mlb_id, full_name, bats, throws, current_team_id, "
                 "updated_at) VALUES (1,'Byron Buxton','R','R',147,?)", (now,))
    conn.execute("INSERT INTO players (mlb_id, full_name, bats, throws, current_team_id, "
                 "updated_at) VALUES (50,'Michael Lorenzen','R','R',111,?)", (now,))
    conn.execute("INSERT INTO player_season_stats (mlb_id, season, stat_group, stats, "
                 "source, as_of_date, scraped_at) VALUES (1,2026,'hitting',?,'mlb','2026-06-27',?)",
                 (json.dumps({"season": {"homeRuns": 22, "plateAppearances": 300}}), now))
    conn.execute("INSERT INTO player_statcast VALUES (1,2026,14.0,48.0,'savant',?)", (now,))
    conn.execute("INSERT INTO games (game_pk, official_date, game_datetime, home_team_id, "
                 "away_team_id, home_team_abbr, away_team_abbr, away_probable_pitcher_id, "
                 "venue_name, scraped_at) VALUES (10,'2026-06-27','2026-06-27T18:00:00Z',"
                 "147,111,'MIN','DET',50,'Target Field',?)", (now,))
    conn.execute("INSERT INTO game_weather VALUES (10,81,'Clear','12 mph, In From RCF',?)", (now,))
    conn.execute("INSERT INTO prop_lines (game_pk, mlb_id, book, market, line, multiplier, "
                 "player_name_raw, captured_at) VALUES (10,1,'DK Pick6','HR',0.5,2.0,"
                 "'Byron Buxton','2026-06-27T12:00:00Z')")


def test_player_watch_builds_real_rows(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    now = "2026-06-27T00:00:00Z"
    _seed_hr_player(conn, now)
    from brains.ev.watch import player_watch
    out = player_watch("2026-06-27", repo=MlbRepo(conn))
    assert out["title"] == "PLAYER WATCH"
    assert out["count"] == 1
    row = out["rows"][0]
    assert row["name"] == "BYRON BUXTON" and row["bats"] == "R"
    assert row["pitcher"] == "Michael Lorenzen"
    assert row["venue"] == "Target Field" and row["temp"] == 81
    assert "Michael Lorenzen" in out["prompt"] and "PLAYER WATCH" in out["prompt"]
    assert "barrel 14" in out["prompt"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_watch_player.py::test_player_watch_builds_real_rows -v`
Expected: FAIL — no module `brains.ev.watch`.

- [ ] **Step 3: Create `watch.py` with `player_watch`**

```python
# rambo-backend/brains/ev/watch.py
"""Player Watch (top-11 HR board) + Moneyline Board. Each turns EV-brain data into
a ready-to-paste CMC ChatGPT image prompt. Formatting + real-data enrichment only —
no new modeling. Honest: optional fields are omitted when absent, never faked."""
from __future__ import annotations
import os
from brains.ev.engine import daily_edge
from brains.ev.moneyline_model import evaluate_game
from brains.ev.parks import hr_factor
from brains.ev.features import TEMP_PARKS, LG_BARREL, LG_HARD_HIT
from brains.ev.slip import PRODUCT

DB_PATH = os.environ.get("RAMBO_DB_PATH", "data/mlb_ingest.db")
PLAYER_WATCH_SIZE = 11


def _open(repo):
    if repo is not None:
        return repo, None
    from db.migrate import get_connection
    from repositories.mlb_repo import MlbRepo
    conn = get_connection(DB_PATH)
    return MlbRepo(conn), conn


def _pw_row(repo, date: str, season: int, rank: int, pick) -> dict:
    ctx = repo.player_game_context(pick.mlb_id, date) or {}
    game_pk = ctx.get("game_pk")
    home_abbr = ctx.get("home_abbr") or ""
    pitcher = ""
    if ctx.get("opp_pitcher_id"):
        pitcher = repo.player_name(ctx["opp_pitcher_id"]) or ""
    venue, temp, wind = "", None, ""
    if game_pk:
        g = repo.game(game_pk) or {}
        venue = g.get("venue_name") or ""
        w = repo.game_weather(game_pk) or {}
        temp = w.get("temp")
        wind = w.get("wind") or ""
    park = 1.0 if home_abbr in TEMP_PARKS else hr_factor(home_abbr)
    sc = repo.player_statcast(pick.mlb_id, season) or {}
    return {
        "rank": rank, "name": pick.name, "team": pick.team,
        "bats": repo.player_bats(pick.mlb_id) or "",
        "pitcher": pitcher, "hr_pct": round(pick.model_p * 100, 1),
        "venue": venue, "temp": temp, "env_pct": round((park - 1) * 100),
        "wind": wind, "barrel": sc.get("barrel_rate"), "hard_hit": sc.get("hard_hit"),
        "form": pick.support,
    }


def _pw_line(r: dict) -> str:
    head = f"{r['rank']}. {r['name']} ({r['team']} · {r['bats']}"
    if r["pitcher"]:
        head += f" · vs {r['pitcher']}"
    head += ")"
    parts = [head, f"HR {r['hr_pct']}%"]
    venue = r["venue"]
    if r["temp"] is not None and r["temp"] != "":
        venue = f"{venue} {r['temp']}°F" if venue else f"{r['temp']}°F"
    if venue:
        parts.append(venue)
    env = f"env {r['env_pct']:+d}%"
    if r["wind"]:
        env += f" · {r['wind']}"
    parts.append(env)
    sub = []
    if r["barrel"] is not None:
        sub.append(f"barrel {r['barrel']}%{'↑' if r['barrel'] >= LG_BARREL else '↓'}")
    if r["hard_hit"] is not None:
        sub.append(f"hardhit {r['hard_hit']}%{'↑' if r['hard_hit'] >= LG_HARD_HIT else '↓'}")
    if sub:
        parts.append(" / ".join(sub))
    if r["form"]:
        parts.append(r["form"])
    return " — ".join(parts)


def _pw_prompt(rows: list[dict], as_of, book) -> str:
    stamp = " · ".join(x for x in (PRODUCT["hr"], f"as of {as_of}" if as_of else None,
                                   book) if x)
    banner = f"[{stamp}]\n\n" if stamp else ""
    body = "\n".join(_pw_line(r) for r in rows) or "(no home-run board available today)"
    return banner + (
        'Create a premium sports-betting "home run watch" graphic for the brand '
        '"Chances Make Champions" (CMC).\n\n'
        "STYLE: cinematic, black background with gold and amber smoke, floating gold "
        "dust, a gold crown, gritty brush/graffiti lettering, neon-gold accents. "
        'Big brush title at the top: "PLAYER WATCH". Moody, high-end, premium.\n\n'
        f"LAYOUT: a clean numbered list of {len(rows)} hitters. Each row shows the "
        "player (team · bat hand · vs starting pitcher), a big HR%, the ballpark and "
        "temperature, the HR environment (park factor % + wind), the power tags, and "
        "recent form. Even spacing, easy to read.\n\n"
        "KEY: % = our model's home-run probability. ↑ = above league average, "
        "↓ = below. No pitch-mix or batter-vs-pitcher shown — figures are model and "
        "Statcast based.\n\n"
        "CRITICAL: reproduce ALL text below EXACTLY as written — do not change, "
        "abbreviate, reorder, add, or invent any name, team, number, %, or stat.\n\n"
        f"HITTERS:\n{body}"
    )


def player_watch(date: str, repo=None, *, count: int = PLAYER_WATCH_SIZE,
                 as_of: str | None = None, book: str | None = None) -> dict:
    repo, conn = _open(repo)
    try:
        season = int(date[:4])
        picks = daily_edge(date, "hr", repo=repo, threshold=-1.0)
        picks = sorted(picks, key=lambda p: p.model_p, reverse=True)
        seen: set[int] = set()
        top = []
        for p in picks:
            if p.mlb_id in seen:
                continue
            seen.add(p.mlb_id)
            top.append(p)
            if len(top) >= count:
                break
        rows = [_pw_row(repo, date, season, i + 1, p) for i, p in enumerate(top)]
        return {"title": "PLAYER WATCH", "product": PRODUCT["hr"],
                "count": len(rows), "rows": rows,
                "prompt": _pw_prompt(rows, as_of, book)}
    finally:
        if conn is not None:
            conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_watch_player.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/brains/ev/watch.py rambo-backend/tests/test_watch_player.py
git commit -m "feat(ev): player_watch (top-11 HR board) builder + prompt"
```

---

### Task 6: `moneyline_board` builder + prompt

**Files:**
- Modify: `rambo-backend/brains/ev/watch.py` (add `moneyline_board` + helpers)
- Test: `rambo-backend/tests/test_watch_moneyline.py` (extend)

**Interfaces:**
- Consumes: `MlbRepo.moneyline_slate` (ordered), `evaluate_game`.
- Produces: `watch.moneyline_board(date, repo=None, *, as_of=None, book=None) -> dict` with keys `{title, product, count, rows, prompt}`; each row dict has `rank, away, away_price, home, home_price, model_home_pct, model_away_pct, lean_side, lean_pct`. Rows are in slate (game-time) order; `lean_side` is `None` when the rounded lean is 0.0.

- [ ] **Step 1: Write the failing test**

Append to `rambo-backend/tests/test_watch_moneyline.py`:

```python
def test_moneyline_board_lists_every_game_in_order(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    now = "2026-06-27T00:00:00Z"
    conn.execute("INSERT INTO team_season_stats VALUES (147,2026,800,600,162,'mlb',?)", (now,))
    conn.execute("INSERT INTO team_season_stats VALUES (111,2026,600,800,162,'mlb',?)", (now,))
    _game(conn, 2, "2026-06-27T23:10:00Z", "LAD", "SDP")
    _game(conn, 1, "2026-06-27T17:05:00Z", "NYY", "BOS")
    from brains.ev.watch import moneyline_board
    out = moneyline_board("2026-06-27", repo=MlbRepo(conn))
    assert out["title"] == "MONEYLINE BOARD" and out["count"] == 2
    assert [r["home"] for r in out["rows"]] == ["NYY", "LAD"]      # game-time order
    r = out["rows"][0]
    assert r["away"] == "BOS" and r["model_home_pct"] + r["model_away_pct"] == 100
    assert "MONEYLINE BOARD" in out["prompt"] and "NYY" in out["prompt"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_watch_moneyline.py::test_moneyline_board_lists_every_game_in_order -v`
Expected: FAIL — `cannot import name 'moneyline_board'`.

- [ ] **Step 3: Add `moneyline_board` to `watch.py`**

Append to `rambo-backend/brains/ev/watch.py`:

```python
def _mb_row(rank: int, ev: dict) -> dict:
    diff_pct = round(ev["diff"] * 100, 1)
    if diff_pct == 0.0:
        lean_side, lean_pct = None, 0.0
    elif diff_pct > 0:
        lean_side, lean_pct = ev["home_abbr"], diff_pct
    else:
        lean_side, lean_pct = ev["away_abbr"], -diff_pct
    return {
        "rank": rank, "away": ev["away_abbr"], "away_price": ev["away_price"],
        "home": ev["home_abbr"], "home_price": ev["home_price"],
        "model_home_pct": round(ev["model_home"] * 100),
        "model_away_pct": round(ev["model_away"] * 100),
        "lean_side": lean_side, "lean_pct": lean_pct,
    }


def _mb_line(r: dict) -> str:
    head = (f"{r['rank']}. {r['away']} ({r['away_price']:+d}) @ "
            f"{r['home']} ({r['home_price']:+d}) — model: "
            f"{r['home']} {r['model_home_pct']}% / {r['away']} {r['model_away_pct']}%")
    if r["lean_side"]:
        head += f" — CMC lean: {r['lean_side']} +{r['lean_pct']}%"
    else:
        head += " — no lean"
    return head


def _mb_prompt(rows: list[dict], as_of, book) -> str:
    stamp = " · ".join(x for x in (PRODUCT["ml"], f"as of {as_of}" if as_of else None,
                                   book) if x)
    banner = f"[{stamp}]\n\n" if stamp else ""
    body = "\n".join(_mb_line(r) for r in rows) or "(no games on the board today)"
    return banner + (
        'Create a premium sports-betting "moneyline board" graphic for the brand '
        '"Chances Make Champions" (CMC).\n\n'
        "STYLE: cinematic, black background with gold and amber smoke, floating gold "
        "dust, a gold crown, gritty brush/graffiti lettering, neon-gold accents. "
        'Big brush title at the top: "MONEYLINE BOARD". Moody, high-end, premium.\n\n'
        f"LAYOUT: a clean numbered list of {len(rows)} games in start-time order. Each "
        "row shows the matchup (away @ home with book odds), our model win % for each "
        "side, and our suggested lean (or 'no lean'). Even spacing, easy to read.\n\n"
        "KEY: odds are the book's American moneyline. Our leans are small, bounded "
        "disagreements with the de-vigged book — they are reads, NOT guarantees. "
        "Build your own card from any side.\n\n"
        "CRITICAL: reproduce ALL text below EXACTLY as written — do not change, "
        "abbreviate, reorder, add, or invent any team, number, %, or odds.\n\n"
        f"GAMES:\n{body}"
    )


def moneyline_board(date: str, repo=None, *, as_of: str | None = None,
                    book: str | None = None) -> dict:
    repo, conn = _open(repo)
    try:
        season = int(date[:4])
        rows = []
        for g in repo.moneyline_slate(date):
            ev = evaluate_game(repo, season, g)
            if ev is None:
                continue
            rows.append(_mb_row(len(rows) + 1, ev))
        return {"title": "MONEYLINE BOARD", "product": PRODUCT["ml"],
                "count": len(rows), "rows": rows,
                "prompt": _mb_prompt(rows, as_of, book)}
    finally:
        if conn is not None:
            conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_watch_moneyline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/brains/ev/watch.py rambo-backend/tests/test_watch_moneyline.py
git commit -m "feat(ev): moneyline_board (full slate) builder + prompt"
```

---

### Task 7: API endpoints

**Files:**
- Modify: `rambo-backend/api/betting.py` (add two routes; import `watch`)
- Test: `rambo-backend/tests/test_ev_api.py` (add smoke tests)

**Interfaces:**
- Consumes: `watch.player_watch`, `watch.moneyline_board`, existing `_provenance`.
- Produces: `GET /betting/player-watch?date=` and `GET /betting/moneyline-board?date=`, each returning `{date, title, product, count, rows, prompt, provenance}`.

- [ ] **Step 1: Write the failing test**

First check how `test_ev_api.py` builds its client (it points the app at a temp DB via `RAMBO_DB_PATH` / TestClient). Mirror that existing fixture. Append two tests using the same setup the file already uses:

```python
def test_player_watch_endpoint(client):
    r = client.get("/betting/player-watch")
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "PLAYER WATCH"
    assert "prompt" in body and "provenance" in body


def test_moneyline_board_endpoint(client):
    r = client.get("/betting/moneyline-board")
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "MONEYLINE BOARD"
    assert "prompt" in body and "provenance" in body
```

(If `test_ev_api.py` uses a different fixture name than `client`, match it. If it has no reusable fixture, copy the app/TestClient setup from the file's existing test verbatim into these two.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ev_api.py -v`
Expected: FAIL — 404 on the new routes.

- [ ] **Step 3: Add the routes**

In `rambo-backend/api/betting.py`, add the import near the top imports:

```python
from brains.ev.watch import player_watch, moneyline_board
```

Then add two routes (after the existing `get_slip`):

```python
@router.get("/player-watch")
def get_player_watch(date: Optional[str] = None) -> dict:
    """Top-11 HR board + a ready-to-paste ChatGPT image prompt (+ provenance)."""
    d = date or datetime.date.today().isoformat()
    try:
        prov, as_of, _ = _provenance("hr")
        watch = player_watch(d, as_of=as_of, book="DraftKings Pick6")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"player_watch failed: {e}") from e
    return {"date": d, **watch, "provenance": prov}


@router.get("/moneyline-board")
def get_moneyline_board(date: Optional[str] = None) -> dict:
    """Every slate game (book odds + model %) + a ChatGPT image prompt (+ provenance)."""
    d = date or datetime.date.today().isoformat()
    try:
        prov, as_of, book = _provenance("ml")
        board = moneyline_board(d, as_of=as_of, book=book)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"moneyline_board failed: {e}") from e
    return {"date": d, **board, "provenance": prov}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ev_api.py -v`
Expected: PASS

- [ ] **Step 5: Run the full EV suite**

Run: `python -m pytest tests/ -k "ev or watch" -q`
Expected: PASS (all EV + watch tests).

- [ ] **Step 6: Commit**

```bash
git add rambo-backend/api/betting.py rambo-backend/tests/test_ev_api.py
git commit -m "feat(ev): /betting/player-watch + /betting/moneyline-board endpoints"
```

---

### Task 8: Wire both boards into `cmc-daily.ps1`

Add Player Watch + Moneyline Board to the daily console output and the Word doc.

**Files:**
- Modify: `cmc-daily.ps1` (repo root)

**Interfaces:**
- Consumes: `GET /betting/player-watch`, `GET /betting/moneyline-board` (via the existing `Get-Json` helper).

- [ ] **Step 1: Fetch the two boards**

In `cmc-daily.ps1`, after the `foreach ($m in $markets.Keys) { ... }` gathering loop (the block that builds `$results`), add:

```powershell
# Boards (read already-pulled data; free under -SkipPrep)
$playerWatch   = Get-Json "$Base/betting/player-watch?date=$Date"
$moneylineBoard = Get-Json "$Base/betting/moneyline-board?date=$Date"
```

- [ ] **Step 2: Print both prompts to the console**

After the existing `===== ChatGPT image prompts =====` loop (the `foreach ($r in $results)` that writes each `$r.Slip.prompt`), add:

```powershell
Write-Host ""
Write-Host "##### PLAYER WATCH #####" -ForegroundColor Magenta
Write-Host $playerWatch.prompt
Write-Host ""
Write-Host "##### MONEYLINE BOARD #####" -ForegroundColor Magenta
Write-Host $moneylineBoard.prompt
```

- [ ] **Step 3: Add both sections to the Word doc**

In `cmc-daily.ps1`, after the `foreach ($r in $results) { ... }` Word-building loop (the one that ends with the per-market prompt block) and BEFORE the `$doc.SaveAs2(...)` call, add:

```powershell
Add-Line ""
Add-Line ("PLAYER WATCH — top {0} HR chances" -f $playerWatch.count) $true
foreach ($line in ($playerWatch.prompt -split "`n")) { Add-Line $line }

Add-Line ""
Add-Line ("MONEYLINE BOARD — {0} games" -f $moneylineBoard.count) $true
foreach ($line in ($moneylineBoard.prompt -split "`n")) { Add-Line $line }
```

- [ ] **Step 4: Verify end-to-end (no spend)**

Run: `& "C:\Users\dokun\PycharmProjects\R.A.M.B.O\cmc-daily.ps1" -SkipPrep`
Expected: console shows the two new `#####` prompt blocks; `CMC_Daily_<date>.docx` is written with PLAYER WATCH + MONEYLINE BOARD sections. Confirm no errors and the doc opens.

- [ ] **Step 5: Commit**

```bash
git add cmc-daily.ps1
git commit -m "feat(cmc): add Player Watch + Moneyline Board to the daily script + doc"
```

---

## Self-Review

**Spec coverage:**
- §3 architecture (watch.py + endpoints + ps1) → Tasks 5,6,7,8 ✓
- §4 Player Watch rows + prompt + honest omissions → Task 5 ✓
- §5.2 game_datetime column + ordering → Task 1 ✓; §5.3 prompt → Task 6 ✓; §5.4 ml re-order → Task 3 ✓
- §6 ps1 integration → Task 8 ✓
- §8 tests: `test_watch_player` (T5), `test_watch_moneyline` (T2,T6), `test_ev_moneyline` ordering (T3), schedule-time (T1), API (T7) ✓
- §9 provenance/honesty → prompts carry stamp (T5,T6); optional fields omitted (T5) ✓

**Placeholder scan:** Task 7 Step 1 notes "match the existing fixture" — this is genuine (the worker must read `test_ev_api.py`'s setup), not a placeholder; concrete fallback (copy the app/TestClient setup) is given.

**Type consistency:** `evaluate_game` returns `home_support`/`away_support` (T2) consumed by `raw_picks` (T2) and `diff` consumed by `_mb_row` (T6). `Pick.game_datetime`/`game_pk` set in T2, read in T3 + T6. Row dict keys produced in T5/T6 match the line formatters. `_open(repo)` returns `(repo, conn)` used consistently. ✓
