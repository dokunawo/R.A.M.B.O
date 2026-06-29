# Alt-Strikeout Parlay Builder — Design

**Date:** 2026-06-29
**Status:** Approved (design)
**Thread:** MLB betting edge engine ("Chances Make Champions") — alt-K Phase 2

## Problem

RAMBO already ranks probable starters by P(9+ K) with the full P(1+…10+) ladder
(`strikeout_watch`), but nothing joins those model probabilities to real book
odds, and the only parlay builder works on PrizePicks over/under lines — not the
FanDuel-style **alt-strikeout** market where you stack `8+`/`9+`/`10+` legs
across multiple starters. The operator wants to build big FanDuel alt-K parlays
with true EV, not just probabilities.

## Goal

Rank tomorrow's starters by P(8+/9+/10+ K), join the model probabilities to real
FanDuel **and** best-of-book alt-strikeout odds, surface per-threshold EV, and
assemble +EV alt-K parlays (auto-suggested and manually specified).

## Non-Goals

- No bet placement (Sentinel data-only boundary stays intact).
- No new strikeout model — reuse `k_model` verbatim.
- No historical alt-K backfill / CLV in this phase (future).

## Decisions

- **Book scope:** show **FanDuel** price (operator's book) **and** best-of-book
  price per leg, for both EV and line-shopping signal.
- **Parlay mode:** support **both** auto-suggested best 2–6 leg parlays and an
  explicit operator-specified leg list.

## Architecture

### 1. Ingestion — alt-K odds source

The Odds API exposes the `pitcher_strikeouts_alternate` market (alternate
strikeout lines with over/under prices across US books, FanDuel included).

- `config/the_odds_api.py`: add `pitcher_strikeouts_alternate` to the prop
  market set and map it in `PROP_MARKET_MAP` to a **new taxonomy value
  `SO_ALT`**, kept distinct from `SO` (the standard single-line strikeout prop)
  so the two don't collide.
- The existing per-event prop fetch (`fetch_props`) and normalizer
  (`map_props_book`) handle it with no structural change: the normalizer
  already groups outcomes by `(player, line)` and writes one `prop_lines` row per
  line with real `over_price`/`under_price`. Each alt line (5.5, 6.5, … 9.5)
  lands as its own row, one per book. `prop_lines.snapshot_key` already includes
  `line`, so multiple lines per pitcher are distinct rows.
- **Quota:** adds 1 credit × events per slate on The Odds API. Gated behind the
  existing prop-pull path (`/betting/pull-book-props`), never auto-run.

### 2. Brain — `brains/ev/alt_k.py`

For each probable starter (reuse `strikeout_watch`'s starter selection +
`min_starts` gate + `_opp_team_id`), compute the opponent-adjusted
`k_projection`, then for each alt line the book offers compute
`k_model.binom_prob_over(round(BF), k_rate, ceil(line))` = model P(line+).

Join model prob → book odds rows (`SO_ALT`, matched by `mlb_id` + line):
- Per leg, per book: `edge = model_p * american_to_decimal(over_price) - 1`.
- Surface the **FanDuel** price and the **best-of-book** price (highest decimal
  payout) for each (pitcher, threshold).

Output a ranked board: per pitcher, each alt-K threshold with model %, FanDuel
odds + EV, best-book odds + EV + which book. +EV thresholds flagged.

### 3. Parlay assembler (in `alt_k.py`)

Legs are independent (different games), so:
- `combined_p = ∏ model_p`
- `parlay_payout = ∏ american_to_decimal(price)` (decimal)
- `parlay_ev = combined_p * parlay_payout - 1`

`american_to_decimal` already exists in `line_shop.py` — reuse it.

Two entry points:
- **Auto-suggest:** from the best-value leg per pitcher (best-book price),
  evaluate 2–6 leg parlays, return the best per size ranked by EV — same shape as
  the existing `suggest_entries`.
- **Manual:** accept an explicit list of `(mlb_id, threshold)` legs (use the book
  chosen for the board: best-of-book by default, FanDuel when requested) and
  return that parlay's combined_p / payout / EV.

### 4. API (`api/betting.py`)

- `GET /betting/alt-k-board?date=` — ranked starters: per-threshold model %,
  FanDuel + best odds, EV, plus a CMC image prompt (mirrors `strikeout_watch`
  prompt style, with odds + EV added).
- `POST /betting/alt-k/parlay?date=&legs=&book=&sizes=` — `legs` optional
  (manual); when omitted, returns auto-suggestions. `book` ∈ {best, fanduel}.

### 5. Data flow

```
The Odds API (pitcher_strikeouts_alternate)
  -> raw_ingest -> map_props_book -> prop_lines (market=SO_ALT, real prices)
                                                  |
probable_starters + k_model.k_projection ---------+--> alt_k.alt_k_board
                                                          |-> per-threshold model% + FD/best odds + EV
                                                          '-> alt_k.suggest_parlays / parlay_ev
                                                                  -> /betting/alt-k-board, /betting/alt-k/parlay
```

## Error handling

- No alt-K odds rows for a pitcher → board still lists the model ladder with
  odds fields null (probabilities are always useful); EV omitted, never faked.
- No probable starters yet / no slate → empty `rows`, graceful prompt
  ("no probable starters available yet"), matching existing boards.
- Missing FanDuel but other books present → FanDuel fields null, best-of-book
  still populated.
- Manual parlay leg with no matching odds row → that leg returns null EV with a
  reason; parlay EV computed only if all legs priced.

## Testing (TDD)

`tests/test_alt_k.py`, pure-Python with a fake/seeded repo:
- `binom_prob_over` ladder → P(line+) mapping for representative lines.
- per-leg EV sign: model_p high vs. low against a known decimal payout.
- parlay math: combined_p = product, payout = product, EV formula, on a 2- and
  3-leg case with hand-computed expected values.
- best-of-book selection picks the highest decimal payout.
- empty / missing-odds graceful paths (null EV, no exceptions).
- normalizer test: a `pitcher_strikeouts_alternate` event lands multiple
  `SO_ALT` rows (one per line) with correct over/under prices.

## Conventions

- Pure-Python math, no new deps. Reuse `american_to_decimal`,
  `american_to_implied`. SQLite via `MlbRepo`. Board functions follow the
  `watch.py` shape (`_open(repo)`, dict with title/product/count/rows/prompt).
- Honest framing: model probabilities vs. real book prices. Most alt-K overs are
  −EV (books shade strikeout overs); value = finding the rare +EV threshold and
  avoiding traps. The board states this.

## Future (out of scope)

- Historical alt-K snapshots + CLV tracking.
- Correlation modeling (legs treated independent; same-game legs not a concern
  since each pitcher is in a different game).
- Voice surface ("Operator, build me an alt-K parlay").
