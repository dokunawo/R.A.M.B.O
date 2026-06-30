# PrizePicks Demon/Goblin Tier Board — Design

**Date:** 2026-06-29
**Status:** Approved (design)
**Thread:** MLB betting edge engine ("Chances Make Champions") — PrizePicks special tiers
**Sub-project:** A of 2 (B = paid Apify fallback, shipped PR #29)

## Problem

PrizePicks offers three projection tiers per stat — goblin (easier/lower line),
standard, and demon (harder/higher line). RAMBO ingests standard only
(`map_prizepicks` drops everything where `odds_type != "standard"`), so the
goblin/demon alt lines — useful for safer or higher-variance parlay legs — are
invisible. The live API confirms all three tiers share a `group_key` with
descending lines (e.g. Pitches Thrown 82.5 / 92.5 / 102.5).

## Goal

Ingest all three tiers for the 6 mapped markets and surface a per-player line
ladder with our model P(over) at each line, on a dedicated board. Existing
standard boards stay byte-for-byte unchanged.

## Non-Goals

- No entry EV / payout multipliers — PrizePicks does NOT expose tier payout
  values via the projections API; we show P(over) only, never a guessed payout.
- No parlay assembly on tiers (future).
- No bet placement (Sentinel boundary).

## Decisions

- **Surface:** a NEW dedicated board/endpoint; existing standard boards untouched.
- **Tiers:** all three (goblin/standard/demon) per player where available.
- **Markets:** the existing 6 (`STAT_MARKET_MAP`: HR, SO, TB, H, H+R+RBI, SB).

## Architecture

### 1. Storage — `db/migrations/009_prop_odds_type.sql`

Add a tier column to `prop_lines`:

```sql
ALTER TABLE prop_lines ADD COLUMN odds_type TEXT NOT NULL DEFAULT 'standard';
```

`prop_lines.snapshot_key` is a STORED generated column that includes `line`.
**Correction during implementation:** the original assumption that tiers always
carry distinct lines is false — goblin and standard frequently share a line
(e.g. both 0.5 HR), so without `odds_type` in the key the second tier is silently
dropped by `ON CONFLICT DO NOTHING`. Migration `010_prop_snapshot_key_with_odds_type.sql`
therefore rebuilds `prop_lines` (rename → recreate with `odds_type` in the
generated `snapshot_key` → copy data → drop old), since SQLite cannot ALTER a
generated column in place. Data is preserved; migrations are idempotent
(`apply_migrations` records applied filenames).

### 2. Ingestion — `ingestion/normalize.py`

- `map_prizepicks`: remove the `odds_type != "standard"` clause from the guard
  (keep the `stat_type not in STAT_MARKET_MAP` clause). Set
  `odds_type = item.get("odds_type") or "standard"` and pass it to `_insert_prop`.
- `_insert_prop`: add `odds_type` to the INSERT column list and `VALUES`. Default
  to `"standard"` when the key is absent (every existing caller — odds props,
  Pick6, the free/paid PrizePicks paths — keeps working; non-PrizePicks callers
  simply get `"standard"`).

Both the free (`prizepicks_client`) and paid (`prizepicks_apify_client`) paths
route through `map_prizepicks`, so both ingest tiers with no further change.

### 3. Query — `repositories/mlb_repo.py`

`latest_props` gains a keyword param `odds_type: Optional[str] = "standard"`:

- When a string (default `"standard"`): add `AND p.odds_type = ?` to the WHERE,
  and add `odds_type` to the dedup subquery's `GROUP BY` + join so each tier
  dedups independently.
- When `None`: no `odds_type` filter, but `odds_type` is still in the dedup
  `GROUP BY`/join so all three tiers survive (one latest row per tier).

Existing callers pass nothing → default `"standard"` → byte-for-byte unchanged
output. The new tier board passes `odds_type=None`.

### 4. Board — `brains/ev/prizepicks_tiers.py`

`prizepicks_tiers(date, market, repo=None, *, count=11) -> dict`:

- Pull `repo.latest_props(market=market, official_date=date, odds_type=None)`,
  keep `book == "prizepicks"` rows with a resolved `mlb_id` on today's slate
  (`player_game_context` not None) — mirrors `prizepicks_board`.
- Group by `mlb_id`. For each tier row, compute P(over the line) by REUSING
  `brains.ev.prizepicks_board._p_over(repo, date, market, prop)` (same HR /
  count / k models). Build a per-player row:
  `{name, team, opponent, market, tiers: {goblin|standard|demon: {line, model_pct}}}`
  (a tier key is present only when that tier exists for the player).
- Rank rows by the standard tier's `model_pct` (fall back to any present tier
  when standard is absent), trim to `count`.
- Return `{title: "PRIZEPICKS TIERS — <market>", product: "PrizePicks", market,
  count, rows, prompt}`. The CMC prompt lists each player's goblin/standard/demon
  lines + P(over), states goblin = safer/lower line and demon = swing/higher
  line, and that these are probabilities with NO payout/EV (PrizePicks does not
  expose tier multipliers).

### 5. API — `api/betting.py`

```
GET /betting/prizepicks-tiers?market=&date=
```

Returns `prizepicks_tiers(date, market.upper())`. `date` defaults to today.

### 6. Data flow

```
prizepicks projections (3 tiers, shared group_key)
  -> free/paid client -> map_prizepicks (all tiers, odds_type stored) -> prop_lines
                                                                            |
standard boards: latest_props(...)            [odds_type="standard" default] |
tier board: latest_props(..., odds_type=None) [all tiers]  -- group by mlb_id, _p_over per line
   -> /betting/prizepicks-tiers
```

## Error handling

- No tiers for a player → only the present tier keys appear; never fabricate a
  line.
- `_p_over` returns `None` (no usable sample) for a tier → that tier is omitted
  from the player's ladder; player still listed if another tier scores.
- No PrizePicks props / no slate → empty `rows`, graceful prompt.
- Non-PrizePicks callers of `_insert_prop` → `odds_type` defaults `"standard"`.

## Testing

1. **Migration** (`tests/test_prop_odds_type_migration.py`): applying migrations
   to a fresh DB yields a `prop_lines.odds_type` column defaulting to
   `"standard"`; re-applying is a no-op.
2. **Normalizer** (`tests/test_prizepicks_tiers_normalize.py`): a demon and a
   goblin projection now LAND (previously dropped) with the right `odds_type`
   and mapped market; a standard one still lands as `standard`.
3. **Repo** (`tests/test_latest_props_odds_type.py`): with goblin+standard+demon
   rows seeded, `latest_props(...)` (default) returns only standard;
   `latest_props(..., odds_type=None)` returns all three; an existing
   standard-only fixture's result is unchanged (regression).
4. **Board** (`tests/test_prizepicks_tiers_board.py`): a fake repo with a
   player carrying all three tiers yields one row whose `tiers` has
   goblin/standard/demon each with `line` + `model_pct`; ranked output; empty
   data → empty rows; prompt mentions tiers and "no payout"/"not guarantees".

All DB tests use `get_connection` + `apply_migrations(conn, "db/migrations")`
(matching `test_prizepicks_normalize.py`). Board test uses a fake repo +
monkeypatched `_p_over` (no live models needed).

## Conventions

- No new dependencies. Board follows `watch.py`/`prizepicks_board.py` shape
  (`_open(repo)`, dict with title/product/count/rows/prompt). Reuse
  `prizepicks_board._p_over` — no new modeling.
- Honest framing: P(over) per real line; never a guessed payout/EV. Standard
  boards must not regress (pinned by the repo regression test).

## Future

- Tier-aware parlay assembly; payout multipliers if a source for them appears.
