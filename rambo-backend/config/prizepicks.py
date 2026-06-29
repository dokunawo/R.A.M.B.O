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
