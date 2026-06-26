# EV Brain (Home Runs) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the HR market of the EV Brain — read ingested MLB data via `MlbRepo`, compute each batter's `P(1+ HR)`, compare to the DK Pick6 multiplier, and return ranked +EV picks shaped for the CMC card.

**Architecture:** A market-pluggable module under `brains/ev/`. Pure math (`hr_model`, `parks`) is unit-tested in isolation; `features` assembles per-prop inputs from `MlbRepo`; `market.HRMarket` produces `Pick`s; `engine.daily_edge` ranks them and calls a per-slate LLM explainer; `api/betting.py` exposes them. v1 registers only the HR market.

**Tech Stack:** Python 3.x, SQLite (via existing `db/migrate.get_connection`), FastAPI, `anthropic` (explainer), pytest. Runs in `rambo-backend/`; local test venv at `rambo-backend/.venv`.

## Global Constraints
- Pick6 EV is multiplier-based: **`edge = P × multiplier − 1`**; +EV when `P > 1/multiplier`. Break-even = `1/multiplier`.
- v1 is **HR market only**, **line 0.5 (1+ HR) only**, **rank-only (no stake suggestions)**.
- `P(1+ HR) = 1 − (1 − rate)^expected_pa`, `expected_pa = 4.2`; `rate = min(hr_rate_per_pa × park_factor, 0.99)`.
- Output is **data-only** — no bet placement anywhere (Sentinel boundary by construction; import no betting tools).
- `Pick` field names must match the CMC card contract (see Task 3).
- All tests are **network-free**: seed SQLite directly; inject/mocked LLM. Run from `rambo-backend/` with `.venv/Scripts/python.exe -m pytest`.
- Headshot URL format: `https://img.mlbstatic.com/mlb-photos/image/upload/w_180,q_auto/v1/people/{mlb_id}/headshot/67/current`.

## File structure
```
brains/ev/
  __init__.py
  types.py        # Pick, HRFeatures dataclasses
  parks.py        # static HR park-factor table by team abbr
  hr_model.py     # pure: hr_probability(), edge(), breakeven()
  features.py     # build_hr_features(repo, date, prop) -> HRFeatures | None
  market.py       # HRMarket.raw_picks(repo, date) -> [Pick]; REGISTRY
  explainer.py    # explain(picks, market_key, complete=None) -> [Pick] (fills rationale)
  engine.py       # daily_edge(date, market='hr', repo=None, threshold=0.0) -> [Pick]
db/migrations/003_game_pitchers.sql   # probable pitchers + team abbrs on games
ingestion/normalize.py                 # map_scoreboard + _upsert_game tweak (Task 4)
repositories/mlb_repo.py               # + player_game_context(), pitcher_throws()
api/betting.py                         # GET /betting/daily-edge
main.py                                # mount betting router (guarded)
tests/test_ev_*.py
```

---

### Task 1: EV package + park factors

**Files:**
- Create: `brains/ev/__init__.py` (empty), `brains/ev/parks.py`
- Test: `tests/test_ev_parks.py`

**Interfaces:**
- Produces: `PARK_HR_FACTOR: dict[str,float]`, `hr_factor(team_abbr: str) -> float` (1.0 for unknown).

- [ ] **Step 1: Write the failing test**
```python
# tests/test_ev_parks.py
from brains.ev.parks import hr_factor, PARK_HR_FACTOR

def test_known_hitter_park_above_neutral():
    assert hr_factor("COL") > 1.0          # Coors

def test_unknown_defaults_neutral():
    assert hr_factor("ZZZ") == 1.0

def test_case_insensitive_and_table_size():
    assert hr_factor("col") == hr_factor("COL")
    assert len(PARK_HR_FACTOR) == 30
```

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/Scripts/python.exe -m pytest tests/test_ev_parks.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brains.ev.parks'`

- [ ] **Step 3: Write minimal implementation**
```python
# brains/ev/parks.py
from __future__ import annotations

# Approximate HR park factors (1.0 = neutral). Refine from Statcast park factors later.
PARK_HR_FACTOR: dict[str, float] = {
    "COL": 1.18, "CIN": 1.12, "NYY": 1.10, "PHI": 1.07, "BAL": 1.06,
    "MIL": 1.05, "BOS": 1.04, "ARI": 1.03, "ATL": 1.02, "HOU": 1.02,
    "TOR": 1.01, "CHC": 1.00, "LAD": 1.00, "MIN": 1.00, "TEX": 1.00,
    "WSH": 0.99, "STL": 0.98, "SD": 0.97, "NYM": 0.97, "CLE": 0.97,
    "CWS": 0.97, "TB": 0.96, "DET": 0.95, "KC": 0.95, "LAA": 0.95,
    "SEA": 0.93, "OAK": 0.92, "PIT": 0.92, "MIA": 0.90, "SF": 0.88,
}

def hr_factor(team_abbr: str) -> float:
    return PARK_HR_FACTOR.get((team_abbr or "").upper(), 1.0)
```

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv/Scripts/python.exe -m pytest tests/test_ev_parks.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**
```bash
git add brains/ev/__init__.py brains/ev/parks.py tests/test_ev_parks.py
git commit -m "feat(ev): HR park-factor table"
```

---

### Task 2: HR probability + edge math (pure)

**Files:**
- Create: `brains/ev/hr_model.py`
- Test: `tests/test_ev_hr_model.py`

**Interfaces:**
- Produces:
  - `hr_probability(hr_rate_per_pa: float, park_factor: float, expected_pa: float = 4.2) -> float`
  - `edge(p: float, multiplier: float) -> float`
  - `breakeven(multiplier: float) -> float`

- [ ] **Step 1: Write the failing test**
```python
# tests/test_ev_hr_model.py
import math
from brains.ev.hr_model import hr_probability, edge, breakeven

def test_probability_neutral_park():
    # 1 - (1-0.05)^4.2
    assert math.isclose(hr_probability(0.05, 1.0, 4.2), 1 - 0.95 ** 4.2, rel_tol=1e-9)

def test_park_boosts_rate():
    assert hr_probability(0.05, 1.2, 4.2) > hr_probability(0.05, 1.0, 4.2)

def test_rate_clamped():
    assert hr_probability(0.9, 2.0, 4.2) <= 1.0

def test_edge_and_breakeven():
    assert math.isclose(edge(0.40, 2.9), 0.40 * 2.9 - 1, rel_tol=1e-9)   # +0.16
    assert edge(0.30, 2.9) < 0
    assert math.isclose(breakeven(2.9), 1 / 2.9, rel_tol=1e-9)
```

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/Scripts/python.exe -m pytest tests/test_ev_hr_model.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**
```python
# brains/ev/hr_model.py
from __future__ import annotations

def hr_probability(hr_rate_per_pa: float, park_factor: float,
                   expected_pa: float = 4.2) -> float:
    rate = max(0.0, min(hr_rate_per_pa * park_factor, 0.99))
    return 1.0 - (1.0 - rate) ** expected_pa

def edge(p: float, multiplier: float) -> float:
    return p * multiplier - 1.0

def breakeven(multiplier: float) -> float:
    return 1.0 / multiplier if multiplier else 0.0
```

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv/Scripts/python.exe -m pytest tests/test_ev_hr_model.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**
```bash
git add brains/ev/hr_model.py tests/test_ev_hr_model.py
git commit -m "feat(ev): HR probability + Pick6 edge math"
```

---

### Task 3: Pick + HRFeatures types (card contract)

**Files:**
- Create: `brains/ev/types.py`
- Test: `tests/test_ev_types.py`

**Interfaces:**
- Produces: `Pick` and `HRFeatures` dataclasses (field names below are the card contract — do not rename).

- [ ] **Step 1: Write the failing test**
```python
# tests/test_ev_types.py
from dataclasses import asdict
from brains.ev.types import Pick, HRFeatures

def test_pick_constructible_and_serializable():
    p = Pick(market="hr", mlb_id=592450, name="AARON JUDGE", initials="AJ",
             team="NYY", opponent="BOS", hand="R", pick="1+ HOME RUN — OVER",
             line=0.5, multiplier=2.5, breakeven=0.4, model_p=0.46, edge=0.15,
             support="58 HR", tags=["EDGE"], glow="gold",
             headshot_url="https://img.mlbstatic.com/...", rationale="")
    d = asdict(p)
    assert d["edge"] == 0.15 and d["tags"] == ["EDGE"] and d["mlb_id"] == 592450

def test_features_constructible():
    f = HRFeatures(mlb_id=592450, name="Aaron Judge", team_abbr="NYY",
                   opponent_abbr="BOS", pitcher_hand="L", hr_rate=0.06,
                   park_factor=1.1, line=0.5, multiplier=2.5, season_hr=58)
    assert f.hr_rate == 0.06
```

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/Scripts/python.exe -m pytest tests/test_ev_types.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**
```python
# brains/ev/types.py
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class Pick:
    market: str            # "hr"
    mlb_id: int
    name: str              # display, upper-cased
    initials: str          # badge, e.g. "AJ"
    team: str              # abbr
    opponent: str          # abbr
    hand: str              # opposing pitcher hand ("L"/"R"/"")
    pick: str              # "1+ HOME RUN — OVER"
    line: float
    multiplier: float
    breakeven: float       # 1/multiplier
    model_p: float
    edge: float
    support: str           # e.g. "58 HR"
    tags: list[str]        # ["EDGE"]
    glow: str              # badge ring colour
    headshot_url: str
    rationale: str = ""

@dataclass
class HRFeatures:
    mlb_id: int
    name: str
    team_abbr: str
    opponent_abbr: str
    pitcher_hand: str
    hr_rate: float         # chosen per-PA rate (vs-hand or overall)
    park_factor: float
    line: float
    multiplier: float
    season_hr: int
```

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv/Scripts/python.exe -m pytest tests/test_ev_types.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**
```bash
git add brains/ev/types.py tests/test_ev_types.py
git commit -m "feat(ev): Pick + HRFeatures types (card contract)"
```

---

### Task 4: Migration 003 — probable pitchers + team abbrs on `games`

**Files:**
- Create: `db/migrations/003_game_pitchers.sql`
- Modify: `ingestion/normalize.py` (`map_scoreboard` dict + `_upsert_game`)
- Test: `tests/test_ev_migration003.py`

**Interfaces:**
- Produces: `games` gains `home_probable_pitcher_id`, `away_probable_pitcher_id`, `home_team_abbr`, `away_team_abbr`; `map_scoreboard` populates them.
- Consumes: `db.migrate.get_connection`/`apply_migrations`, `ingestion.raw_store.land_raw`, `ingestion.statsapi_client` shape.

- [ ] **Step 1: Write the failing test**
```python
# tests/test_ev_migration003.py
import json
from db.migrate import get_connection, apply_migrations
from ingestion.raw_store import land_raw
from ingestion.normalize import normalize_pending
from ingestion.apify_client_wrapper import RunResult

def _schedule_item():
    return {"gamePk": 999, "officialDate": "2026-06-26", "season": 2026,
            "teams": {
              "home": {"team": {"id": 147, "name": "New York Yankees", "abbreviation": "NYY"},
                       "probablePitcher": {"id": 111}},
              "away": {"team": {"id": 111, "name": "Boston Red Sox", "abbreviation": "BOS"},
                       "probablePitcher": {"id": 222}}}}

def test_games_gets_pitchers_and_abbrs(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    run = RunResult("mlb/statsapi:schedule", "r", "d", [_schedule_item()], 1, 0.0)
    land_raw(conn, run)
    normalize_pending(conn)
    g = conn.execute(
        "SELECT home_team_abbr, away_team_abbr, home_probable_pitcher_id, "
        "away_probable_pitcher_id FROM games WHERE game_pk=999").fetchone()
    assert g["home_team_abbr"] == "NYY"
    assert g["away_team_abbr"] == "BOS"
    assert g["home_probable_pitcher_id"] == 111
    assert g["away_probable_pitcher_id"] == 222
```

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/Scripts/python.exe -m pytest tests/test_ev_migration003.py -v`
Expected: FAIL (`no such column: home_team_abbr`)

- [ ] **Step 3a: Write the migration**
```sql
-- db/migrations/003_game_pitchers.sql
-- Probable pitchers + team abbreviations on games, for the EV Brain's
-- handedness split and park lookup. The schedule pull already hydrates these.
ALTER TABLE games ADD COLUMN home_probable_pitcher_id INTEGER;
ALTER TABLE games ADD COLUMN away_probable_pitcher_id INTEGER;
ALTER TABLE games ADD COLUMN home_team_abbr TEXT;
ALTER TABLE games ADD COLUMN away_team_abbr TEXT;
```

- [ ] **Step 3b: Extend `_upsert_game` in `ingestion/normalize.py`**
Replace the `_upsert_game` function with this (adds the 4 columns to INSERT + conflict update):
```python
def _upsert_game(conn: sqlite3.Connection, g: dict, scraped_at: str) -> None:
    conn.execute(
        """INSERT INTO games
             (game_pk, official_date, season, game_type, status_detail,
              home_team_id, home_team_name, away_team_id, away_team_name,
              home_score, away_score, venue_id, venue_name, day_night,
              double_header, scheduled_innings, url,
              home_probable_pitcher_id, away_probable_pitcher_id,
              home_team_abbr, away_team_abbr, scraped_at)
           VALUES (:game_pk,:official_date,:season,:game_type,:status_detail,
              :home_team_id,:home_team_name,:away_team_id,:away_team_name,
              :home_score,:away_score,:venue_id,:venue_name,:day_night,
              :double_header,:scheduled_innings,:url,
              :home_probable_pitcher_id,:away_probable_pitcher_id,
              :home_team_abbr,:away_team_abbr,:scraped_at)
           ON CONFLICT(game_pk) DO UPDATE SET
              status_detail=excluded.status_detail,
              home_score=excluded.home_score, away_score=excluded.away_score,
              home_probable_pitcher_id=excluded.home_probable_pitcher_id,
              away_probable_pitcher_id=excluded.away_probable_pitcher_id,
              home_team_abbr=excluded.home_team_abbr,
              away_team_abbr=excluded.away_team_abbr,
              scraped_at=excluded.scraped_at;""",
        {**g, "scraped_at": scraped_at},
    )
```

- [ ] **Step 3c: Extend the `g` dict in `map_scoreboard`** (add these four keys before the `_upsert_game(conn, g, scraped_at)` call):
```python
        "home_probable_pitcher_id": _as_int(_dig(item, "teams", "home", "probablePitcher", "id")),
        "away_probable_pitcher_id": _as_int(_dig(item, "teams", "away", "probablePitcher", "id")),
        "home_team_abbr": _dig(item, "teams", "home", "team", "abbreviation"),
        "away_team_abbr": _dig(item, "teams", "away", "team", "abbreviation"),
```

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv/Scripts/python.exe -m pytest tests/test_ev_migration003.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**
```bash
git add db/migrations/003_game_pitchers.sql ingestion/normalize.py tests/test_ev_migration003.py
git commit -m "feat(ev): migration 003 — probable pitchers + team abbrs on games"
```

---

### Task 5: Repo reads — game context + pitcher hand

**Files:**
- Modify: `repositories/mlb_repo.py` (add two methods)
- Test: `tests/test_ev_repo.py`

**Interfaces:**
- Produces (methods on `MlbRepo`):
  - `player_game_context(mlb_id: int, date: str) -> dict | None` → keys: `game_pk, is_home, team_abbr, opponent_abbr, home_abbr, opp_pitcher_id`
  - `pitcher_throws(mlb_id: int) -> str | None`
- Consumes: `games` columns from Task 4; `players.current_team_id`, `players.throws`.

- [ ] **Step 1: Write the failing test**
```python
# tests/test_ev_repo.py
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo

def _seed(conn):
    now = "2026-06-26T00:00:00Z"
    conn.execute("INSERT INTO players (mlb_id, full_name, throws, current_team_id, updated_at) "
                 "VALUES (592450,'Aaron Judge','R',147,?)", (now,))
    conn.execute("INSERT INTO players (mlb_id, full_name, throws, current_team_id, updated_at) "
                 "VALUES (222,'Lefty Pitcher','L',111,?)", (now,))
    conn.execute(
        "INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
        "home_team_abbr, away_team_abbr, home_probable_pitcher_id, away_probable_pitcher_id, "
        "scraped_at) VALUES (999,'2026-06-26',147,111,'NYY','BOS',111,222,?)", (now,))

def test_player_game_context_home_batter(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    _seed(conn)
    ctx = MlbRepo(conn).player_game_context(592450, "2026-06-26")
    assert ctx["game_pk"] == 999 and ctx["is_home"] is True
    assert ctx["team_abbr"] == "NYY" and ctx["opponent_abbr"] == "BOS"
    assert ctx["home_abbr"] == "NYY" and ctx["opp_pitcher_id"] == 222   # away pitcher

def test_pitcher_throws(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    _seed(conn)
    assert MlbRepo(conn).pitcher_throws(222) == "L"
    assert MlbRepo(conn).pitcher_throws(999999) is None
```

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/Scripts/python.exe -m pytest tests/test_ev_repo.py -v`
Expected: FAIL (`AttributeError: 'MlbRepo' object has no attribute 'player_game_context'`)

- [ ] **Step 3: Add the methods to `MlbRepo`** (in `repositories/mlb_repo.py`, before `# -- health / ops`)
```python
    # -- ev brain lookups ----------------------------------------------------

    def player_game_context(self, mlb_id: int, date: str) -> Optional[dict]:
        row = self.conn.execute(
            """SELECT g.game_pk, g.home_team_id, g.away_team_id,
                      g.home_team_abbr, g.away_team_abbr,
                      g.home_probable_pitcher_id, g.away_probable_pitcher_id,
                      p.current_team_id
               FROM games g JOIN players p ON p.mlb_id=?
               WHERE g.official_date=?
                 AND (g.home_team_id=p.current_team_id OR g.away_team_id=p.current_team_id)
               LIMIT 1""",
            (mlb_id, date)).fetchone()
        if row is None:
            return None
        is_home = row["home_team_id"] == row["current_team_id"]
        return {
            "game_pk": row["game_pk"],
            "is_home": is_home,
            "team_abbr": row["home_team_abbr"] if is_home else row["away_team_abbr"],
            "opponent_abbr": row["away_team_abbr"] if is_home else row["home_team_abbr"],
            "home_abbr": row["home_team_abbr"],
            "opp_pitcher_id": (row["away_probable_pitcher_id"] if is_home
                               else row["home_probable_pitcher_id"]),
        }

    def pitcher_throws(self, mlb_id: int) -> Optional[str]:
        row = self.conn.execute(
            "SELECT throws FROM players WHERE mlb_id=?", (mlb_id,)).fetchone()
        return row["throws"] if row else None
```

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv/Scripts/python.exe -m pytest tests/test_ev_repo.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**
```bash
git add repositories/mlb_repo.py tests/test_ev_repo.py
git commit -m "feat(ev): repo lookups for game context + pitcher hand"
```

---

### Task 6: Feature assembly

**Files:**
- Create: `brains/ev/features.py`
- Test: `tests/test_ev_features.py`

**Interfaces:**
- Consumes: `MlbRepo.player_season`, `MlbRepo.player_game_context`, `MlbRepo.pitcher_throws`; `brains.ev.parks.hr_factor`; `brains.ev.types.HRFeatures`.
- Produces: `build_hr_features(repo, date: str, prop: dict) -> HRFeatures | None` where `prop` has keys `mlb_id, player_name_raw, line, multiplier`.

- [ ] **Step 1: Write the failing test**
```python
# tests/test_ev_features.py
import json, math
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev.features import build_hr_features

def _seed(conn):
    now = "2026-06-26T00:00:00Z"
    conn.execute("INSERT INTO players (mlb_id, full_name, throws, current_team_id, updated_at) "
                 "VALUES (592450,'Aaron Judge','R',147,?)", (now,))
    conn.execute("INSERT INTO players (mlb_id, full_name, throws, current_team_id, updated_at) "
                 "VALUES (222,'Lefty','L',111,?)", (now,))
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
                 "home_team_abbr, away_team_abbr, home_probable_pitcher_id, away_probable_pitcher_id, "
                 "scraped_at) VALUES (999,'2026-06-26',147,111,'NYY','BOS',111,222,?)", (now,))
    stats = {"season": {"homeRuns": 50, "plateAppearances": 600},
             "splits": {"vr": {"homeRuns": 30, "plateAppearances": 450},
                        "vl": {"homeRuns": 20, "plateAppearances": 150}}}
    conn.execute("INSERT INTO player_season_stats (mlb_id, season, stat_group, stats, source, "
                 "as_of_date, scraped_at) VALUES (592450,2026,'hitting',?,'mlb','2026-06-26',?)",
                 (json.dumps(stats), now))

def test_features_use_vs_lefty_split_and_park(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    _seed(conn)
    prop = {"mlb_id": 592450, "player_name_raw": "Aaron Judge", "line": 0.5, "multiplier": 2.5}
    f = build_hr_features(MlbRepo(conn), "2026-06-26", prop)
    assert f is not None
    assert f.pitcher_hand == "L"                       # away probable pitcher throws L
    assert math.isclose(f.hr_rate, 20/150, rel_tol=1e-9)   # vs-LHP split
    assert f.park_factor == 1.10                       # NYY home park
    assert f.opponent_abbr == "BOS" and f.season_hr == 50

def test_features_none_without_stats(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    prop = {"mlb_id": 1, "player_name_raw": "Nobody", "line": 0.5, "multiplier": 2.0}
    assert build_hr_features(MlbRepo(conn), "2026-06-26", prop) is None
```

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/Scripts/python.exe -m pytest tests/test_ev_features.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**
```python
# brains/ev/features.py
from __future__ import annotations
import json
from typing import Optional
from brains.ev.parks import hr_factor
from brains.ev.types import HRFeatures

def _hr_rate(stat: Optional[dict]) -> Optional[float]:
    if not stat:
        return None
    try:
        hr = float(stat.get("homeRuns"))
        pa = float(stat.get("plateAppearances"))
    except (TypeError, ValueError):
        return None
    return hr / pa if pa > 0 else None

def build_hr_features(repo, date: str, prop: dict) -> Optional[HRFeatures]:
    mlb_id = prop["mlb_id"]
    season = int(date[:4])
    rows = repo.player_season(mlb_id, season, "hitting")
    if not rows:
        return None
    stats = json.loads(rows[0]["stats"])
    season_stat = stats.get("season") or {}
    overall = _hr_rate(season_stat)
    if overall is None:
        return None
    season_hr = int(season_stat.get("homeRuns") or 0)

    team_abbr = opp_abbr = ""
    park = 1.0
    hand = ""
    rate = overall
    ctx = repo.player_game_context(mlb_id, date)
    if ctx:
        team_abbr = ctx["team_abbr"] or ""
        opp_abbr = ctx["opponent_abbr"] or ""
        park = hr_factor(ctx["home_abbr"])
        if ctx["opp_pitcher_id"]:
            hand = repo.pitcher_throws(ctx["opp_pitcher_id"]) or ""
        splits = stats.get("splits") or {}
        if hand == "L":
            rate = _hr_rate(splits.get("vl")) or overall
        elif hand == "R":
            rate = _hr_rate(splits.get("vr")) or overall

    return HRFeatures(
        mlb_id=mlb_id, name=prop["player_name_raw"], team_abbr=team_abbr,
        opponent_abbr=opp_abbr, pitcher_hand=hand, hr_rate=rate,
        park_factor=park, line=prop["line"], multiplier=prop["multiplier"],
        season_hr=season_hr,
    )
```

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv/Scripts/python.exe -m pytest tests/test_ev_features.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**
```bash
git add brains/ev/features.py tests/test_ev_features.py
git commit -m "feat(ev): HR feature assembly from MlbRepo"
```

---

### Task 7: HR market — raw picks + registry

**Files:**
- Create: `brains/ev/market.py`
- Test: `tests/test_ev_market.py`

**Interfaces:**
- Consumes: `MlbRepo.latest_props`, `build_hr_features`, `hr_model.hr_probability/edge/breakeven`, `types.Pick`.
- Produces: `HRMarket` with `market_key="hr"` and `raw_picks(repo, date) -> list[Pick]` (edge computed, `rationale=""`); `REGISTRY: dict[str, object]` containing `"hr"`.

- [ ] **Step 1: Write the failing test**
```python
# tests/test_ev_market.py
import json
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev.market import HRMarket, REGISTRY

def _seed(conn):
    now = "2026-06-26T00:00:00Z"
    conn.execute("INSERT INTO players (mlb_id, full_name, throws, current_team_id, updated_at) "
                 "VALUES (592450,'Aaron Judge','R',147,?)", (now,))
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
                 "home_team_abbr, away_team_abbr, scraped_at) "
                 "VALUES (999,'2026-06-26',147,111,'NYY','BOS',?)", (now,))
    stats = {"season": {"homeRuns": 50, "plateAppearances": 600}, "splits": {}}
    conn.execute("INSERT INTO player_season_stats (mlb_id, season, stat_group, stats, source, "
                 "as_of_date, scraped_at) VALUES (592450,2026,'hitting',?,'mlb','2026-06-26',?)",
                 (json.dumps(stats), now))
    # a resolved 1+ HR Pick6 prop at 2.5x
    conn.execute("INSERT INTO prop_lines (game_pk, mlb_id, book, market, line, multiplier, "
                 "player_name_raw, captured_at) VALUES (NULL,592450,'dk_pick6','HR',0.5,2.5,"
                 "'Aaron Judge','2026-06-26T18:00Z')")

def test_hrmarket_builds_pick(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    _seed(conn)
    picks = HRMarket().raw_picks(MlbRepo(conn), "2026-06-26")
    assert len(picks) == 1
    pk = picks[0]
    assert pk.market == "hr" and pk.mlb_id == 592450
    assert pk.initials == "AJ" and pk.name == "AARON JUDGE"
    assert pk.pick == "1+ HOME RUN — OVER" and pk.multiplier == 2.5
    assert pk.support == "50 HR" and pk.tags == ["EDGE"]
    assert "/people/592450/headshot/" in pk.headshot_url
    # P(1+HR) at rate 50/600=0.0833, neutral park, 4.2 PA -> ~0.306; edge=0.306*2.5-1
    assert 0.20 < pk.model_p < 0.40
    assert abs(pk.edge - (pk.model_p * 2.5 - 1)) < 1e-9

def test_registry_has_hr():
    assert "hr" in REGISTRY and REGISTRY["hr"].market_key == "hr"
```

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/Scripts/python.exe -m pytest tests/test_ev_market.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**
```python
# brains/ev/market.py
from __future__ import annotations
from brains.ev.features import build_hr_features
from brains.ev.hr_model import hr_probability, edge, breakeven
from brains.ev.types import Pick

_HEADSHOT = ("https://img.mlbstatic.com/mlb-photos/image/upload/"
             "w_180,q_auto/v1/people/{mlb_id}/headshot/67/current")

def _initials(name: str) -> str:
    toks = name.replace("-", " ").split()
    return "".join(t[0] for t in toks if t and t[0].isalpha())[:3].upper()

class HRMarket:
    market_key = "hr"

    def raw_picks(self, repo, date: str) -> list[Pick]:
        props = [p for p in repo.latest_props(market="HR", resolved_only=True)
                 if p["line"] == 0.5]
        picks: list[Pick] = []
        for prop in props:
            feat = build_hr_features(repo, date, prop)
            if feat is None:
                continue
            p = hr_probability(feat.hr_rate, feat.park_factor)
            picks.append(Pick(
                market="hr", mlb_id=feat.mlb_id, name=feat.name.upper(),
                initials=_initials(feat.name), team=feat.team_abbr,
                opponent=feat.opponent_abbr, hand=feat.pitcher_hand,
                pick="1+ HOME RUN — OVER", line=feat.line,
                multiplier=feat.multiplier, breakeven=round(breakeven(feat.multiplier), 4),
                model_p=round(p, 4), edge=round(edge(p, feat.multiplier), 4),
                support=f"{feat.season_hr} HR", tags=["EDGE"], glow="gold",
                headshot_url=_HEADSHOT.format(mlb_id=feat.mlb_id), rationale="",
            ))
        return picks

REGISTRY: dict[str, object] = {"hr": HRMarket()}
```

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv/Scripts/python.exe -m pytest tests/test_ev_market.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**
```bash
git add brains/ev/market.py tests/test_ev_market.py
git commit -m "feat(ev): HR market builds ranked Pick candidates"
```

---

### Task 8: LLM explainer (per-slate, with fallback)

**Files:**
- Create: `brains/ev/explainer.py`
- Test: `tests/test_ev_explainer.py`

**Interfaces:**
- Consumes: `types.Pick`.
- Produces: `explain(picks: list[Pick], market_key: str, complete=None) -> list[Pick]`. `complete` is an injectable `(prompt: str) -> str` returning one rationale line per pick (newline-separated); defaults to a real Anthropic call. On any failure it fills a templated rationale. Mutates and returns the same list.
- Also: `_fallback(pick) -> str`.

- [ ] **Step 1: Write the failing test**
```python
# tests/test_ev_explainer.py
from brains.ev.types import Pick
from brains.ev.explainer import explain, _fallback

def _pick(name, edge):
    return Pick(market="hr", mlb_id=1, name=name, initials="X", team="NYY",
                opponent="BOS", hand="L", pick="1+ HOME RUN — OVER", line=0.5,
                multiplier=2.5, breakeven=0.4, model_p=0.46, edge=edge,
                support="50 HR", tags=["EDGE"], glow="gold", headshot_url="u")

def test_explain_fills_from_completion():
    picks = [_pick("A", 0.16), _pick("B", 0.10)]
    out = explain(picks, "hr", complete=lambda prompt: "first reason\nsecond reason")
    assert out[0].rationale == "first reason"
    assert out[1].rationale == "second reason"

def test_explain_fallback_on_error():
    picks = [_pick("A", 0.16)]
    def boom(prompt): raise RuntimeError("no api key")
    out = explain(picks, "hr", complete=boom)
    assert out[0].rationale == _fallback(picks[0])
    assert "%" in out[0].rationale  # templated, mentions the numbers

def test_explain_empty_is_noop():
    assert explain([], "hr", complete=lambda p: "") == []
```

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/Scripts/python.exe -m pytest tests/test_ev_explainer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**
```python
# brains/ev/explainer.py
from __future__ import annotations
import logging
from typing import Callable, Optional
from brains.ev.types import Pick

logger = logging.getLogger("rambo.ev.explainer")


def _fallback(pick: Pick) -> str:
    return (f"Model {pick.model_p:.0%} vs break-even {pick.breakeven:.0%} "
            f"({pick.edge:+.0%} edge) on {pick.pick.lower()}.")


def _prompt(picks: list[Pick], market_key: str) -> str:
    lines = [f"You are a sharp MLB betting analyst. For each {market_key.upper()} play, "
             "write ONE punchy sentence (max 18 words) on why it's +EV. "
             "Return exactly one line per play, in order, no numbering.\n"]
    for p in picks:
        lines.append(
            f"- {p.name} ({p.team} vs {p.opponent}, opp hand {p.hand or '?'}): "
            f"{p.pick} at {p.multiplier}x; model {p.model_p:.0%} vs break-even "
            f"{p.breakeven:.0%}; season {p.support}.")
    return "\n".join(lines)


def _anthropic_complete(prompt: str) -> str:
    import os
    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=400,
        messages=[{"role": "user", "content": prompt}])
    return resp.content[0].text


def explain(picks: list[Pick], market_key: str,
            complete: Optional[Callable[[str], str]] = None) -> list[Pick]:
    if not picks:
        return picks
    complete = complete or _anthropic_complete
    try:
        text = complete(_prompt(picks, market_key))
        lines = [ln.strip("-• ").strip() for ln in text.splitlines() if ln.strip()]
        if len(lines) < len(picks):
            raise ValueError("fewer rationales than picks")
        for pick, line in zip(picks, lines):
            pick.rationale = line
    except Exception as exc:
        logger.warning("explainer fell back to templates: %s", exc)
        for pick in picks:
            pick.rationale = _fallback(pick)
    return picks
```

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv/Scripts/python.exe -m pytest tests/test_ev_explainer.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**
```bash
git add brains/ev/explainer.py tests/test_ev_explainer.py
git commit -m "feat(ev): per-slate LLM explainer with templated fallback"
```

---

### Task 9: Engine — daily_edge orchestrator

**Files:**
- Create: `brains/ev/engine.py`
- Test: `tests/test_ev_engine.py`

**Interfaces:**
- Consumes: `market.REGISTRY`, `explainer.explain`, `MlbRepo`, `db.migrate.get_connection`.
- Produces: `daily_edge(date: str, market: str = "hr", repo=None, threshold: float = 0.0, complete=None) -> list[Pick]` — ranked by edge desc, only `edge > threshold`, rationales filled.

- [ ] **Step 1: Write the failing test**
```python
# tests/test_ev_engine.py
import json
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev.engine import daily_edge

def _seed(conn):
    now = "2026-06-26T00:00:00Z"
    # strong hitter (good edge) + weak hitter (negative edge, filtered out)
    for mlb_id, name, hr in [(1, "Big Bopper", 60), (2, "Weak Hitter", 5)]:
        conn.execute("INSERT INTO players (mlb_id, full_name, throws, current_team_id, updated_at)"
                     " VALUES (?,?,'R',147,?)", (mlb_id, name, now))
        stats = {"season": {"homeRuns": hr, "plateAppearances": 600}, "splits": {}}
        conn.execute("INSERT INTO player_season_stats (mlb_id, season, stat_group, stats, source,"
                     " as_of_date, scraped_at) VALUES (?,2026,'hitting',?,'mlb','2026-06-26',?)",
                     (mlb_id, json.dumps(stats), now))
        conn.execute("INSERT INTO prop_lines (game_pk, mlb_id, book, market, line, multiplier,"
                     " player_name_raw, captured_at) VALUES (NULL,?,'dk_pick6','HR',0.5,3.5,?,"
                     "'2026-06-26T18:00Z')", (mlb_id, name))
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_id, away_team_id,"
                 " home_team_abbr, away_team_abbr, scraped_at)"
                 " VALUES (999,'2026-06-26',147,111,'NYY','BOS',?)", (now,))

def test_daily_edge_ranks_and_filters(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    _seed(conn)
    picks = daily_edge("2026-06-26", "hr", repo=MlbRepo(conn),
                       complete=lambda prompt: "\n".join("reason" for _ in range(10)))
    # only the strong hitter clears edge>0 at 2.5x (break-even 40%)
    assert [p.name for p in picks] == ["BIG BOPPER"]
    assert picks[0].edge > 0 and picks[0].rationale == "reason"

def test_unknown_market_raises(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    import pytest
    with pytest.raises(KeyError):
        daily_edge("2026-06-26", "nope", repo=MlbRepo(conn))
```

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/Scripts/python.exe -m pytest tests/test_ev_engine.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**
```python
# brains/ev/engine.py
from __future__ import annotations
import os
from typing import Callable, Optional
from brains.ev.market import REGISTRY
from brains.ev.explainer import explain
from brains.ev.types import Pick

DB_PATH = os.environ.get("RAMBO_DB_PATH", "data/mlb_ingest.db")


def daily_edge(date: str, market: str = "hr", repo=None,
               threshold: float = 0.0,
               complete: Optional[Callable[[str], str]] = None) -> list[Pick]:
    model = REGISTRY[market]                      # KeyError on unknown market
    own_conn = None
    if repo is None:
        from db.migrate import get_connection
        from repositories.mlb_repo import MlbRepo
        own_conn = get_connection(DB_PATH)
        repo = MlbRepo(own_conn)
    try:
        picks = [pk for pk in model.raw_picks(repo, date) if pk.edge > threshold]
        picks.sort(key=lambda pk: pk.edge, reverse=True)
        explain(picks, market, complete=complete)
        return picks
    finally:
        if own_conn is not None:
            own_conn.close()
```

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv/Scripts/python.exe -m pytest tests/test_ev_engine.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**
```bash
git add brains/ev/engine.py tests/test_ev_engine.py
git commit -m "feat(ev): daily_edge orchestrator (rank + explain)"
```

---

### Task 10: API endpoint + mount

**Files:**
- Create: `api/betting.py`
- Modify: `main.py` (guarded include, next to the ingest router)
- Test: `tests/test_ev_api.py`

**Interfaces:**
- Consumes: `brains.ev.engine.daily_edge`, `brains.ev.market.REGISTRY`.
- Produces: `GET /betting/daily-edge?market=hr&date=YYYY-MM-DD` → `{market, date, count, picks: [...]}`. `router` mounted on `app`.

- [ ] **Step 1: Write the failing test**
```python
# tests/test_ev_api.py
from fastapi import FastAPI
from fastapi.testclient import TestClient
from brains.ev import engine as engine_mod
from brains.ev.types import Pick
import api.betting as betting

def _pick():
    return Pick(market="hr", mlb_id=1, name="BIG BOPPER", initials="BB", team="NYY",
                opponent="BOS", hand="R", pick="1+ HOME RUN — OVER", line=0.5,
                multiplier=2.5, breakeven=0.4, model_p=0.46, edge=0.15, support="60 HR",
                tags=["EDGE"], glow="gold", headshot_url="u", rationale="mash")

def _client(monkeypatch):
    monkeypatch.setattr(betting, "daily_edge", lambda date, market: [_pick()])
    app = FastAPI(); app.include_router(betting.router)
    return TestClient(app)

def test_daily_edge_endpoint(monkeypatch):
    c = _client(monkeypatch)
    r = c.get("/betting/daily-edge?market=hr&date=2026-06-26")
    assert r.status_code == 200
    body = r.json()
    assert body["market"] == "hr" and body["count"] == 1
    assert body["picks"][0]["name"] == "BIG BOPPER" and body["picks"][0]["edge"] == 0.15

def test_unknown_market_404(monkeypatch):
    c = _client(monkeypatch)
    assert c.get("/betting/daily-edge?market=nope").status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/Scripts/python.exe -m pytest tests/test_ev_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.betting'`

- [ ] **Step 3a: Write the router**
```python
# api/betting.py
"""
EV Brain read API (data-only). GET /betting/daily-edge?market=hr&date=YYYY-MM-DD
returns the ranked +EV picks for one market — the JSON the CMC card fetches.
Imports no bet-placement capability (Sentinel boundary by construction).
"""
from __future__ import annotations
import datetime
from dataclasses import asdict
from typing import Optional
from fastapi import APIRouter, HTTPException
from brains.ev.engine import daily_edge
from brains.ev.market import REGISTRY

router = APIRouter(prefix="/betting", tags=["betting"])


@router.get("/daily-edge")
def get_daily_edge(market: str = "hr", date: Optional[str] = None) -> dict:
    if market not in REGISTRY:
        raise HTTPException(status_code=404,
                            detail=f"unknown market '{market}' (valid: {sorted(REGISTRY)})")
    d = date or datetime.date.today().isoformat()
    try:
        picks = daily_edge(d, market)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"daily_edge failed: {e}") from e
    return {"market": market, "date": d, "count": len(picks),
            "picks": [asdict(p) for p in picks]}
```

- [ ] **Step 3b: Mount in `main.py`** (immediately after the guarded ingest-router block added earlier):
```python
try:
    from api.betting import router as _betting_router
    app.include_router(_betting_router)
except Exception as _betting_err:  # pragma: no cover
    print(f"[rambo] betting router not mounted: {_betting_err}")
```

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv/Scripts/python.exe -m pytest tests/test_ev_api.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the whole EV suite + commit**
Run: `.venv/Scripts/python.exe -m pytest tests/test_ev_*.py -q`
Expected: PASS (all green)
```bash
git add api/betting.py main.py tests/test_ev_api.py
git commit -m "feat(ev): /betting/daily-edge endpoint + mount"
```

---

## Post-implementation manual verification (with real data)
1. Pull a slate: `.venv/Scripts/python.exe -m ingestion.cli pull --source schedule --date <today>`, then `roster`, then `props` (Pick6).
2. Re-normalize schedule so migration-003 columns fill: `.venv/Scripts/python.exe -m ingestion.cli renormalize --actor mlb/statsapi:schedule` then `normalize`.
3. `.venv/Scripts/python.exe -c "from db.migrate import get_connection; from repositories.mlb_repo import MlbRepo; from brains.ev.engine import daily_edge; [print(p.name, p.pick, p.multiplier, round(p.model_p,3), round(p.edge,3)) for p in daily_edge('<today>','hr', repo=MlbRepo(get_connection('data/mlb_ingest.db')))]"`
4. Confirm plausible HR picks ranked by edge; spot-check one player's season HR vs Baseball Savant.

## Self-review notes
- **Spec coverage:** multiplier-EV (Task 2), HR model + park + hand (Tasks 1/2/6), migration-003 data gap (Task 4), repo reads (Task 5), market-pluggable `REGISTRY` (Task 7), per-slate explainer + fallback (Task 8), rank-only engine (Task 9), `/betting/daily-edge` (Task 10), card-aligned `Pick` (Task 3). Sentinel boundary: no betting imports anywhere.
- **Out of scope (per spec):** H+R+RBI/SB/Strikeouts/moneyline models, the card frontend rebuild, pitcher-HR-allowed/weather/Statcast, calibration tracking, bet placement.
- **Known v1 simplification:** line 0.5 (1+ HR) only; props whose game/pitcher can't be resolved fall back to the overall HR rate (no hand split) but still rank.
