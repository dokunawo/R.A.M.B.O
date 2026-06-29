# PrizePicks Boards + Power/Flex Parlay EV Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dead DK Pick6 feed with a direct PrizePicks public-API ingestion, surface 6 model-confidence player-prop boards (HR/SO/TB/H/HRR/SB), and add a Power/Flex entry-EV parlay builder.

**Architecture:** A pure-stdlib httpx client pulls PrizePicks' free JSON:API → normalizes into the existing `prop_lines` table (no per-prop multiplier) → boards reuse RAMBO's existing prop models to rank legs by model P(clear the line) → a Poisson-binomial parlay module evaluates Power/Flex entry EV.

**Tech Stack:** Python 3 (stdlib + httpx, already a dep), SQLite, FastAPI, pytest.

## Global Constraints

- **No new dependencies** (httpx already used). Pure-stdlib math for the parlay.
- Source is the **direct PrizePicks public API** (`https://api.prizepicks.com`), NOT the Apify actor. `league_id=2` = MLB.
- Markets (standard `odds_type` only): `Home Runs→HR`, `Pitcher Strikeouts→SO`, `Total Bases→TB`, `Hits→H`, `Hits+Runs+RBIs→H+R+RBI`, `Stolen Bases→SB`.
- `book="prizepicks"`; PrizePicks props have `multiplier=NULL` (payouts are play-level).
- Board ranking = model **P(clear the PrizePicks line)**, model-favored side (over if `p_over≥0.5` else under).
- Power table `{2:3.0,3:5.0,4:10.0,5:20.0,6:37.5}`; Flex `{3:{3:2.25,2:1.25},4:{4:5.0,3:1.5},5:{5:10.0,4:2.0,3:0.4},6:{6:25.0,5:2.0,4:0.4}}`.
- Tests run from `rambo-backend/` with `./.venv/Scripts/python.exe -m pytest` (fall back to `python`).
- Commit messages use Bash heredoc; co-author `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Branch: `feat/prizepicks-boards` (already created).
- `_insert_prop(conn, dict)` (in `ingestion/normalize.py`) is the shared prop insert; the `DISPATCH` dict (≈line 567) maps a raw-ingest source/actor id → its normalizer.
- prop_lines columns: `game_pk, mlb_id, book, market, line, over_price, under_price, multiplier, player_name_raw, captured_at`.

---

### Task 1: Config — markets + Power/Flex tables

**Files:**
- Create: `config/prizepicks.py`
- Test: `tests/test_prizepicks_config.py`

**Interfaces:**
- Produces: `BASE="https://api.prizepicks.com"`, `LEAGUE_ID=2`, `SOURCE_ID="prizepicks"`, `STAT_MARKET_MAP: dict[str,str]`, `POWER: dict[int,float]`, `FLEX: dict[int,dict[int,float]]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prizepicks_config.py
from config import prizepicks as pp


def test_stat_market_map_covers_six_markets():
    assert pp.STAT_MARKET_MAP == {
        "Home Runs": "HR", "Pitcher Strikeouts": "SO", "Total Bases": "TB",
        "Hits": "H", "Hits+Runs+RBIs": "H+R+RBI", "Stolen Bases": "SB",
    }
    assert pp.LEAGUE_ID == 2 and pp.SOURCE_ID == "prizepicks"


def test_payout_tables():
    assert pp.POWER[2] == 3.0 and pp.POWER[6] == 37.5
    # Flex partial tables are keyed by leg-count then by hits
    assert pp.FLEX[3][3] == 2.25 and pp.FLEX[3][2] == 1.25
    assert set(pp.FLEX.keys()) == {3, 4, 5, 6}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'config.prizepicks'`

- [ ] **Step 3: Write minimal implementation**

```python
# config/prizepicks.py
"""PrizePicks ingestion config — direct public API (free), MLB only. Power/Flex
payout tables are PrizePicks' published standard values; verify against current
payouts (they can vary by region/promo)."""
from __future__ import annotations

BASE = "https://api.prizepicks.com"
LEAGUE_ID = 2            # MLB
SOURCE_ID = "prizepicks"

# PrizePicks stat_type -> RAMBO market key. Only these (standard tier) are kept.
STAT_MARKET_MAP = {
    "Home Runs": "HR",
    "Pitcher Strikeouts": "SO",
    "Total Bases": "TB",
    "Hits": "H",
    "Hits+Runs+RBIs": "H+R+RBI",
    "Stolen Bases": "SB",
}

# Power Play: all N legs must hit -> fixed multiplier.
POWER = {2: 3.0, 3: 5.0, 4: 10.0, 5: 20.0, 6: 37.5}

# Flex Play: partial payouts. FLEX[n_legs][n_hits] = multiplier (missing key = 0).
FLEX = {
    3: {3: 2.25, 2: 1.25},
    4: {4: 5.0, 3: 1.5},
    5: {5: 10.0, 4: 2.0, 3: 0.4},
    6: {6: 25.0, 5: 2.0, 4: 0.4},
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/config/prizepicks.py rambo-backend/tests/test_prizepicks_config.py
git commit -m "$(cat <<'EOF'
feat(betting): PrizePicks config — market map + Power/Flex tables

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: PrizePicks API client (JSON:API join)

**Files:**
- Create: `ingestion/prizepicks_client.py`
- Test: `tests/test_prizepicks_client.py`

**Interfaces:**
- Consumes: `config.prizepicks` (BASE, LEAGUE_ID, SOURCE_ID); `ingestion.apify_client_wrapper.RunResult`.
- Produces: `fetch_mlb_props(*, client=None) -> RunResult` whose `items` are flat dicts: `{projection_id, player_name, team, position, stat_type, line, odds_type, start_time, game_id}`. `actor_id == "prizepicks"`, `estimated_cost_usd == 0.0`. Never raises.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prizepicks_client.py
from ingestion import prizepicks_client as pc


class _Resp:
    def __init__(self, payload): self._p = payload; self.status_code = 200
    def raise_for_status(self): pass
    def json(self): return self._p


class _Client:
    def __init__(self, payload): self._p = payload; self.calls = []
    def get(self, url, params=None, headers=None):
        self.calls.append((url, params)); return _Resp(self._p)
    def close(self): pass


def _payload():
    return {
        "data": [
            {"id": "p1", "type": "projection",
             "attributes": {"line_score": 0.5, "stat_type": "Home Runs",
                            "odds_type": "standard", "start_time": "2026-06-29T19:00:00-04:00",
                            "game_id": "g9"},
             "relationships": {"new_player": {"data": {"type": "new_player", "id": "np1"}}}},
        ],
        "included": [
            {"id": "np1", "type": "new_player",
             "attributes": {"name": "Aaron Judge", "team": "NYY", "position": "OF"}},
        ],
        "links": {},
    }


def test_fetch_joins_player_and_flattens():
    run = pc.fetch_mlb_props(client=_Client(_payload()))
    assert run.actor_id == "prizepicks" and run.estimated_cost_usd == 0.0
    assert run.item_count == 1
    it = run.items[0]
    assert it["player_name"] == "Aaron Judge" and it["team"] == "NYY"
    assert it["stat_type"] == "Home Runs" and it["line"] == 0.5
    assert it["odds_type"] == "standard" and it["projection_id"] == "p1"


def test_fetch_never_raises_on_bad_payload():
    run = pc.fetch_mlb_props(client=_Client({"nonsense": True}))
    assert run.item_count == 0 and run.actor_id == "prizepicks"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingestion.prizepicks_client'`

- [ ] **Step 3: Write minimal implementation**

```python
# ingestion/prizepicks_client.py
"""Direct PrizePicks public-API client (free, no auth). Pulls MLB projections,
joins each to its new_player from the JSON:API `included`, and emits flat per-prop
items. Never raises — returns 0 items on any error so prep can warn and move on."""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from config import prizepicks as cfg
from ingestion.apify_client_wrapper import RunResult

logger = logging.getLogger("rambo.ingestion.prizepicks")

_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_MAX_PAGES = 10


def fetch_mlb_props(*, client: Optional[httpx.Client] = None) -> RunResult:
    own = client is None
    client = client or httpx.Client(timeout=30)
    items: list[dict] = []
    try:
        url = f"{cfg.BASE}/projections"
        params = {"league_id": cfg.LEAGUE_ID, "per_page": 1000}
        for _ in range(_MAX_PAGES):
            resp = client.get(url, params=params, headers=_HEADERS)
            resp.raise_for_status()
            body = resp.json() or {}
            data = body.get("data") or []
            players = {x["id"]: (x.get("attributes") or {})
                       for x in (body.get("included") or [])
                       if x.get("type") == "new_player"}
            for proj in data:
                attrs = proj.get("attributes") or {}
                rel = (((proj.get("relationships") or {}).get("new_player") or {}).get("data") or {})
                pl = players.get(rel.get("id"), {})
                items.append({
                    "projection_id": proj.get("id"),
                    "player_name": pl.get("name") or pl.get("display_name"),
                    "team": pl.get("team"),
                    "position": pl.get("position"),
                    "stat_type": attrs.get("stat_type"),
                    "line": attrs.get("line_score"),
                    "odds_type": attrs.get("odds_type"),
                    "start_time": attrs.get("start_time"),
                    "game_id": attrs.get("game_id"),
                })
            nxt = ((body.get("links") or {}).get("next"))
            if not nxt:
                break
            url, params = (nxt if nxt.startswith("http") else f"{cfg.BASE}{nxt}"), None
        logger.info("prizepicks: %d projections", len(items))
    except Exception:
        logger.exception("prizepicks fetch failed")
        items = []
    finally:
        if own:
            client.close()
    rid = f"{cfg.SOURCE_ID}:mlb"
    return RunResult(actor_id=cfg.SOURCE_ID, run_id=rid, dataset_id=rid,
                     items=items, item_count=len(items), estimated_cost_usd=0.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_client.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/ingestion/prizepicks_client.py rambo-backend/tests/test_prizepicks_client.py
git commit -m "$(cat <<'EOF'
feat(betting): direct PrizePicks API client (JSON:API join, free)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Source route + normalizer

**Files:**
- Modify: `ingestion/sources.py` (route `"prizepicks"`)
- Modify: `ingestion/normalize.py` (`map_prizepicks` + DISPATCH)
- Test: `tests/test_prizepicks_normalize.py`

**Interfaces:**
- Consumes: `prizepicks_client.fetch_mlb_props` (Task 2); `config.prizepicks.STAT_MARKET_MAP`; `normalize._insert_prop`.
- Produces: `sources.pull_source(conn, "prizepicks")` lands raw; `normalize.map_prizepicks(conn, item, scraped_at)` writes a `prop_lines` row for mapped+standard items only.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prizepicks_normalize.py
from db.migrate import get_connection, apply_migrations
from ingestion.normalize import map_prizepicks


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _item(stat="Home Runs", odds="standard", line=0.5, name="Aaron Judge"):
    return {"projection_id": "p1", "player_name": name, "team": "NYY",
            "position": "OF", "stat_type": stat, "line": line, "odds_type": odds,
            "start_time": "2026-06-29T19:00:00-04:00", "game_id": "g9"}


def test_mapped_standard_prop_lands(tmp_path):
    conn = _conn(tmp_path)
    assert map_prizepicks(conn, _item(), "2026-06-29T18:00:00Z") is True
    row = conn.execute("SELECT book, market, line, multiplier, player_name_raw "
                       "FROM prop_lines").fetchone()
    assert row["book"] == "prizepicks" and row["market"] == "HR"
    assert row["line"] == 0.5 and row["multiplier"] is None
    assert row["player_name_raw"] == "Aaron Judge"


def test_unmapped_stat_or_alt_tier_skipped(tmp_path):
    conn = _conn(tmp_path)
    map_prizepicks(conn, _item(stat="Pitches Thrown"), "2026-06-29T18:00:00Z")
    map_prizepicks(conn, _item(odds="demon"), "2026-06-29T18:00:00Z")
    assert conn.execute("SELECT COUNT(*) FROM prop_lines").fetchone()[0] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_normalize.py -v`
Expected: FAIL — `ImportError: cannot import name 'map_prizepicks'`

- [ ] **Step 3: Write minimal implementation**

Add to `ingestion/normalize.py` (near `map_props`), and import the map at the top of the file (`from config.prizepicks import STAT_MARKET_MAP, SOURCE_ID as PRIZEPICKS_SOURCE`):

```python
def map_prizepicks(conn, item, scraped_at) -> bool:
    """PrizePicks projection -> prop_lines. Keeps only the 6 mapped stat_types on
    the STANDARD odds tier; multiplier is NULL (payouts are play-level). mlb_id +
    game_pk are resolved downstream by the IdResolver / prep."""
    if (item.get("odds_type") != "standard"
            or item.get("stat_type") not in STAT_MARKET_MAP):
        return True  # handled: not a board market / not standard tier
    line = _as_float(item.get("line"))
    player = item.get("player_name")
    if line is None or not player:
        return False
    _insert_prop(conn, {
        "game_pk": None, "mlb_id": None, "book": "prizepicks",
        "market": STAT_MARKET_MAP[item["stat_type"]], "line": line,
        "over_price": None, "under_price": None, "multiplier": None,
        "player_name_raw": player,
        "captured_at": item.get("start_time") or scraped_at,
    })
    return True
```

Add to the `DISPATCH` dict (≈line 567): `PRIZEPICKS_SOURCE: map_prizepicks,`

Add to `ingestion/sources.py` — extend `OTHER_SOURCES` with `"prizepicks"` and add a branch in `pull_source`:

```python
    elif source == "prizepicks":
        from ingestion import prizepicks_client as pp
        run = pp.fetch_mlb_props()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_normalize.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/ingestion/sources.py rambo-backend/ingestion/normalize.py rambo-backend/tests/test_prizepicks_normalize.py
git commit -m "$(cat <<'EOF'
feat(betting): PrizePicks source route + normalizer (standard tier, 6 markets)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Power/Flex parlay EV (pure math)

**Files:**
- Create: `brains/ev/prizepicks_parlay.py`
- Test: `tests/test_prizepicks_parlay.py`

**Interfaces:**
- Consumes: `config.prizepicks.POWER`, `config.prizepicks.FLEX`.
- Produces:
  - `hit_distribution(probs: list[float]) -> list[float]` — `P(exactly k hits)` for k=0..N (Poisson-binomial, independent legs).
  - `entry_ev(probs: list[float], play_type: str) -> dict` → `{"combined_all": float, "ev": float}` where `play_type in {"power","flex"}`; EV is per 1 unit stake = `Σ P(k)·payout(k) − 1`.
  - `suggest_entries(legs: list[dict], sizes=(2,3,4,5,6)) -> list[dict]` — each leg `{name, p, ...}`; returns best entry per (size, play_type) sorted by ev desc: `{size, play_type, legs, combined_all, ev}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prizepicks_parlay.py
import math
from brains.ev.prizepicks_parlay import hit_distribution, entry_ev, suggest_entries


def test_hit_distribution_sums_to_one_and_known():
    d = hit_distribution([0.5, 0.5])
    assert math.isclose(sum(d), 1.0, rel_tol=1e-9)
    assert math.isclose(d[0], 0.25) and math.isclose(d[1], 0.5) and math.isclose(d[2], 0.25)


def test_power_ev_pays_only_on_all_hit():
    # 2-pick power pays 3x only if both hit (P=0.25): EV = 0.25*3 - 1 = -0.25
    res = entry_ev([0.5, 0.5], "power")
    assert math.isclose(res["combined_all"], 0.25, rel_tol=1e-9)
    assert math.isclose(res["ev"], 0.25 * 3.0 - 1.0, rel_tol=1e-9)


def test_flex_ev_uses_partial_table():
    # 3-pick flex, all p=0.8. P(3)=0.512, P(2)=3*0.8^2*0.2=0.384
    # EV = 0.512*2.25 + 0.384*1.25 - 1
    res = entry_ev([0.8, 0.8, 0.8], "flex")
    expected = 0.8**3 * 2.25 + (3 * 0.8**2 * 0.2) * 1.25 - 1.0
    assert math.isclose(res["ev"], expected, rel_tol=1e-9)


def test_suggest_returns_best_first():
    legs = [{"name": f"P{i}", "p": p} for i, p in enumerate([0.9, 0.85, 0.6, 0.55])]
    out = suggest_entries(legs, sizes=(2, 3))
    assert out and all("ev" in e for e in out)
    assert out[0]["ev"] >= out[-1]["ev"]            # sorted desc
    assert out[0]["size"] in (2, 3) and out[0]["play_type"] in ("power", "flex")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_parlay.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brains.ev.prizepicks_parlay'`

- [ ] **Step 3: Write minimal implementation**

```python
# brains/ev/prizepicks_parlay.py
"""PrizePicks entry EV. Each leg has a model probability `p` (the favored side).
hit_distribution is the Poisson-binomial P(exactly k of N hit); entry_ev applies
the Power/Flex payout tables. Pure Python."""
from __future__ import annotations

from itertools import combinations

from config.prizepicks import POWER, FLEX


def hit_distribution(probs: list[float]) -> list[float]:
    """P(exactly k hits) for k=0..len(probs), independent legs (DP)."""
    dist = [1.0]
    for p in probs:
        p = min(1.0, max(0.0, p))
        nxt = [0.0] * (len(dist) + 1)
        for k, val in enumerate(dist):
            nxt[k] += val * (1.0 - p)      # leg misses
            nxt[k + 1] += val * p          # leg hits
        dist = nxt
    return dist


def entry_ev(probs: list[float], play_type: str) -> dict:
    """EV per 1 unit stake = sum_k P(k) * payout(k) - 1."""
    n = len(probs)
    dist = hit_distribution(probs)
    if play_type == "power":
        payout = {n: POWER.get(n, 0.0)}            # pays only when all hit
    elif play_type == "flex":
        payout = FLEX.get(n, {})
    else:
        raise ValueError(f"unknown play_type {play_type!r}")
    ev = sum(dist[k] * payout.get(k, 0.0) for k in range(n + 1)) - 1.0
    return {"combined_all": dist[n], "ev": round(ev, 4)}


def suggest_entries(legs: list[dict], sizes=(2, 3, 4, 5, 6)) -> list[dict]:
    """From the highest-p legs, evaluate Power and Flex at each size; return the
    best entry per (size, play_type), sorted by EV desc."""
    ranked = sorted(legs, key=lambda l: l.get("p", 0.0), reverse=True)
    out: list[dict] = []
    for size in sizes:
        if size > len(ranked):
            continue
        chosen = ranked[:size]
        probs = [l.get("p", 0.0) for l in chosen]
        for play_type in ("power", "flex"):
            if play_type == "flex" and size not in FLEX:
                continue
            res = entry_ev(probs, play_type)
            out.append({"size": size, "play_type": play_type,
                        "legs": [l.get("name") for l in chosen],
                        "combined_all": round(res["combined_all"], 4),
                        "ev": res["ev"]})
    out.sort(key=lambda e: e["ev"], reverse=True)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_parlay.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/brains/ev/prizepicks_parlay.py rambo-backend/tests/test_prizepicks_parlay.py
git commit -m "$(cat <<'EOF'
feat(betting): Power/Flex parlay EV (Poisson-binomial)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Probability boards

**Files:**
- Create: `brains/ev/prizepicks_board.py`
- Test: `tests/test_prizepicks_board.py`

**Interfaces:**
- Consumes: `MlbRepo.latest_props`, `MlbRepo.player_game_context`; `features.build_hr_features_core` / `build_count_features_core`; `hr_model.hr_probability`; `count_model.poisson_prob_over`; `k_model.k_projection` + `binom_prob_over`.
- Produces: `prizepicks_board(date, market, repo=None, *, count=11) -> dict` → `{title, product:"PrizePicks", market, count, rows, prompt}`. `market in {"HR","SO","TB","H","H+R+RBI","SB"}`. Each row: `{rank, name, team, opponent, stat, line, side, model_pct, support}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prizepicks_board.py
import json
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev.prizepicks_board import prizepicks_board


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _seed_hr(conn, mlb_id=592450, team=147):
    now = "2026-06-29T00:00:00Z"
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_id, away_team_id,"
                 " home_team_abbr, away_team_abbr, scraped_at) "
                 "VALUES (900,'2026-06-29',?,111,'NYY','BOS',?)", (team, now))
    conn.execute("INSERT INTO players (mlb_id, full_name, bats, current_team_id, updated_at) "
                 "VALUES (?,?,'R',?,?)", (mlb_id, "Aaron Judge", team, now))
    stats = {"season": {"homeRuns": 50, "plateAppearances": 600}, "splits": {}}
    conn.execute("INSERT INTO player_season_stats (mlb_id, season, stat_group, stats, source,"
                 " as_of_date, scraped_at) VALUES (?,2026,'hitting',?,'mlb','2026-06-29',?)",
                 (mlb_id, json.dumps(stats), now))
    conn.execute("INSERT INTO prop_lines (game_pk, mlb_id, book, market, line, multiplier,"
                 " player_name_raw, captured_at) VALUES (900,?,'prizepicks','HR',0.5,NULL,"
                 "'Aaron Judge','2026-06-29T18:00:00Z')", (mlb_id,))


def test_hr_board_ranks_by_model_prob(tmp_path):
    conn = _conn(tmp_path)
    _seed_hr(conn)
    board = prizepicks_board("2026-06-29", "HR", repo=MlbRepo(conn))
    assert board["product"] == "PrizePicks"
    assert board["count"] == 1
    r = board["rows"][0]
    assert r["name"] == "AARON JUDGE" and r["stat"] == "HR" and r["line"] == 0.5
    assert r["side"] in ("over", "under")
    assert 0 <= r["model_pct"] <= 100


def test_board_skips_player_not_on_slate(tmp_path):
    conn = _conn(tmp_path)
    _seed_hr(conn)
    # ask for a different date with no game for this player
    assert prizepicks_board("2026-06-30", "HR", repo=MlbRepo(conn))["count"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_board.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brains.ev.prizepicks_board'`

- [ ] **Step 3: Write minimal implementation**

```python
# brains/ev/prizepicks_board.py
"""PrizePicks model-confidence boards. Per market, score each PrizePicks prop by
the model's probability of clearing the line (reusing RAMBO's existing prop
models), pick the favored side, and rank by confidence. No per-prop multiplier."""
from __future__ import annotations

import os

from brains.ev.features import build_hr_features_core, build_count_features_core
from brains.ev.hr_model import hr_probability
from brains.ev.count_model import poisson_prob_over
from brains.ev import k_model

DB_PATH = os.environ.get("RAMBO_DB_PATH", "data/mlb_ingest.db")
BOARD_SIZE = 11

# market -> (stat label, count-model stat_keys / None for HR & SO which use their own model)
_COUNT_KEYS = {
    "TB": ["totalBases"], "H": ["hits"],
    "H+R+RBI": ["hits", "runs", "rbi"], "SB": ["stolenBases"],
}


def _open(repo):
    if repo is not None:
        return repo, None
    from db.migrate import get_connection
    from repositories.mlb_repo import MlbRepo
    conn = get_connection(DB_PATH)
    return MlbRepo(conn), conn


def _p_over(repo, date, market, prop) -> tuple[float, str] | None:
    """model P(over the line) + a support string, or None if no usable sample."""
    mid, line = prop["mlb_id"], prop["line"]
    name = prop["player_name_raw"] or ""
    if market == "HR":
        feat = build_hr_features_core(repo, date, mid, name, line=line)
        if feat is None:
            return None
        return hr_probability(feat.hr_rate, feat.park_factor), feat.support
    if market == "SO":
        ctx = repo.player_game_context(mid, date) or {}
        proj = k_model.k_projection(repo, date, {
            "mlb_id": mid, "name": name, "team_abbr": ctx.get("team_abbr", ""),
            "opponent_abbr": ctx.get("opponent_abbr", ""),
            "opponent_team_id": None}, max_j=20)
        if proj is None:
            return None
        from math import ceil
        return (k_model.binom_prob_over(round(proj["batters_faced"]), proj["k_rate"],
                                        ceil(line + 1e-9)),
                f"{proj['k_mean']:.1f} proj K")
    keys = _COUNT_KEYS.get(market)
    if not keys:
        return None
    feat = build_count_features_core(repo, date, mid, name, stat_keys=keys,
                                     label=market, group="hitting")
    if feat is None:
        return None
    return poisson_prob_over(feat.per_game_mean, line), feat.support


def prizepicks_board(date: str, market: str, repo=None, *, count: int = BOARD_SIZE) -> dict:
    repo, conn = _open(repo)
    try:
        scored = []
        for prop in repo.latest_props(market=market, official_date=date):
            if prop["book"] != "prizepicks" or prop["mlb_id"] is None:
                continue
            ctx = repo.player_game_context(prop["mlb_id"], date)
            if ctx is None:
                continue                       # not on today's slate
            got = _p_over(repo, date, market, prop)
            if got is None:
                continue
            p_over, support = got
            side = "over" if p_over >= 0.5 else "under"
            p = p_over if side == "over" else 1.0 - p_over
            scored.append({
                "name": (prop["player_name_raw"] or "").upper(),
                "team": ctx.get("team_abbr", ""), "opponent": ctx.get("opponent_abbr", ""),
                "stat": market, "line": prop["line"], "side": side,
                "model_pct": round(p * 100), "support": support, "_p": p,
            })
        scored.sort(key=lambda r: r["_p"], reverse=True)
        rows = [{k: v for k, v in r.items() if k != "_p"} | {"rank": i + 1}
                for i, r in enumerate(scored[:count])]
        prompt = _prompt(rows, market)
        return {"title": f"PRIZEPICKS — {market}", "product": "PrizePicks",
                "market": market, "count": len(rows), "rows": rows, "prompt": prompt}
    finally:
        if conn is not None:
            conn.close()


def _prompt(rows: list[dict], market: str) -> str:
    head = (f'Create a premium "Chances Make Champions" PrizePicks {market} board. '
            "Numbered list; each row: player (team vs opp), the pick (over/under the "
            "line), and our model %.\n\nPICKS:\n")
    body = "\n".join(
        f"{r['rank']}. {r['name']} ({r['team']} vs {r['opponent']}) — "
        f"{r['side'].upper()} {r['line']} {market} — {r['model_pct']}%"
        for r in rows) or "(no PrizePicks props available)"
    return head + body
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_board.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/brains/ev/prizepicks_board.py rambo-backend/tests/test_prizepicks_board.py
git commit -m "$(cat <<'EOF'
feat(betting): PrizePicks model-confidence boards (6 markets)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: API endpoints

**Files:**
- Modify: `api/betting.py` (+ `/prizepicks`, `/prizepicks/parlay`)
- Test: `tests/test_prizepicks_api.py`

**Interfaces:**
- Consumes: `prizepicks_board.prizepicks_board` (Task 5), `prizepicks_parlay.suggest_entries`/`entry_ev` (Task 4), `MlbRepo`, `get_connection`.
- Produces: `GET /betting/prizepicks?market=hr&date=…` → board dict; `POST /betting/prizepicks/parlay` body `{date, market, size?}` → `{suggestions: [...]}` built from the board's legs.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prizepicks_api.py
import os
from fastapi import FastAPI
from fastapi.testclient import TestClient
from db.migrate import get_connection, apply_migrations


def _app(db):
    os.environ["RAMBO_DB_PATH"] = db
    import importlib, api.betting as betting
    importlib.reload(betting)
    app = FastAPI(); app.include_router(betting.router)
    return TestClient(app)


def test_prizepicks_board_empty_ok(tmp_path):
    db = str(tmp_path / "t.db")
    conn = get_connection(db); apply_migrations(conn, "db/migrations"); conn.commit(); conn.close()
    client = _app(db)
    r = client.get("/betting/prizepicks", params={"market": "HR", "date": "2026-06-29"})
    assert r.status_code == 200
    assert r.json()["product"] == "PrizePicks" and r.json()["count"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_api.py -v`
Expected: FAIL — 404 (route not defined)

- [ ] **Step 3: Write minimal implementation**

Add to `api/betting.py`:

```python
@router.get("/prizepicks")
def get_prizepicks_board(market: str, date: Optional[str] = None) -> dict:
    """PrizePicks model-confidence board for a market (HR/SO/TB/H/H+R+RBI/SB).
    Data-only — model probabilities, not a bet-placement path."""
    from brains.ev.prizepicks_board import prizepicks_board
    d = date or datetime.date.today().isoformat()
    return prizepicks_board(d, market.upper())


@router.post("/prizepicks/parlay")
def post_prizepicks_parlay(date: Optional[str] = None, market: str = "HR",
                           size: Optional[int] = None) -> dict:
    """Suggest Power/Flex entries from a market's top board legs."""
    from brains.ev.prizepicks_board import prizepicks_board
    from brains.ev.prizepicks_parlay import suggest_entries
    d = date or datetime.date.today().isoformat()
    board = prizepicks_board(d, market.upper())
    legs = [{"name": r["name"], "p": r["model_pct"] / 100.0} for r in board["rows"]]
    sizes = (size,) if size else (2, 3, 4, 5, 6)
    return {"market": market.upper(), "date": d,
            "suggestions": suggest_entries(legs, sizes=sizes)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/api/betting.py rambo-backend/tests/test_prizepicks_api.py
git commit -m "$(cat <<'EOF'
feat(betting): /betting/prizepicks board + parlay endpoints

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Prep wiring + game_pk resolution + retire dead Pick6

**Files:**
- Modify: `ingestion/prep.py` (call `prizepicks` source instead of dead `props`; resolve game_pk for PrizePicks props)
- Test: `tests/test_prizepicks_prep.py`

**Interfaces:**
- Consumes: `sources.pull_source(conn, "prizepicks")`; `MlbRepo.player_game_context`.
- Produces: after prep, PrizePicks props in `prop_lines` have `game_pk` set for players on the slate (so they survive the date-filter). A helper `_resolve_prizepicks_game_pks(conn, date)` does this.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prizepicks_prep.py
from db.migrate import get_connection, apply_migrations
from ingestion.prep import _resolve_prizepicks_game_pks


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def test_resolves_game_pk_for_slate_player(tmp_path):
    conn = _conn(tmp_path)
    now = "2026-06-29T00:00:00Z"
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_id, away_team_id,"
                 " home_team_abbr, away_team_abbr, scraped_at) "
                 "VALUES (900,'2026-06-29',147,111,'NYY','BOS',?)", (now,))
    conn.execute("INSERT INTO players (mlb_id, full_name, current_team_id, updated_at) "
                 "VALUES (592450,'Aaron Judge',147,?)", (now,))
    conn.execute("INSERT INTO prop_lines (game_pk, mlb_id, book, market, line, multiplier,"
                 " player_name_raw, captured_at) VALUES (NULL,592450,'prizepicks','HR',0.5,NULL,"
                 "'Aaron Judge','2026-06-29T18:00:00Z')")
    n = _resolve_prizepicks_game_pks(conn, "2026-06-29")
    assert n == 1
    assert conn.execute("SELECT game_pk FROM prop_lines").fetchone()[0] == 900
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_prep.py -v`
Expected: FAIL — `ImportError: cannot import name '_resolve_prizepicks_game_pks'`

- [ ] **Step 3: Write minimal implementation**

In `ingestion/prep.py`: replace the dead `props` (Apify Pick6) pull with the `prizepicks` source, and add the resolver. Change the props block:

```python
    if with_props:
        try:
            summary["props"] = pull_source(conn, "prizepicks", {})["items"]
        except Exception as exc:
            logger.warning("PrizePicks props pull failed: %s", exc)
            summary["props"] = 0
        if not summary["props"]:
            logger.warning("PrizePicks props returned 0 — source may be down; "
                           "boards (HR/SO/TB/H/HRR/SB) will be stale or empty.")
```

Add the resolver (and call it after `normalize_pending(conn)` + the existing ID resolver, passing `d`):

```python
def _resolve_prizepicks_game_pks(conn, date: str) -> int:
    """Set game_pk on PrizePicks props whose resolved player is on `date`'s slate,
    so they survive the slate date-filter. Returns the number updated."""
    rows = conn.execute(
        "SELECT id, mlb_id FROM prop_lines WHERE book='prizepicks' "
        "AND game_pk IS NULL AND mlb_id IS NOT NULL").fetchall()
    updated = 0
    for r in rows:
        g = conn.execute(
            "SELECT g.game_pk FROM games g JOIN players p ON p.mlb_id=? "
            "WHERE g.official_date=? AND (g.home_team_id=p.current_team_id "
            "OR g.away_team_id=p.current_team_id) LIMIT 1",
            (r["mlb_id"], date)).fetchone()
        if g:
            conn.execute("UPDATE prop_lines SET game_pk=? WHERE id=?",
                         (g["game_pk"], r["id"]))
            updated += 1
    conn.commit()
    return updated
```

Call it in `prep_slate` after the IdResolver line (`summary["resolved"] = IdResolver(conn).run_unresolved_props()`):

```python
    summary["pp_game_pks"] = _resolve_prizepicks_game_pks(conn, d)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_prep.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/ingestion/prep.py rambo-backend/tests/test_prizepicks_prep.py
git commit -m "$(cat <<'EOF'
feat(betting): prep pulls PrizePicks + resolves prop game_pk; retire dead Pick6

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: cmc-daily.ps1 — PrizePicks boards + entry EV

**Files:**
- Modify: `cmc-daily.ps1`

**Interfaces:** consumes `GET /betting/prizepicks` + `POST /betting/prizepicks/parlay`.

- [ ] **Step 1: Add the PrizePicks section to the console + Word doc**

After the existing board pulls in `cmc-daily.ps1`, add (console + a Word table per market, reusing the `Add-Table` helper):

```powershell
# PrizePicks model-confidence boards (replaces dead DK Pick6 markets)
$ppMarkets = [ordered]@{ HR="Home Runs"; SO="Strikeouts"; TB="Total Bases"; H="Hits"; "H+R+RBI"="H+R+RBI"; SB="Stolen Bases" }
Add-Line ""
Add-Header "PRIZEPICKS BOARDS (model confidence)"
foreach ($mk in $ppMarkets.Keys) {
    $b = Get-Json "$Base/betting/prizepicks?market=$([uri]::EscapeDataString($mk))&date=$Date"
    Add-Line ""
    Add-Header ("{0} — top {1} by model %" -f $ppMarkets[$mk], $b.count)
    if ($b.rows.Count -gt 0) {
        $rows = foreach ($r in $b.rows) { ,@($r.rank, $r.name, $r.team, $r.opponent, $r.side.ToUpper(), $r.line, "$($r.model_pct)%") }
        Add-Table @("#","Player","Team","Opp","Side","Line","Model") $rows
    } else { Add-Line "(no PrizePicks props — source may be down)" }
}
```

- [ ] **Step 2: Parse-check the script**

Run (PowerShell): `[System.Management.Automation.Language.Parser]::ParseFile("C:\Users\dokun\PycharmProjects\R.A.M.B.O\cmc-daily.ps1",[ref]$null,[ref]([ref]$errs).Value)` — Expected: no parse errors.

- [ ] **Step 3: Commit**

```bash
git add cmc-daily.ps1
git commit -m "$(cat <<'EOF'
feat(cmc): PrizePicks boards in the daily doc (tables per market)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Live gate + full suite

**Files:** none (operational verification).

- [ ] **Step 1: Pull real PrizePicks + verify markets land**

```bash
cd rambo-backend && ./.venv/Scripts/python.exe -c "from db.migrate import get_connection; from ingestion.sources import pull_source; from ingestion.normalize import normalize_pending; c=get_connection('data/mlb_ingest.db'); print(pull_source(c,'prizepicks',{})['items'],'items'); print(normalize_pending(c)); import sqlite3; c.row_factory=sqlite3.Row; print([dict(r) for r in c.execute(\"SELECT market, COUNT(*) n FROM prop_lines WHERE book='prizepicks' GROUP BY market\")])"
```
Expected: hundreds of items; prop_lines rows for HR/SO/TB/H/H+R+RBI/SB.

- [ ] **Step 2: Render a board + a parlay on real data**

```bash
cd rambo-backend && ./.venv/Scripts/python.exe -c "from brains.ev.prizepicks_board import prizepicks_board; b=prizepicks_board('2026-06-29','HR'); print('rows',b['count']); [print(r['rank'],r['name'],r['side'],r['line'],r['model_pct']) for r in b['rows'][:6]]"
```
Expected: ranked HR legs with model %; sanity-check names/sides are plausible. (If 0, the slate may not be loaded — run prep first.)

- [ ] **Step 3: Full suite gate**

Run: `cd rambo-backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: all prior tests pass plus the new ones. No regressions.

- [ ] **Step 4: Commit recorded result + push**

```bash
git commit --allow-empty -m "$(cat <<'EOF'
chore(betting): PrizePicks boards verified on live slate

<paste board counts per market + a sample HR board>

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
git push -u origin feat/prizepicks-boards
```

---

## Notes for the implementer
- The board reuses existing models verbatim — do NOT re-implement HR/Poisson/K math; feed them the PrizePicks `line`.
- For SO, the PrizePicks line is a pitcher-K total (e.g. 6.5); `binom_prob_over(n=round(BF), p=k_rate, j=ceil(line))` gives P(over). `k_projection`'s opponent_team_id can stay None (neutral) for the board; a later pass can resolve it.
- PrizePicks props carry `multiplier=NULL` by design — they never enter the legacy multiplier markets in `market.py` (those filter on `multiplier`). The boards are a separate path.
- Do NOT tune the Power/Flex tables to look good — they're PrizePicks' published values; verify against the live app and leave them as config.
- The honest-result discipline holds: PrizePicks lines are sharp, so model edges + entry EV are often thin/negative — report them straight.
