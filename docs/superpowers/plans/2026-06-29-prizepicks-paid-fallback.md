# PrizePicks Paid Apify Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-fall back to a configurable, cost-capped Apify actor when the free public PrizePicks API fails or returns 0 props, adapting its output to the existing item shape so the existing normalizer handles it unchanged.

**Architecture:** New env-driven `paid_actor_config()` in `config/prizepicks.py`; a new `ingestion/prizepicks_apify_client.py` that runs the actor via the existing spend-guarded `run_actor`, adapts each item to the free client's flat shape, and returns a `RunResult` tagged `actor_id="prizepicks"` (so `map_prizepicks` handles it). A `prizepicks_paid` source in `sources.py`, and an auto-fallback branch in `prep.py`.

**Tech Stack:** Python 3, SQLite (`MlbRepo`/migrations), pytest. No new dependencies. Reuse `ingestion/apify_client_wrapper.py` (`run_actor`, `ActorConfig`, `RunResult`, `ApifyIngestError`, `get_client`).

## Global Constraints

- Free public API stays PRIMARY; paid actor is an AUTO-FALLBACK (fires only when free fails or returns 0 props).
- Actor id is env-configured via `PRIZEPICKS_APIFY_ACTOR`; when unset, `paid_actor_config()` returns `None` and fallback is disabled (free behavior unchanged). No working hard-coded default.
- Paid client emits `RunResult(actor_id="prizepicks", ...)` so the EXISTING `map_prizepicks` normalizer handles it unchanged. Standard-tier filter stays (demon/goblin = sub-project A, NOT this plan).
- Adapter output item shape is EXACTLY the free client's: keys `projection_id, player_name, team, position, stat_type, line, odds_type, start_time, game_id`.
- Never-raise ingestion contract: the client returns 0 items on any error, never propagates an exception.
- Drop malformed/non-MLB items rather than fabricate. No bet placement (Sentinel boundary).
- No new dependencies. Reuse `apify_client_wrapper`. Env-driven config like `config/the_odds_api.py`.
- Run pytest from `rambo-backend/` with the venv python: `./.venv/Scripts/python.exe -m pytest`.
- Commit messages via Bash heredoc (never PowerShell), ending with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

### Task 1: Env-driven paid actor config

**Files:**
- Modify: `rambo-backend/config/prizepicks.py`
- Test: `rambo-backend/tests/test_prizepicks_paid_config.py`

**Interfaces:**
- Consumes: `ActorConfig` from `ingestion/apify_client_wrapper.py`.
- Produces:
  - `paid_actor_config() -> ActorConfig | None` — `ActorConfig` when `PRIZEPICKS_APIFY_ACTOR` is set, else `None`. Reads `PRIZEPICKS_APIFY_PRICE_PER_1K` (default `0.10`), `PRIZEPICKS_APIFY_MAX_COST_USD` (default `2.00`), `PRIZEPICKS_APIFY_MAX_ITEMS` (default `2000`).
  - `paid_actor_input() -> dict` — parsed `PRIZEPICKS_APIFY_INPUT` JSON (default `{"league": "MLB"}`); bad JSON → default.

- [ ] **Step 1: Write the failing test**

```python
# rambo-backend/tests/test_prizepicks_paid_config.py
import importlib
from config import prizepicks as cfg


def test_no_actor_env_disables_fallback(monkeypatch):
    monkeypatch.delenv("PRIZEPICKS_APIFY_ACTOR", raising=False)
    assert cfg.paid_actor_config() is None


def test_actor_env_builds_config(monkeypatch):
    monkeypatch.setenv("PRIZEPICKS_APIFY_ACTOR", "someuser/pp-scraper")
    monkeypatch.setenv("PRIZEPICKS_APIFY_MAX_COST_USD", "1.50")
    monkeypatch.setenv("PRIZEPICKS_APIFY_MAX_ITEMS", "500")
    ac = cfg.paid_actor_config()
    assert ac is not None
    assert ac.actor_id == "someuser/pp-scraper"
    assert ac.max_cost_usd == 1.50
    assert ac.max_items == 500


def test_actor_input_defaults_and_parses(monkeypatch):
    monkeypatch.delenv("PRIZEPICKS_APIFY_INPUT", raising=False)
    assert cfg.paid_actor_input() == {"league": "MLB"}
    monkeypatch.setenv("PRIZEPICKS_APIFY_INPUT", '{"league": "MLB", "x": 1}')
    assert cfg.paid_actor_input() == {"league": "MLB", "x": 1}
    monkeypatch.setenv("PRIZEPICKS_APIFY_INPUT", "not json")
    assert cfg.paid_actor_input() == {"league": "MLB"}   # bad JSON -> default
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_paid_config.py -v`
Expected: FAIL — `module config.prizepicks has no attribute 'paid_actor_config'`.

- [ ] **Step 3: Write minimal implementation**

Append to `config/prizepicks.py`:

```python
import json as _json
import os as _os


def paid_actor_input() -> dict:
    """Apify run input for the paid PrizePicks actor. Bad JSON -> default."""
    raw = _os.environ.get("PRIZEPICKS_APIFY_INPUT")
    if not raw:
        return {"league": "MLB"}
    try:
        val = _json.loads(raw)
        return val if isinstance(val, dict) else {"league": "MLB"}
    except (ValueError, TypeError):
        return {"league": "MLB"}


def paid_actor_config():
    """ActorConfig for the env-configured paid PrizePicks Apify actor, or None
    when PRIZEPICKS_APIFY_ACTOR is unset (fallback disabled)."""
    actor = _os.environ.get("PRIZEPICKS_APIFY_ACTOR")
    if not actor:
        return None
    from ingestion.apify_client_wrapper import ActorConfig
    return ActorConfig(
        actor_id=actor,
        max_items=int(_os.environ.get("PRIZEPICKS_APIFY_MAX_ITEMS", "2000")),
        price_per_1k=float(_os.environ.get("PRIZEPICKS_APIFY_PRICE_PER_1K", "0.10")),
        max_cost_usd=float(_os.environ.get("PRIZEPICKS_APIFY_MAX_COST_USD", "2.00")),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_paid_config.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/config/prizepicks.py rambo-backend/tests/test_prizepicks_paid_config.py
git commit -m "$(cat <<'EOF'
feat(betting): env-driven paid PrizePicks Apify actor config

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Defensive item adapter

**Files:**
- Create: `rambo-backend/ingestion/prizepicks_apify_client.py`
- Test: `rambo-backend/tests/test_prizepicks_apify.py`

**Interfaces:**
- Consumes: nothing (pure function).
- Produces:
  - `_adapt_item(raw: dict) -> dict | None` — maps a raw actor item to the free client's flat shape; returns `None` if `player_name`, `line`, or `stat_type` is missing/unparseable, or if a present league field is non-MLB. Items with no league field are kept.

Free shape keys (exact): `projection_id, player_name, team, position, stat_type, line, odds_type, start_time, game_id`. `odds_type` defaults to `"standard"`.

- [ ] **Step 1: Write the failing test**

```python
# rambo-backend/tests/test_prizepicks_apify.py
from ingestion import prizepicks_apify_client as ppa


def test_adapt_canonical_item():
    raw = {"id": "p1", "player_name": "Aaron Judge", "team": "NYY",
           "position": "OF", "stat_type": "Home Runs", "line": 0.5,
           "odds_type": "standard", "start_time": "2026-06-29T19:00:00-04:00",
           "game_id": "g9"}
    out = ppa._adapt_item(raw)
    assert out == {"projection_id": "p1", "player_name": "Aaron Judge",
                   "team": "NYY", "position": "OF", "stat_type": "Home Runs",
                   "line": 0.5, "odds_type": "standard",
                   "start_time": "2026-06-29T19:00:00-04:00", "game_id": "g9"}


def test_adapt_key_aliases():
    raw = {"projectionId": "p2", "playerName": "Mookie Betts",
           "statType": "Hits", "lineScore": 1.5, "oddsType": "goblin",
           "startTime": "t", "gameId": "g"}
    out = ppa._adapt_item(raw)
    assert out["projection_id"] == "p2"
    assert out["player_name"] == "Mookie Betts"
    assert out["stat_type"] == "Hits"
    assert out["line"] == 1.5
    assert out["odds_type"] == "goblin"


def test_adapt_defaults_odds_type_standard():
    raw = {"player_name": "X", "stat_type": "Hits", "line": 1.5}
    assert ppa._adapt_item(raw)["odds_type"] == "standard"


def test_adapt_drops_missing_required():
    assert ppa._adapt_item({"player_name": "X", "stat_type": "Hits"}) is None   # no line
    assert ppa._adapt_item({"line": 1.5, "stat_type": "Hits"}) is None          # no player
    assert ppa._adapt_item({"player_name": "X", "line": 1.5}) is None           # no stat


def test_adapt_drops_non_mlb_when_league_present():
    raw = {"player_name": "X", "stat_type": "Points", "line": 20.5, "league": "NBA"}
    assert ppa._adapt_item(raw) is None


def test_adapt_keeps_when_no_league_field():
    raw = {"player_name": "X", "stat_type": "Hits", "line": 1.5}
    assert ppa._adapt_item(raw) is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_apify.py -v`
Expected: FAIL — module/`_adapt_item` not found.

- [ ] **Step 3: Write minimal implementation**

```python
# rambo-backend/ingestion/prizepicks_apify_client.py
"""Paid PrizePicks fallback via a configurable Apify actor. Runs the actor
through the spend-guarded run_actor, adapts each item to the free public-API
client's flat shape, and returns a RunResult tagged actor_id="prizepicks" so the
existing map_prizepicks normalizer handles it. Never raises — 0 items on error."""
from __future__ import annotations

import logging
from typing import Optional

from config import prizepicks as cfg
from ingestion.apify_client_wrapper import RunResult

logger = logging.getLogger("rambo.ingestion.prizepicks_apify")

_MLB = {"mlb", "baseball", "baseball_mlb"}


def _first(raw: dict, *names: str):
    for n in names:
        if n in raw and raw[n] is not None:
            return raw[n]
    return None


def _adapt_item(raw: dict) -> Optional[dict]:
    """Map a raw actor item to the free client's flat shape. None if a required
    field (player_name/line/stat_type) is missing or a present league is non-MLB."""
    league = _first(raw, "league", "sport")
    if league is not None and str(league).lower() not in _MLB:
        return None
    player = _first(raw, "player_name", "playerName", "name", "player")
    stat = _first(raw, "stat_type", "statType", "stat", "market")
    line_raw = _first(raw, "line", "line_score", "lineScore", "value", "points")
    if player is None or stat is None or line_raw is None:
        return None
    try:
        line = float(line_raw)
    except (ValueError, TypeError):
        return None
    return {
        "projection_id": _first(raw, "id", "projection_id", "projectionId"),
        "player_name": player,
        "team": _first(raw, "team", "team_abbreviation", "teamName"),
        "position": _first(raw, "position", "pos"),
        "stat_type": stat,
        "line": line,
        "odds_type": _first(raw, "odds_type", "oddsType", "tier") or "standard",
        "start_time": _first(raw, "start_time", "startTime", "start", "game_time"),
        "game_id": _first(raw, "game_id", "gameId", "game"),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_apify.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/ingestion/prizepicks_apify_client.py rambo-backend/tests/test_prizepicks_apify.py
git commit -m "$(cat <<'EOF'
feat(betting): defensive adapter for paid PrizePicks actor items

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `fetch_mlb_props_paid` (spend-guarded run + never-raise)

**Files:**
- Modify: `rambo-backend/ingestion/prizepicks_apify_client.py`
- Test: `rambo-backend/tests/test_prizepicks_apify.py` (append)

**Interfaces:**
- Consumes:
  - `cfg.paid_actor_config()`, `cfg.paid_actor_input()` (Task 1).
  - `_adapt_item` (Task 2).
  - `run_actor(cfg, run_input, *, client=None) -> RunResult` and `RunResult(actor_id, run_id, dataset_id, items, item_count, estimated_cost_usd)` from `apify_client_wrapper`. `run_actor` raises `ApifyIngestError` on spend-guard breach or missing token.
- Produces:
  - `fetch_mlb_props_paid(*, client=None) -> RunResult` — `actor_id="prizepicks"`. Returns an empty `RunResult` when `paid_actor_config()` is `None` OR on any exception. Otherwise runs the actor, adapts items (dropping `None`), and returns them.

- [ ] **Step 1: Write the failing test (append)**

```python
from ingestion.apify_client_wrapper import RunResult, ApifyIngestError


def test_fetch_paid_disabled_when_no_actor(monkeypatch):
    monkeypatch.setattr(ppa.cfg, "paid_actor_config", lambda: None)
    res = ppa.fetch_mlb_props_paid()
    assert res.item_count == 0
    assert res.actor_id == "prizepicks"


def test_fetch_paid_adapts_and_tags_actor(monkeypatch):
    from ingestion.apify_client_wrapper import ActorConfig
    monkeypatch.setattr(ppa.cfg, "paid_actor_config",
                        lambda: ActorConfig("u/a", max_items=10, price_per_1k=0.1))
    monkeypatch.setattr(ppa.cfg, "paid_actor_input", lambda: {"league": "MLB"})
    raw = [{"id": "p1", "player_name": "Aaron Judge", "stat_type": "Home Runs",
            "line": 0.5, "odds_type": "standard"},
           {"id": "bad", "stat_type": "Hits"}]                      # dropped: no line
    monkeypatch.setattr(ppa, "run_actor",
                        lambda c, i, **k: RunResult("u/a", "r1", "d1", raw, 2, 0.02))
    res = ppa.fetch_mlb_props_paid()
    assert res.actor_id == "prizepicks"       # routes to map_prizepicks
    assert res.item_count == 1                 # malformed dropped
    assert res.items[0]["player_name"] == "Aaron Judge"
    assert res.estimated_cost_usd == 0.02


def test_fetch_paid_never_raises_on_run_actor_error(monkeypatch):
    from ingestion.apify_client_wrapper import ActorConfig
    monkeypatch.setattr(ppa.cfg, "paid_actor_config",
                        lambda: ActorConfig("u/a", max_items=10, price_per_1k=0.1))
    def _boom(c, i, **k):
        raise ApifyIngestError("worst-case exceeds max_cost_usd. Refusing run.")
    monkeypatch.setattr(ppa, "run_actor", _boom)
    res = ppa.fetch_mlb_props_paid()
    assert res.item_count == 0                 # spend-guard breach -> 0, no raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_apify.py -v`
Expected: FAIL — no attribute `fetch_mlb_props_paid` / `run_actor` not imported.

- [ ] **Step 3: Write minimal implementation (append to prizepicks_apify_client.py)**

Add `run_actor` to the imports and append the function:

```python
from ingestion.apify_client_wrapper import RunResult, run_actor   # update existing import line


def _empty() -> RunResult:
    rid = f"{cfg.SOURCE_ID}:paid:empty"
    return RunResult(actor_id=cfg.SOURCE_ID, run_id=rid, dataset_id=rid,
                     items=[], item_count=0, estimated_cost_usd=0.0)


def fetch_mlb_props_paid(*, client=None) -> RunResult:
    """Run the env-configured paid PrizePicks actor, adapt items to the free
    shape, tag actor_id='prizepicks' for map_prizepicks. 0 items if disabled or
    on any error (never raises)."""
    ac = cfg.paid_actor_config()
    if ac is None:
        return _empty()
    try:
        run = run_actor(ac, cfg.paid_actor_input(), client=client)
        items = [a for a in (_adapt_item(r) for r in run.items) if a is not None]
        return RunResult(actor_id=cfg.SOURCE_ID, run_id=run.run_id,
                         dataset_id=run.dataset_id, items=items,
                         item_count=len(items),
                         estimated_cost_usd=run.estimated_cost_usd)
    except Exception:
        logger.exception("prizepicks paid fallback failed")
        return _empty()
```

Note: `cfg.SOURCE_ID == "prizepicks"` (existing constant in `config/prizepicks.py`), which is why the result routes to `map_prizepicks`. Keep the existing `from ingestion.apify_client_wrapper import RunResult` line consistent (merge `run_actor` into it; do not duplicate the import).

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_apify.py -v`
Expected: PASS (9 tests total).

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/ingestion/prizepicks_apify_client.py rambo-backend/tests/test_prizepicks_apify.py
git commit -m "$(cat <<'EOF'
feat(betting): fetch_mlb_props_paid — spend-guarded run + never-raise

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Source wiring + normalizer flow-through

**Files:**
- Modify: `rambo-backend/ingestion/sources.py` (add `prizepicks_paid` dispatch + `OTHER_SOURCES`)
- Test: `rambo-backend/tests/test_prizepicks_apify.py` (append)

**Interfaces:**
- Consumes: `fetch_mlb_props_paid` (Task 3); `map_prizepicks` (existing, in `normalize.py`).
- Produces: a `"prizepicks_paid"` source usable via `pull_source(conn, "prizepicks_paid", {})`. Adapted standard items land in `prop_lines` (book=`prizepicks`); demon/goblin still skipped.

- [ ] **Step 1: Write the failing test (append)**

This test exercises the adapter→normalizer contract directly (no live actor): adapt an item, then run it through `map_prizepicks` exactly as `land_raw`→normalize would.

```python
import sqlite3
from db.migrate import get_connection, apply_migrations
from ingestion.normalize import map_prizepicks


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def test_adapted_standard_item_lands_via_map_prizepicks(tmp_path):
    conn = _conn(tmp_path)
    adapted = ppa._adapt_item({"id": "p1", "player_name": "Aaron Judge",
                               "stat_type": "Home Runs", "line": 0.5,
                               "odds_type": "standard",
                               "start_time": "2026-06-29T19:00:00-04:00"})
    assert map_prizepicks(conn, adapted, "2026-06-29T18:00:00Z") is True
    row = conn.execute("SELECT book, market, line FROM prop_lines").fetchone()
    assert row["book"] == "prizepicks" and row["market"] == "HR" and row["line"] == 0.5


def test_adapted_demon_item_still_skipped(tmp_path):
    conn = _conn(tmp_path)
    adapted = ppa._adapt_item({"id": "p2", "player_name": "X",
                               "stat_type": "Home Runs", "line": 1.5,
                               "odds_type": "demon"})
    map_prizepicks(conn, adapted, "2026-06-29T18:00:00Z")
    assert conn.execute("SELECT COUNT(*) c FROM prop_lines").fetchone()["c"] == 0
```

- [ ] **Step 2: Run test to verify it fails (or confirm the wiring need)**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_apify.py -k adapted -v`
Expected: PASS already (the adapter + existing `map_prizepicks` cover this). If it passes, the contract holds; proceed to wire the source so `pull_source` can reach it.

- [ ] **Step 3: Wire the source in `sources.py`**

In `ingestion/sources.py`, add to the `OTHER_SOURCES` set (line ~27): add `"prizepicks_paid"`. Then in the free-path dispatch chain, right after the `elif source == "prizepicks":` block, add:

```python
    elif source == "prizepicks_paid":
        from ingestion import prizepicks_apify_client as ppa
        run = ppa.fetch_mlb_props_paid()
```

(The shared tail `return _summary(run, land_raw(conn, run))` already handles it.)

- [ ] **Step 4: Verify wiring + tests pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_apify.py -v`
Then confirm the source is recognized:
`./.venv/Scripts/python.exe -c "from ingestion.sources import OTHER_SOURCES; print('prizepicks_paid' in OTHER_SOURCES)"`
Expected: tests PASS; print `True`.

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/ingestion/sources.py rambo-backend/tests/test_prizepicks_apify.py
git commit -m "$(cat <<'EOF'
feat(betting): wire prizepicks_paid source; verify normalizer flow-through

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Auto-fallback in prep

**Files:**
- Modify: `rambo-backend/ingestion/prep.py:70-77`
- Test: `rambo-backend/tests/test_prizepicks_prep_fallback.py`

**Interfaces:**
- Consumes: `pull_source` (existing), `cfg.paid_actor_config` (Task 1), `prizepicks_paid` source (Task 4).
- Produces: prep tries `prizepicks_paid` only when the free pull is 0/failed AND an actor is configured; sets `summary["props_source"]` to `"free"`, `"paid"`, or `"none"`.

- [ ] **Step 1: Write the failing test**

This test calls the fallback decision in isolation by monkeypatching `pull_source` and `paid_actor_config`. To make the branch independently testable, factor the fallback into a helper `_pull_props_with_fallback(conn, summary)` in `prep.py` and test that.

```python
# rambo-backend/tests/test_prizepicks_prep_fallback.py
from ingestion import prep


def test_no_fallback_when_free_has_props(monkeypatch):
    calls = []
    def fake_pull(conn, source, params=None):
        calls.append(source)
        return {"items": 12 if source == "prizepicks" else 0}
    monkeypatch.setattr(prep, "pull_source", fake_pull)
    summary = {}
    prep._pull_props_with_fallback(None, summary)
    assert summary["props"] == 12 and summary["props_source"] == "free"
    assert "prizepicks_paid" not in calls


def test_fallback_runs_when_free_zero_and_actor_configured(monkeypatch):
    calls = []
    def fake_pull(conn, source, params=None):
        calls.append(source)
        return {"items": 0 if source == "prizepicks" else 7}
    monkeypatch.setattr(prep, "pull_source", fake_pull)
    monkeypatch.setattr(prep, "paid_actor_config", lambda: object())  # configured
    summary = {}
    prep._pull_props_with_fallback(None, summary)
    assert "prizepicks_paid" in calls
    assert summary["props"] == 7 and summary["props_source"] == "paid"


def test_no_fallback_when_actor_unconfigured(monkeypatch):
    calls = []
    def fake_pull(conn, source, params=None):
        calls.append(source)
        return {"items": 0}
    monkeypatch.setattr(prep, "pull_source", fake_pull)
    monkeypatch.setattr(prep, "paid_actor_config", lambda: None)      # disabled
    summary = {}
    prep._pull_props_with_fallback(None, summary)
    assert "prizepicks_paid" not in calls
    assert summary["props"] == 0 and summary["props_source"] == "none"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_prep_fallback.py -v`
Expected: FAIL — no attribute `_pull_props_with_fallback` / `paid_actor_config` not imported in prep.

- [ ] **Step 3: Write minimal implementation**

In `ingestion/prep.py`, add the import near the top: `from config.prizepicks import paid_actor_config`. Add the helper:

```python
def _pull_props_with_fallback(conn, summary: dict) -> None:
    """Free PrizePicks pull; auto-fall back to the paid Apify actor when free is
    0/failed and an actor is configured. Records summary['props_source']."""
    try:
        summary["props"] = pull_source(conn, "prizepicks", {})["items"]
    except Exception as exc:
        logger.warning("PrizePicks props pull failed: %s", exc)
        summary["props"] = 0
    if summary["props"]:
        summary["props_source"] = "free"
        return
    if paid_actor_config() is not None:
        logger.warning("PrizePicks free pull empty — trying paid Apify fallback.")
        try:
            summary["props"] = pull_source(conn, "prizepicks_paid", {})["items"]
        except Exception as exc:
            logger.warning("PrizePicks paid fallback failed: %s", exc)
        summary["props_source"] = "paid" if summary["props"] else "none"
    else:
        summary["props_source"] = "none"
    if not summary["props"]:
        logger.warning("PrizePicks returned 0 — boards (HR/SO/TB/H/HRR/SB) will be "
                       "stale or empty.")
```

Then replace the old lines 70-77 block (the `try: summary["props"] = pull_source(...)` through the `if not summary["props"]: logger.warning(...)`) with a single call:

```python
        _pull_props_with_fallback(conn, summary)
```

(Keep the surrounding `if`/indentation that guards the props pull. The replaced block is only the free-pull + 0-warning lines.)

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prizepicks_prep_fallback.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/ingestion/prep.py rambo-backend/tests/test_prizepicks_prep_fallback.py
git commit -m "$(cat <<'EOF'
feat(betting): auto-fallback to paid PrizePicks actor when free pull empty

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Full-suite regression + finish

**Files:** none (verification only).

- [ ] **Step 1: Run the whole suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: all prior tests still pass (647 baseline on `main` + the new PrizePicks-paid tests). If any pre-existing test fails, investigate before proceeding — do not edit unrelated tests to make them pass.

- [ ] **Step 2: Import-sanity the new module**

Run: `./.venv/Scripts/python.exe -c "import ingestion.prizepicks_apify_client, ingestion.prep, ingestion.sources; print('ok')"`
Expected: prints `ok` (no import error / cycle).

- [ ] **Step 3: Confirm clean tree + push branch**

```bash
git status -s
git push -u origin feat/prizepicks-paid-fallback
```

- [ ] **Step 4: Open the PR**

```bash
gh pr create --base main --head feat/prizepicks-paid-fallback --title "PrizePicks paid Apify fallback" --body "$(cat <<'EOF'
Auto-fall back to a configurable, cost-capped Apify actor when the free public PrizePicks API fails or returns 0 props.

- Env-configured actor (`PRIZEPICKS_APIFY_ACTOR`); fallback disabled cleanly when unset
- Defensive adapter maps actor field aliases -> the free client's item shape; feeds the existing `map_prizepicks` (actor_id="prizepicks"), standard-tier filter intact
- Spend-guarded via existing `run_actor`; never-raise, drops malformed/non-MLB items
- prep auto-fallback fires only when free is 0/failed; logs `props_source`

Data-only (Sentinel boundary). Demon/goblin tiers are the next sub-project.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Notes for the implementer

- `cfg.SOURCE_ID` is `"prizepicks"` — the paid client deliberately reuses it as the `RunResult.actor_id` so the normalizer dispatch routes paid items to `map_prizepicks` with no normalizer change.
- The paid path is intentionally NOT registered in `ACTORS`/`APIFY_SOURCES` (those land raw without the adapter). The client owns the spend-guarded run + adaptation and returns a free-style `RunResult`, landed via `land_raw`.
- This plan does NOT touch demon/goblin handling. The standard-tier filter in `map_prizepicks` stays; Task 4's `test_adapted_demon_item_still_skipped` pins that.
- No live Apify call is made in tests — `run_actor` is always monkeypatched.
