# PrizePicks Demon/Goblin Tier Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest all three PrizePicks tiers (goblin/standard/demon) for the 6 mapped markets and surface a per-player line ladder with model P(over) per line on a dedicated board — no payout/EV — without changing existing standard boards.

**Architecture:** Add an `odds_type` column to `prop_lines` (migration), have `_insert_prop` always write it (default `"standard"`), drop the standard-only filter in `map_prizepicks`, make `latest_props` tier-aware (default `"standard"` = no regression; `None` = all tiers, per-tier dedup), and add a `brains/ev/prizepicks_tiers.py` board + endpoint that reuses `prizepicks_board._p_over`.

**Tech Stack:** Python 3, SQLite (migrations via `db/migrate.py`), FastAPI, pytest. No new dependencies. Reuse `brains/ev/prizepicks_board._p_over`.

## Global Constraints

- Existing standard boards must stay byte-for-byte unchanged (pinned by a regression test). `latest_props` default `odds_type="standard"`.
- New `odds_type` column: `TEXT NOT NULL DEFAULT 'standard'`. Tiers have distinct lines by construction → no `snapshot_key` collision; do NOT rebuild the generated column.
- Ingest the 6 mapped markets only (`STAT_MARKET_MAP`: HR, SO, TB, H, H+R+RBI, SB) across all tiers; keep the `stat_type` filter, drop only the `odds_type != "standard"` clause.
- No payout/EV for tiers — P(over) only; never fabricate a payout. Honest framing in the board prompt (goblin = safer/lower line, demon = swing/higher line; NOT guarantees).
- Reuse `prizepicks_board._p_over` — no new modeling.
- No new dependencies. Board follows `prizepicks_board.py` shape (`_open(repo)`, dict with title/product/count/rows/prompt).
- Run pytest from `rambo-backend/` with the venv python: `./.venv/Scripts/python.exe -m pytest`.
- DB tests use `get_connection` + `apply_migrations(conn, "db/migrations")` (see `tests/test_prizepicks_normalize.py`).
- Commit messages via Bash heredoc (never PowerShell), ending with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

### Task 1: Migration + `_insert_prop` writes `odds_type`

**Files:**
- Create: `rambo-backend/db/migrations/009_prop_odds_type.sql`
- Modify: `rambo-backend/ingestion/normalize.py` (`_insert_prop`, ~line 150)
- Test: `rambo-backend/tests/test_prop_odds_type_migration.py`

**Interfaces:**
- Consumes: `db.migrate.get_connection`, `apply_migrations`.
- Produces: `prop_lines.odds_type` column (default `'standard'`); `_insert_prop` writes `p["odds_type"]`, defaulting to `"standard"` when the caller omits it.

- [ ] **Step 1: Write the failing test**

```python
# rambo-backend/tests/test_prop_odds_type_migration.py
from db.migrate import get_connection, apply_migrations
from ingestion.normalize import _insert_prop


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def test_odds_type_column_exists_default_standard(tmp_path):
    conn = _conn(tmp_path)
    cols = {r["name"]: r for r in conn.execute("PRAGMA table_info(prop_lines)")}
    assert "odds_type" in cols
    assert cols["odds_type"]["dflt_value"].strip("'") == "standard"


def test_insert_prop_defaults_odds_type_standard(tmp_path):
    conn = _conn(tmp_path)
    _insert_prop(conn, {"game_pk": None, "mlb_id": None, "book": "prizepicks",
                        "market": "HR", "line": 0.5, "over_price": None,
                        "under_price": None, "multiplier": None,
                        "player_name_raw": "X", "captured_at": "2026-06-29T00:00Z"})
    assert conn.execute("SELECT odds_type FROM prop_lines").fetchone()["odds_type"] == "standard"


def test_insert_prop_writes_given_odds_type(tmp_path):
    conn = _conn(tmp_path)
    _insert_prop(conn, {"game_pk": None, "mlb_id": None, "book": "prizepicks",
                        "market": "HR", "line": 1.5, "over_price": None,
                        "under_price": None, "multiplier": None,
                        "player_name_raw": "Y", "captured_at": "2026-06-29T00:00Z",
                        "odds_type": "demon"})
    assert conn.execute("SELECT odds_type FROM prop_lines WHERE player_name_raw='Y'"
                        ).fetchone()["odds_type"] == "demon"


def test_migration_idempotent(tmp_path):
    conn = _conn(tmp_path)
    applied = apply_migrations(conn, "db/migrations")   # second run
    assert "009_prop_odds_type.sql" not in applied      # already applied first time
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prop_odds_type_migration.py -v`
Expected: FAIL — no `odds_type` column.

- [ ] **Step 3: Write the migration + update `_insert_prop`**

Create `rambo-backend/db/migrations/009_prop_odds_type.sql`:

```sql
-- Add the PrizePicks projection tier (standard | demon | goblin) to prop_lines.
-- Tiers share a player/stat but always carry distinct lines (goblin < standard <
-- demon), so the existing STORED snapshot_key (which includes `line`) cannot
-- collide across tiers; we intentionally do NOT rebuild that generated column
-- (SQLite cannot ALTER it in place). Non-PrizePicks rows stay 'standard'.
ALTER TABLE prop_lines ADD COLUMN odds_type TEXT NOT NULL DEFAULT 'standard';
```

In `ingestion/normalize.py`, update `_insert_prop` to default + write the column:

```python
def _insert_prop(conn: sqlite3.Connection, p: dict) -> None:
    p.setdefault("odds_type", "standard")
    conn.execute(
        """INSERT INTO prop_lines
             (game_pk, mlb_id, book, market, line, over_price, under_price,
              multiplier, player_name_raw, captured_at, odds_type)
           VALUES (:game_pk,:mlb_id,:book,:market,:line,:over_price,:under_price,
              :multiplier,:player_name_raw,:captured_at,:odds_type)
           ON CONFLICT(snapshot_key) DO NOTHING;""",
        p,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prop_odds_type_migration.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/db/migrations/009_prop_odds_type.sql rambo-backend/ingestion/normalize.py rambo-backend/tests/test_prop_odds_type_migration.py
git commit -m "$(cat <<'EOF'
feat(betting): add prop_lines.odds_type column; _insert_prop writes it

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `map_prizepicks` ingests all tiers

**Files:**
- Modify: `rambo-backend/ingestion/normalize.py` (`map_prizepicks`, ~line 475)
- Test: `rambo-backend/tests/test_prizepicks_tiers_normalize.py`

**Interfaces:**
- Consumes: `_insert_prop` (Task 1, now writes `odds_type`); `STAT_MARKET_MAP`.
- Produces: `map_prizepicks` lands standard, demon, and goblin projections for mapped markets, storing the projection's `odds_type`.

- [ ] **Step 1: Write the failing test**

```python
# rambo-backend/tests/test_prizepicks_tiers_normalize.py
from db.migrate import get_connection, apply_migrations
from ingestion.normalize import map_prizepicks


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _item(odds, line, name="Aaron Judge", stat="Home Runs"):
    return {"projection_id": f"p-{odds}-{line}", "player_name": name, "team": "NYY",
            "position": "OF", "stat_type": stat, "line": line, "odds_type": odds,
            "start_time": "2026-06-29T19:00:00-04:00", "game_id": "g9"}


def test_all_three_tiers_land(tmp_path):
    conn = _conn(tmp_path)
    for odds, line in (("goblin", 0.5), ("standard", 0.5), ("demon", 1.5)):
        assert map_prizepicks(conn, _item(odds, line), "2026-06-29T18:00:00Z") is True
    rows = conn.execute("SELECT odds_type, line, market FROM prop_lines "
                        "ORDER BY odds_type").fetchall()
    tiers = {r["odds_type"] for r in rows}
    assert tiers == {"goblin", "standard", "demon"}
    assert all(r["market"] == "HR" for r in rows)


def test_unmapped_stat_still_skipped_all_tiers(tmp_path):
    conn = _conn(tmp_path)
    map_prizepicks(conn, _item("demon", 100.5, stat="Pitches Thrown"), "2026-06-29T18:00:00Z")
    assert conn.execute("SELECT COUNT(*) c FROM prop_lines").fetchone()["c"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_tiers_normalize.py -v`
Expected: FAIL — `test_all_three_tiers_land` lands only the standard row (demon/goblin dropped by the current filter).

- [ ] **Step 3: Update `map_prizepicks`**

Current guard (drop the `odds_type` clause, keep the stat clause) and store `odds_type`:

```python
def map_prizepicks(conn, item, scraped_at) -> bool:
    """PrizePicks projection -> prop_lines. Keeps the 6 mapped stat_types across
    ALL tiers (standard | demon | goblin); the tier is stored in odds_type.
    multiplier is NULL (payouts are play-level). mlb_id + game_pk resolved downstream."""
    if item.get("stat_type") not in STAT_MARKET_MAP:
        return True  # handled: not a board market
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
        "odds_type": item.get("odds_type") or "standard",
    })
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_tiers_normalize.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/ingestion/normalize.py rambo-backend/tests/test_prizepicks_tiers_normalize.py
git commit -m "$(cat <<'EOF'
feat(betting): ingest all PrizePicks tiers (goblin/standard/demon)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Tier-aware `latest_props`

**Files:**
- Modify: `rambo-backend/repositories/mlb_repo.py` (`latest_props`, ~line 100)
- Test: `rambo-backend/tests/test_latest_props_odds_type.py`

**Interfaces:**
- Consumes: `prop_lines.odds_type` (Task 1); tier rows (Task 2).
- Produces: `latest_props(..., odds_type: str | None = "standard")` — default returns standard-only (existing callers unchanged); `odds_type=None` returns all tiers, deduped per `(book, market, pkey, odds_type)`.

- [ ] **Step 1: Write the failing test**

```python
# rambo-backend/tests/test_latest_props_odds_type.py
from db.migrate import get_connection, apply_migrations
from ingestion.normalize import _insert_prop
from repositories.mlb_repo import MlbRepo


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _seed_game_and_player(conn):
    conn.execute("INSERT INTO games (game_pk, official_date, season) "
                 "VALUES (1, '2026-06-29', 2026)")
    conn.execute("INSERT INTO players (mlb_id, full_name) VALUES (100, 'Aaron Judge')")


def _seed_tier(conn, odds, line):
    _insert_prop(conn, {"game_pk": 1, "mlb_id": 100, "book": "prizepicks",
                        "market": "HR", "line": line, "over_price": None,
                        "under_price": None, "multiplier": None,
                        "player_name_raw": "Aaron Judge",
                        "captured_at": "2026-06-29T18:00:00Z", "odds_type": odds})


def test_default_returns_standard_only(tmp_path):
    conn = _conn(tmp_path); _seed_game_and_player(conn)
    for odds, line in (("goblin", 0.5), ("standard", 0.5), ("demon", 1.5)):
        _seed_tier(conn, odds, line)
    repo = MlbRepo(conn)
    rows = repo.latest_props(market="HR", official_date="2026-06-29")
    assert len(rows) == 1 and rows[0]["odds_type"] == "standard"


def test_none_returns_all_tiers(tmp_path):
    conn = _conn(tmp_path); _seed_game_and_player(conn)
    for odds, line in (("goblin", 0.5), ("standard", 0.5), ("demon", 1.5)):
        _seed_tier(conn, odds, line)
    repo = MlbRepo(conn)
    rows = repo.latest_props(market="HR", official_date="2026-06-29", odds_type=None)
    assert {r["odds_type"] for r in rows} == {"goblin", "standard", "demon"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_latest_props_odds_type.py -v`
Expected: FAIL — `latest_props()` has no `odds_type` param / returns all rows.

- [ ] **Step 3: Update `latest_props`**

Replace the method body's query + signature. Add `odds_type` to the signature, the dedup subquery `GROUP BY`, the join, and an optional WHERE filter:

```python
    def latest_props(self, game_pk: Optional[int] = None,
                     market: Optional[str] = None,
                     resolved_only: bool = True,
                     official_date: Optional[str] = None,
                     odds_type: Optional[str] = "standard") -> list[dict]:
        # `official_date` restricts to props whose game is on that date — without it
        # the latest-per-player snapshot leaks STALE props. `odds_type` defaults to
        # 'standard' (existing boards unchanged); pass None to get all tiers. The
        # dedup is always per-tier so goblin/standard/demon don't collapse.
        q = """
            SELECT p.* FROM prop_lines p
            JOIN (
                SELECT book, market, odds_type,
                       COALESCE(CAST(mlb_id AS TEXT), player_name_raw) AS pkey,
                       MAX(captured_at) AS mx
                FROM prop_lines GROUP BY book, market, odds_type, pkey
            ) last
              ON p.book=last.book AND p.market=last.market
             AND p.odds_type=last.odds_type
             AND COALESCE(CAST(p.mlb_id AS TEXT), p.player_name_raw)=last.pkey
             AND p.captured_at=last.mx
            WHERE 1=1
        """
        params: list[Any] = []
        if game_pk is not None:
            q += " AND p.game_pk=?"; params.append(game_pk)
        if market:
            q += " AND p.market=?"; params.append(market)
        if odds_type is not None:
            q += " AND p.odds_type=?"; params.append(odds_type)
        if resolved_only:
            q += " AND p.mlb_id IS NOT NULL"
        if official_date is not None:
            q += (" AND p.game_pk IN (SELECT game_pk FROM games "
                  "WHERE official_date=?)"); params.append(official_date)
        q += " ORDER BY p.market, p.player_name_raw"
        return _dicts(self.conn.execute(q, params))
```

(Keep the existing `_dicts(...)` return and the trailing lines exactly; only the signature, the subquery `GROUP BY`/join, and the new `odds_type` WHERE change.)

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_latest_props_odds_type.py -v`
Then confirm no regression in existing prop tests:
`./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_normalize.py tests/test_alt_k_normalize.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/repositories/mlb_repo.py rambo-backend/tests/test_latest_props_odds_type.py
git commit -m "$(cat <<'EOF'
feat(betting): tier-aware latest_props (standard default, per-tier dedup)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Tier board `prizepicks_tiers`

**Files:**
- Create: `rambo-backend/brains/ev/prizepicks_tiers.py`
- Test: `rambo-backend/tests/test_prizepicks_tiers_board.py`

**Interfaces:**
- Consumes:
  - `latest_props(market=, official_date=, odds_type=None)` (Task 3).
  - `repo.player_game_context(mlb_id, date) -> dict | None` (existing; used by `prizepicks_board`).
  - `brains.ev.prizepicks_board._p_over(repo, date, market, prop) -> tuple[float, str] | None` — model P(over the line) + support string; `prop` needs keys `mlb_id`, `line`, `player_name_raw`.
- Produces:
  - `prizepicks_tiers(date: str, market: str, repo=None, *, count: int = 11) -> dict` returning `{"title", "product": "PrizePicks", "market", "count", "rows", "prompt"}`. Each row: `{"name", "team", "opponent", "market", "tiers": {<tier>: {"line", "model_pct"}}}` for tiers present with a usable model prob. Ranked by the standard tier's `model_pct` (fallback to max present tier). `_TIER_ORDER = ("goblin", "standard", "demon")`.

- [ ] **Step 1: Write the failing test**

```python
# rambo-backend/tests/test_prizepicks_tiers_board.py
from brains.ev import prizepicks_tiers as pt


class FakeRepo:
    def __init__(self):
        self._props = [
            {"mlb_id": 1, "line": 0.5, "book": "prizepicks", "odds_type": "goblin",
             "player_name_raw": "Aaron Judge"},
            {"mlb_id": 1, "line": 0.5, "book": "prizepicks", "odds_type": "standard",
             "player_name_raw": "Aaron Judge"},
            {"mlb_id": 1, "line": 1.5, "book": "prizepicks", "odds_type": "demon",
             "player_name_raw": "Aaron Judge"},
        ]

    def latest_props(self, market=None, official_date=None, odds_type=None):
        assert odds_type is None        # board asks for all tiers
        return list(self._props)

    def player_game_context(self, mlb_id, date):
        return {"team_abbr": "NYY", "opponent_abbr": "BOS"}


def test_tiers_board_builds_ladder(monkeypatch):
    # P(over): goblin 0.5 -> .80, standard 0.5 -> .55, demon 1.5 -> .25
    probs = {("goblin", 0.5): 0.80, ("standard", 0.5): 0.55, ("demon", 1.5): 0.25}
    def fake_p_over(repo, date, market, prop):
        # identify tier by line+the seeded order; here line alone disambiguates demon
        for (tier, line), p in probs.items():
            if line == prop["line"] and tier in pt._TIER_ORDER:
                # pick the tier matching this row's odds_type if present
                if prop.get("odds_type") == tier:
                    return p, "form"
        return None
    monkeypatch.setattr(pt, "_p_over", fake_p_over)
    board = pt.prizepicks_tiers("2026-06-29", "HR", repo=FakeRepo())
    assert board["title"] == "PRIZEPICKS TIERS — HR"
    assert board["count"] == 1
    row = board["rows"][0]
    assert row["name"] == "AARON JUDGE"
    assert set(row["tiers"]) == {"goblin", "standard", "demon"}
    assert row["tiers"]["goblin"] == {"line": 0.5, "model_pct": 80}
    assert row["tiers"]["demon"] == {"line": 1.5, "model_pct": 25}
    assert "ALT" not in board["prompt"] and "TIERS" in board["prompt"].upper()


def test_tiers_board_empty(monkeypatch):
    class Empty(FakeRepo):
        def latest_props(self, market=None, official_date=None, odds_type=None):
            return []
    board = pt.prizepicks_tiers("2026-06-29", "HR", repo=Empty())
    assert board["count"] == 0 and board["rows"] == []
```

Note: the board passes each prop row (including its `odds_type`) to `_p_over`; `_p_over` ignores `odds_type` in production (it only reads `mlb_id`/`line`/`player_name_raw`), but the fake uses it to disambiguate. The board must therefore include `odds_type` on the dict it hands to `_p_over` (it already has it from the row).

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_tiers_board.py -v`
Expected: FAIL — module `prizepicks_tiers` not found.

- [ ] **Step 3: Write the board**

```python
# rambo-backend/brains/ev/prizepicks_tiers.py
"""PrizePicks tier board (goblin/standard/demon). Per player, the line ladder
across tiers with our model P(over) at each line. No payout/EV — PrizePicks
doesn't expose tier multipliers. Reuses prizepicks_board._p_over."""
from __future__ import annotations

import os

from brains.ev.prizepicks_board import _p_over

DB_PATH = os.environ.get("RAMBO_DB_PATH", "data/mlb_ingest.db")
BOARD_SIZE = 11
_TIER_ORDER = ("goblin", "standard", "demon")


def _open(repo):
    if repo is not None:
        return repo, None
    from db.migrate import get_connection
    from repositories.mlb_repo import MlbRepo
    conn = get_connection(DB_PATH)
    return MlbRepo(conn), conn


def prizepicks_tiers(date: str, market: str, repo=None, *, count: int = BOARD_SIZE) -> dict:
    repo, conn = _open(repo)
    try:
        by_player: dict = {}
        for prop in repo.latest_props(market=market, official_date=date, odds_type=None):
            if prop.get("book") != "prizepicks" or prop.get("mlb_id") is None:
                continue
            tier = prop.get("odds_type") or "standard"
            if tier not in _TIER_ORDER:
                continue
            ctx = repo.player_game_context(prop["mlb_id"], date)
            if ctx is None:
                continue
            got = _p_over(repo, date, market, prop)
            if got is None:
                continue
            p_over, _support = got
            entry = by_player.setdefault(prop["mlb_id"], {
                "name": (prop.get("player_name_raw") or "").upper(),
                "team": ctx.get("team_abbr", ""), "opponent": ctx.get("opponent_abbr", ""),
                "market": market, "tiers": {}})
            entry["tiers"][tier] = {"line": prop["line"], "model_pct": round(p_over * 100)}

        def _rank_key(e: dict) -> float:
            t = e["tiers"]
            if "standard" in t:
                return t["standard"]["model_pct"]
            return max(v["model_pct"] for v in t.values())

        rows = sorted((e for e in by_player.values() if e["tiers"]),
                      key=_rank_key, reverse=True)[:count]
        return {"title": f"PRIZEPICKS TIERS — {market}", "product": "PrizePicks",
                "market": market, "count": len(rows), "rows": rows,
                "prompt": _prompt(rows, market)}
    finally:
        if conn is not None:
            conn.close()


def _prompt(rows: list[dict], market: str) -> str:
    head = (f'Create a premium "Chances Make Champions" PrizePicks {market} TIERS '
            "board. For each player show the goblin / standard / demon line and our "
            "model % to go over it.\n\n"
            "KEY: goblin = safer, lower line; demon = swing, higher line. These are "
            "model probabilities, NOT guarantees. PrizePicks does not publish tier "
            "payouts, so no EV is shown.\n\nPLAYERS:\n")
    lines = []
    for i, r in enumerate(rows, 1):
        segs = [f"{t} {r['tiers'][t]['line']} ({r['tiers'][t]['model_pct']}%)"
                for t in _TIER_ORDER if t in r["tiers"]]
        lines.append(f"{i}. {r['name']} ({r['team']} vs {r['opponent']}) — "
                     + " · ".join(segs))
    return head + ("\n".join(lines) or "(no PrizePicks tier props available)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_tiers_board.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/brains/ev/prizepicks_tiers.py rambo-backend/tests/test_prizepicks_tiers_board.py
git commit -m "$(cat <<'EOF'
feat(betting): PrizePicks tier board (goblin/standard/demon ladder + P(over))

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: API endpoint

**Files:**
- Modify: `rambo-backend/api/betting.py` (near the `/prizepicks` route ~line 294)
- Test: `rambo-backend/tests/test_prizepicks_tiers_api.py`

**Interfaces:**
- Consumes: `brains.ev.prizepicks_tiers.prizepicks_tiers` (Task 4).
- Produces: `GET /betting/prizepicks-tiers?market=&date=` → `prizepicks_tiers(date, market.upper())`.

- [ ] **Step 1: Write the failing test**

```python
# rambo-backend/tests/test_prizepicks_tiers_api.py
from fastapi.testclient import TestClient
from main import app
import brains.ev.prizepicks_tiers as pt

client = TestClient(app)


def test_prizepicks_tiers_endpoint(monkeypatch):
    monkeypatch.setattr(pt, "prizepicks_tiers",
                        lambda d, m, **k: {"title": f"PRIZEPICKS TIERS — {m}",
                                           "product": "PrizePicks", "market": m,
                                           "count": 0, "rows": [], "prompt": "x"})
    r = client.get("/betting/prizepicks-tiers?market=hr&date=2026-06-29")
    assert r.status_code == 200
    assert r.json()["market"] == "HR"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_tiers_api.py -v`
Expected: FAIL — 404.

- [ ] **Step 3: Add the route**

In `api/betting.py`, after the existing `get_prizepicks_board` route:

```python
@router.get("/prizepicks-tiers")
def get_prizepicks_tiers(market: str, date: Optional[str] = None) -> dict:
    """PrizePicks goblin/standard/demon line ladder for a market, with model
    P(over) per line. Data-only; no payout/EV (tiers' payouts aren't published)."""
    from brains.ev.prizepicks_tiers import prizepicks_tiers
    d = date or datetime.date.today().isoformat()
    return prizepicks_tiers(d, market.upper())
```

Note: the test monkeypatches `brains.ev.prizepicks_tiers.prizepicks_tiers`, and the handler imports the function from that module at call time, so the patch takes effect.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_tiers_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/api/betting.py rambo-backend/tests/test_prizepicks_tiers_api.py
git commit -m "$(cat <<'EOF'
feat(betting): /betting/prizepicks-tiers endpoint

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Full-suite regression + finish

**Files:** none (verification only).

- [ ] **Step 1: Run the whole suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: all prior tests pass (664 baseline on `main` + the new tier tests). If any pre-existing test fails, investigate before proceeding — do not edit unrelated tests to make them pass. Pay special attention to existing PrizePicks board tests (`test_prizepicks_*`) to confirm the standard boards did not regress.

- [ ] **Step 2: Live sanity-check (best effort)**

Run: `./.venv/Scripts/python.exe -c "from brains.ev.prizepicks_tiers import prizepicks_tiers; import json, datetime; b=prizepicks_tiers(datetime.date.today().isoformat(), 'HR'); print(b['title'], b['count'])"`
Expected: prints the title + a count (0 is acceptable if no tier props are loaded today — the point is no exception).

- [ ] **Step 3: Confirm clean tree + push**

```bash
git status -s
git push -u origin feat/prizepicks-tiers
```

- [ ] **Step 4: Open the PR**

```bash
gh pr create --base main --head feat/prizepicks-tiers --title "PrizePicks demon/goblin tier board" --body "$(cat <<'EOF'
Ingest all three PrizePicks tiers (goblin/standard/demon) and surface a per-player line ladder with model P(over) per line.

- prop_lines.odds_type column (migration 009); _insert_prop writes it (default standard)
- map_prizepicks ingests all tiers for the 6 mapped markets (was standard-only)
- latest_props tier-aware: default standard (no regression), odds_type=None = all tiers, per-tier dedup
- brains/ev/prizepicks_tiers.py board + GET /betting/prizepicks-tiers (reuses _p_over)
- No payout/EV (PrizePicks doesn't expose tier multipliers) — P(over) only, honest framing

Existing standard boards unchanged (regression-pinned). Data-only (Sentinel boundary).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Notes for the implementer

- The migration is plain `ALTER TABLE ... ADD COLUMN`; `snapshot_key` is a STORED generated column and is intentionally left unchanged (tiers carry distinct lines, so no collision).
- `_insert_prop` is called by several normalizers (odds props, Pick6, both PrizePicks paths). `p.setdefault("odds_type", "standard")` keeps every non-tier caller correct with no edits to them.
- The ONLY behavioral change to standard boards is none — `latest_props` defaults to `odds_type="standard"`. Task 3's regression check and Task 6's full suite guard this.
- `_p_over` lives in `brains/ev/prizepicks_board.py` and reads `mlb_id`/`line`/`player_name_raw` from the prop dict; the tier board passes the full `prop` row so it works unchanged.
