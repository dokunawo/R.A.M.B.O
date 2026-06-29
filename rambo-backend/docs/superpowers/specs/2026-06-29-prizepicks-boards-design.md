# PrizePicks Boards + Power/Flex Parlay EV — Design

**Date:** 2026-06-29
**Status:** Approved (design), pending implementation plan
**Thread:** Replace the dead DK Pick6 feed with a direct **PrizePicks** ingestion, restore the 6 player-prop boards as **model-confidence** boards, and add a **Power/Flex entry-EV / parlay builder**.

## 1. Context

The DK Pick6 Apify actor died (returns 0). PrizePicks is the chosen replacement. The third-party PrizePicks Apify actor is also limited (returns 10 junk props), but **PrizePicks' own public API is wide open** — `GET https://api.prizepicks.com/projections?league_id=2` returns ~8,000 MLB projections, free, no auth, no Cloudflare block. We ingest that directly.

PrizePicks has **no per-prop multiplier** (unlike Pick6); payouts are **play-level** (Power / Flex by leg count). So the per-prop board ranks by **model probability of clearing the line**, and the betting EV lives in a **parlay builder** over the public Power/Flex payout tables. Both phases ship together. Operator confirmed the 6 markets exist with volume: Home Runs (267), Pitcher Strikeouts (171), Total Bases (1293), Hits (712), Hits+Runs+RBIs (1346), Stolen Bases (244).

## 2. Decisions (settled)

- **Source:** direct PrizePicks public API (free), NOT the Apify actor. Let the $5 day-pass lapse.
- **Markets (standard odds_type only):** `Home Runs→HR`, `Pitcher Strikeouts→SO`, `Total Bases→TB`, `Hits→H`, `Hits+Runs+RBIs→H+R+RBI`, `Stolen Bases→SB`. (demon/goblin alt lines deferred.)
- **Board ranking:** model **P(clear the PrizePicks line)**, pick the model-favored side (over if P≥0.5 else under), rank by confidence. No fake per-prop multiplier/EV.
- **EV:** at the **entry** level via Power/Flex payout tables (parlay builder).
- **Rebrand:** "DK Pick6" → "PrizePicks" across the affected boards/labels; retire the dead Pick6 path.

## 3. Data shape (verified from the live API)

JSON:API. `data[]` = projections; `included[]` = `new_player`, `team`, `game`, `stat_type`, …
- Projection `attributes`: `line_score` (the line), `stat_type` ("Home Runs"…), `odds_type` (`standard`|`demon`|`goblin`), `start_time`, `status`, `game_id`.
- Projection `relationships.new_player.data.id` → `included` `new_player` with `attributes`: `name`, `display_name`, `team`, `team_name`, `position`, `league`.

## 4. Components

### 4.1 Ingestion — `ingestion/prizepicks_client.py`
`fetch_mlb_props(*, client=None) -> RunResult` — GET `{BASE}/projections?league_id=2&per_page=1000` (+ paginate via `links.next` if present), build a `new_player` id→attrs index from `included`, and emit one flat item per projection:
`{projection_id, player_name, team, position, stat_type, line, odds_type, start_time, game_id}`.
Headers: a desktop `User-Agent` + `Accept: application/json`. Returns `RunResult(actor_id="prizepicks", item_count=…, estimated_cost_usd=0.0)`. Best-effort; never raises into prep.

### 4.2 Source + normalize
- `config/prizepicks.py` — `SOURCE_ID = "prizepicks"`, `LEAGUE_ID = 2`, and `STAT_MARKET_MAP = {"Home Runs":"HR","Pitcher Strikeouts":"SO","Total Bases":"TB","Hits":"H","Hits+Runs+RBIs":"H+R+RBI","Stolen Bases":"SB"}`.
- `ingestion/sources.py` — route `"prizepicks"` → `prizepicks_client.fetch_mlb_props`.
- `ingestion/normalize.py` — `map_prizepicks(conn, item, scraped_at)`: keep only items whose `stat_type` is in `STAT_MARKET_MAP` **and** `odds_type=="standard"`; insert via the existing `_insert_prop` with `book="prizepicks"`, `market=<mapped>`, `line=<line>`, `over_price=NULL`, `under_price=NULL`, `multiplier=NULL`, `player_name_raw=<player_name>`, `captured_at=<scraped_at>`. Register `SOURCE_ID` in `DISPATCH`.
- **game_pk resolution:** the existing `IdResolver` links `player_name_raw → mlb_id`; extend the prep step so PrizePicks props also get `game_pk` set from the player's game on `start_time`'s date (so they survive the slate date-filter shipped in PR #27). Reuse `player_game_context`-style logic; leave `game_pk` NULL if the player isn't on the slate (board still resolves at read time).

### 4.3 Probability boards — `brains/ev/prizepicks_board.py`
`prizepicks_board(date, market, repo=None, *, count=11) -> dict`. For each PrizePicks prop of `market` on `date` (player on the slate via `player_game_context`):
- Compute **model P over the PrizePicks `line`** reusing existing models:
  - HR: `hr_probability(hr_rate, park)` (line ~0.5 → P(1+)). Build via `build_hr_features_core`.
  - SO (pitcher K): the binomial K ladder from `k_model.k_projection` → `P(line+ K)`.
  - TB / H / H+R+RBI / SB: `count_model.poisson_prob_over(per_game_mean, line)` via `build_count_features_core` with the right `stat_keys`.
- `p_over = P(X > line)`; pick side: `over` if `p_over ≥ 0.5` else `under` (`p = max(p_over, 1−p_over)`).
- Rank by `p` desc; emit rows `{rank, name, team, opponent, stat, line, side, model_pct, support}`. Returns `{title, product:"PrizePicks", market, count, rows, prompt}` (poster prompt like the existing watch boards).

### 4.4 Power/Flex parlay EV — `brains/ev/prizepicks_parlay.py`
- `POWER` and `FLEX` payout tables (config, verified against PrizePicks' published values), e.g. Power `{2:3.0, 3:5.0, 4:10.0, 5:20.0, 6:37.5}`; Flex partial tables per leg count (`3:{3:2.25,2:1.25}, 4:{4:5,3:1.5}, 5:{5:10,4:2,3:0.4}, 6:{6:25,5:2,4:0.4}`).
- `hit_distribution(probs: list[float]) -> list[float]` — Poisson-binomial P(exactly k of N hit) for independent legs (DP, pure Python).
- `entry_ev(probs, play_type) -> dict` — `Σ P(k)·payout(k) − 1` (Power pays only at k==N; Flex per its table). Returns `{combined_all, ev, payout_table}`.
- `suggest_entries(legs, sizes=(2,3,4,5,6)) -> list` — from the board's top legs (each with model `p`), evaluate Power and Flex at each size and return the best +EV entries (or the least-negative, reported honestly).

### 4.5 Surface + rebrand
- API: `GET /betting/prizepicks?market=hr|so|tb|h|hrr|sb&date=…` (board) and `POST /betting/prizepicks/parlay` (body: chosen leg ids or `{auto:true}`) → EV/suggestions.
- `cmc-daily.ps1`: add the PrizePicks boards (tables) + an entry-EV section; warn if PrizePicks pulled 0.
- Rebrand: the betting `PRODUCT` labels / poster banners change "DK Pick6" → "PrizePicks" for these markets; `prep_slate` calls the new `prizepicks` source in place of the dead Apify `props`.

## 5. Data flow

```
api.prizepicks.com/projections?league_id=2
  → prizepicks_client.fetch_mlb_props (flat items)
  → raw_ingest → normalize.map_prizepicks → prop_lines (book=prizepicks, multiplier NULL)
  → IdResolver (player_name→mlb_id, game_pk from slate)
        │
  prizepicks_board(date, market): model P(over line) per leg → ranked board (PrizePicks)
        │  top legs (player, side, model p)
  prizepicks_parlay: Poisson-binomial over chosen legs × Power/Flex tables → entry EV / suggestions
        │
  /betting/prizepicks  ·  /betting/prizepicks/parlay  ·  cmc-daily.ps1
```

## 6. Error handling
- PrizePicks API down / non-200 → `fetch_mlb_props` returns 0 items (never raises); prep logs a warning (the PR #27 "props 0" warning path applies).
- Unmapped `stat_type` / non-standard tier → silently skipped in normalize.
- Player not on the slate / no model sample → board skips that prop (counted).
- Parlay math is pure Python; guard empty/short leg lists.

## 7. Testing
- `test_prizepicks_client.py` — JSON:API join (projection→player via fake response), flat-item shape, pagination handling.
- `test_prizepicks_normalize.py` — only mapped stat_types + standard tier land; book/market/line/multiplier-NULL correct.
- `test_prizepicks_board.py` — per-market P(over line) uses the right model; side selection (over/under); ranking; player-on-slate filter.
- `test_prizepicks_parlay.py` — Poisson-binomial distribution sums to 1 + known small cases; Power EV (k==N only) and Flex EV (partial table) against hand-computed values; suggest picks the higher-EV entry.
- Live gate: pull real PrizePicks, render each board, run a sample parlay, full suite green.

## 8. Honest limitations
- PrizePicks lines are sharp (set near the median projection), so model edges are small; the board surfaces model confidence, not a vig-beating EV. Genuine +EV at the entry level is reported truthfully (often the honest answer is "thin").
- Power/Flex payout tables can vary by region/promo — they're config, to be verified against PrizePicks' current published payouts.
- Independence assumption in the parlay math (legs across different games are ~independent; same-game legs correlate — a known simplification).
- Standard tier only in v1; demon/goblin alt lines (with explicit `adjusted_odds`) are a later add.

## 9. File manifest
| File | Change |
|---|---|
| `config/prizepicks.py` | new — SOURCE_ID, LEAGUE_ID, STAT_MARKET_MAP, Power/Flex tables |
| `ingestion/prizepicks_client.py` | new — `fetch_mlb_props` |
| `ingestion/sources.py` | + `"prizepicks"` route |
| `ingestion/normalize.py` | + `map_prizepicks` + DISPATCH entry |
| `ingestion/prep.py` | call `prizepicks` source (replace dead `props`); resolve game_pk for PrizePicks props |
| `brains/ev/prizepicks_board.py` | new — model-confidence boards |
| `brains/ev/prizepicks_parlay.py` | new — Poisson-binomial + Power/Flex EV + suggest |
| `api/betting.py` | + `/betting/prizepicks` + `/betting/prizepicks/parlay` |
| `cmc-daily.ps1` | PrizePicks boards + entry-EV section |
| betting `PRODUCT`/poster labels | rebrand DK Pick6 → PrizePicks for these markets |
| `tests/test_prizepicks_*.py` | new (client, normalize, board, parlay) |
