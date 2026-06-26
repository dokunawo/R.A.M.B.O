"""
R.A.M.B.O. MLB Betting Agent — Apify Actor Config (Step 1)
config/apify.py

PAID Apify actors ONLY. Per the data-source decision, the free data
(roster / schedule / player stats) comes directly from statsapi.mlb.com
(see config/statsapi.py) — not Apify. The only actors that earn their cost are the
two scraping data MLB does not publish for free:
  - game-line odds            (seemuapps/sports-odds-scraper)
  - DraftKings Pick6 props     (zen-studio/draftkings-pick6-player-props)

`price_per_1k` / `max_cost_usd` only ESTIMATE cost for the pre-flight spend guard
and logging — they never bill. VERIFY each price against the live Apify Store page
before any real pull.

NOTE: `ActorConfig` is defined in ingestion/apify_client_wrapper.py (Step 2). This
is a forward import — nothing here executes until that module lands.
"""

from __future__ import annotations

from ingestion.apify_client_wrapper import ActorConfig

# --- Actor registry (paid only) ---------------------------------------------
# max_items:   hard ceiling per run (caps spend).
# price_per_1k: $ per 1,000 results from the Store page — VERIFY before relying on it.
# max_cost_usd: pre-flight guard; a run whose worst case exceeds this is refused.

ODDS = ActorConfig(
    actor_id="seemuapps/sports-odds-scraper",
    max_items=300,            # game lines across the slate + books
    price_per_1k=3.00,        # verified 2026-06-26: $3.00 / 1k odds rows (pay-per-event)
    max_cost_usd=2.50,
    run_timeout_secs=180,
)

PROPS = ActorConfig(
    actor_id="zen-studio/draftkings-pick6-player-props",
    max_items=500,            # props fan out fast — the biggest pull
    price_per_1k=0.03,        # verified 2026-06-26: ~$0.03 / 1k props (pay-per-event)
    max_cost_usd=4.00,
    run_timeout_secs=240,
)

ACTORS: dict[str, ActorConfig] = {
    "odds": ODDS,
    "props": PROPS,
}

# --- Default run inputs -----------------------------------------------------
# Merged with runtime overrides (date, ...) before run_actor(). maxItems is clamped
# by the wrapper regardless. VERIFY these keys on each actor's Input tab.

DEFAULT_INPUTS: dict[str, dict] = {
    # Verified 2026-06-26 against the actor's input schema: `leagues` is a required
    # array (`["mlb"]`); `dates` is YYYYMMDD or a YYYYMMDD-YYYYMMDD range (empty =
    # today); `oddsFormat` defaults to american (both american+decimal always
    # returned). It returns all markets — h2h/spreads/totals — via each row's
    # marketKey. Add `"dates": "YYYYMMDD"` at call time to pull a specific day.
    "odds": {"leagues": ["mlb"]},
    # The actor scrapes all sports (free tier caps at 50 props/run); a per-sport
    # input filter wasn't honored by `league`. TODO: confirm the MLB filter key on
    # the Input tab. For now normalize filters to league == "MLB".
    "props": {},
}
