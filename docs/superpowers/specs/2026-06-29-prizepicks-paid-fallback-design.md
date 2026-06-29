# PrizePicks Paid Apify Fallback — Design

**Date:** 2026-06-29
**Status:** Approved (design)
**Thread:** MLB betting edge engine ("Chances Make Champions") — PrizePicks data reliability
**Sub-project:** B of 2 (A = demon/goblin special tiers, brainstormed next)

## Problem

PrizePicks props come from the free, direct public API (`api.prizepicks.com`,
no auth). When that endpoint is blocked, rate-limited, or down, every
PrizePicks board (HR/SO/TB/H/H+R+RBI/SB) goes stale or empty — the same way the
DK Pick6 Apify actor died on 06/27. There is no backup data path.

## Goal

When the free public PrizePicks pull fails or returns 0 props, automatically
pull the same data via a configurable, cost-capped Apify actor, adapt it to the
existing item shape, and run it through the existing normalizer — so boards
recover without code changes when the free endpoint is unavailable.

## Non-Goals

- No demon/goblin special tiers (sub-project A). The standard-tier filter in
  `map_prizepicks` stays; the paid path reuses that normalizer unchanged.
- No bet placement (Sentinel boundary).
- No hard-pinned actor id — actors die; the actor is configured via env.

## Decisions

- **Relationship:** free public API stays **primary**; paid actor is an
  **auto-fallback**, triggered only when the free pull fails or returns 0.
- **Actor:** **configurable via env var** (`PRIZEPICKS_APIFY_ACTOR`), with a
  **defensive adapter** that maps common field-name aliases — not tailored to
  one actor's schema. If unset, fallback is disabled (free behavior unchanged).

## Architecture

### 1. Config — `config/prizepicks.py` (+ `config/apify.py`)

Add a PrizePicks Apify actor config sourced from env (never billed by these —
they only feed the pre-flight spend guard and logging):

- `PRIZEPICKS_APIFY_ACTOR` — Apify actor id. **No working default**; when unset,
  `paid_actor_config()` returns `None` and the fallback is disabled.
- `PRIZEPICKS_APIFY_PRICE_PER_1K` — default `0.10` (estimate; verify on Store).
- `PRIZEPICKS_APIFY_MAX_COST_USD` — default `2.00` (pre-flight refusal ceiling).
- `PRIZEPICKS_APIFY_MAX_ITEMS` — default `2000`.
- `PRIZEPICKS_APIFY_INPUT` — JSON string for the actor's run input; default
  `{"league": "MLB"}`. Parsed defensively (bad JSON → default + warning).

Expose `paid_actor_config() -> ActorConfig | None` returning an `ActorConfig`
(from `ingestion/apify_client_wrapper.py`) when the actor id is set, else `None`.

### 2. Client — `ingestion/prizepicks_apify_client.py`

`fetch_mlb_props_paid(*, client=None) -> RunResult`:

1. `cfg = paid_actor_config()`; if `None`, return an empty `RunResult`
   (`actor_id="prizepicks"`, 0 items, cost 0) — caller treats as "no fallback".
2. `run = run_actor(cfg, run_input)` — the wrapper enforces the spend guard
   (refuses if worst-case > `max_cost_usd`) and caps `maxItems`.
3. Adapt each raw item via `_adapt_item` (below); drop items missing
   player/line/stat.
4. Return `RunResult(actor_id="prizepicks", run_id=…, dataset_id=…,
   items=adapted, item_count=len(adapted), estimated_cost_usd=run.cost)`.
   `actor_id="prizepicks"` routes the landed items to the existing
   `map_prizepicks` normalizer.
5. Never raise — on any exception, log and return the empty `RunResult` (mirrors
   the free client's never-raise contract).

`_adapt_item(raw: dict) -> dict | None` maps to the free client's flat shape:

```
projection_id <- id | projection_id | projectionId
player_name   <- player_name | playerName | name | player
team          <- team | team_abbreviation | teamName
position      <- position | pos
stat_type     <- stat_type | statType | stat | market
line          <- line | line_score | lineScore | value | points     (float)
odds_type     <- odds_type | oddsType | tier            (default "standard")
start_time    <- start_time | startTime | start | game_time
game_id       <- game_id | gameId | game
```

Return `None` if `player_name`, `line`, or `stat_type` is missing/unparseable.
Filter to MLB when the actor exposes a league field (`league`/`sport` not in
{MLB, baseball, baseball_mlb} → drop); items with no league field are kept
(the actor input already scoped MLB).

### 3. Source wiring — `ingestion/sources.py`

Add to the free-path dispatch chain:

```python
elif source == "prizepicks_paid":
    from ingestion import prizepicks_apify_client as ppa
    run = ppa.fetch_mlb_props_paid()
```

`return _summary(run, land_raw(conn, run))` (same tail as `prizepicks`). Add
`"prizepicks_paid"` to `OTHER_SOURCES`. It is NOT added to `ACTORS`/
`APIFY_SOURCES` (those land raw without the adapter); the client owns the
spend-guarded run + adaptation and emits a free-style `RunResult`.

### 4. Auto-fallback — `ingestion/prep.py` (lines 70-77)

Replace the 0-props warning block:

```python
try:
    summary["props"] = pull_source(conn, "prizepicks", {})["items"]
except Exception as exc:
    logger.warning("PrizePicks props pull failed: %s", exc)
    summary["props"] = 0
if not summary["props"]:
    from config.prizepicks import paid_actor_config
    if paid_actor_config() is not None:
        logger.warning("PrizePicks free pull empty — trying paid Apify fallback.")
        try:
            summary["props"] = pull_source(conn, "prizepicks_paid", {})["items"]
            summary["props_source"] = "paid" if summary["props"] else "none"
        except Exception as exc:
            logger.warning("PrizePicks paid fallback failed: %s", exc)
    if not summary["props"]:
        logger.warning("PrizePicks returned 0 (free%s) — boards will be stale/empty.",
                       " + paid" if paid_actor_config() is not None else "")
else:
    summary["props_source"] = "free"
```

Fallback failures never abort prep.

### 5. Data flow

```
prep_slate
  └─ pull_source("prizepicks")  ── free public API ── N props?
        ├─ N>0 → land → map_prizepicks → prop_lines   (props_source="free")
        └─ 0/err and actor configured →
             pull_source("prizepicks_paid")
               └─ run_actor (spend-guarded) → _adapt_item* → RunResult(actor_id="prizepicks")
                    → land_raw → map_prizepicks → prop_lines   (props_source="paid")
```

Both sources land items under `actor_id="prizepicks"`, so `map_prizepicks`
handles both with no normalizer change; the standard-tier filter still applies.

## Error handling

- Actor id unset → `paid_actor_config()` is `None` → fallback skipped, logged;
  free behavior unchanged.
- `APIFY_TOKEN` unset → `run_actor`/`get_client` raises; caught by the client's
  never-raise wrapper → empty `RunResult` → prep logs and leaves props at 0.
- Spend-guard breach (worst-case > `max_cost_usd`) → `run_actor` raises
  `ApifyIngestError`; client catches → 0 items (no partial/over-budget run).
- Malformed actor items (missing player/line/stat) → dropped by `_adapt_item`;
  never landed as junk props.
- Bad `PRIZEPICKS_APIFY_INPUT` JSON → default input + warning.

## Testing — `tests/test_prizepicks_apify.py`

Pure-Python with a fake `run_actor` (monkeypatched) and a seeded in-memory DB
(`get_connection` + `apply_migrations`, matching `test_prizepicks_normalize.py`):

1. `_adapt_item` maps a canonical actor item and each key-alias variant to the
   free shape; returns `None` for items missing player/line/stat.
2. `_adapt_item` drops a non-MLB item when a league field is present; keeps an
   item with no league field.
3. `fetch_mlb_props_paid` returns an empty `RunResult` (0 items,
   `actor_id="prizepicks"`) when `paid_actor_config()` is `None`.
4. `fetch_mlb_props_paid` never raises when `run_actor` raises (spend guard or
   token error) — returns 0 items.
5. A landed adapted standard item flows through `map_prizepicks` into
   `prop_lines` (book=`prizepicks`, market mapped); a demon item is still
   skipped (standard-tier filter intact).
6. Fallback logic: a fake `pull_source` returning 0 for `prizepicks` triggers a
   `prizepicks_paid` call; returning >0 does NOT (assert via call capture).

## Conventions

- No new dependencies (reuse `apify_client_wrapper.run_actor`, `ActorConfig`,
  `RunResult`). Pure-Python adapter. Env-driven config like
  `config/the_odds_api.py`.
- Never-raise ingestion contract (matches `prizepicks_client.py`).
- Honest: drop malformed/over-budget rather than fabricate; log which source
  served each slate (`summary["props_source"]`).

## Future (sub-project A, next)

- Demon/goblin tiers: add `odds_type` to `prop_lines` + dedup key, group by
  `group_key`, surface lines + model P(over) per tier (no entry EV — payout
  multipliers aren't exposed by the API).
