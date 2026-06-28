"""The Odds API config — complete, multi-book MLB odds (the source cowork uses, so
the two systems can't disagree on a line). Free tier 500 req/mo; one slate = 1 request.
Key from THE_ODDS_API_KEY (gitignored .env)."""
from __future__ import annotations
import os

BASE = "https://api.the-odds-api.com/v4"
SPORT = "baseball_mlb"
REGIONS = "us"
MARKETS = "h2h"          # moneyline; player props are per-event (below)
ODDS_FORMAT = "american"
SOURCE_ID = "the-odds-api:odds"

# ── Player props (per-event endpoint) ────────────────────────────────────────
# Props are only available per event: list events (FREE), then each event's odds
# costs (markets × regions). Cost = events × len(prop_markets) for the us region.
# Keep the market set small to protect quota; override via RAMBO_PROP_MARKETS.
PROPS_SOURCE_ID = "the-odds-api:props"
_DEFAULT_PROP_MARKETS = "batter_home_runs,pitcher_strikeouts,batter_total_bases,batter_hits"

# The Odds API market key -> our EV/Pick6 taxonomy. Only mapped markets are kept.
PROP_MARKET_MAP = {
    "batter_home_runs": "HR",
    "pitcher_strikeouts": "SO",
    "batter_total_bases": "TB",
    "batter_hits": "H",
}


def prop_markets() -> list[str]:
    return [m.strip() for m in
            os.environ.get("RAMBO_PROP_MARKETS", _DEFAULT_PROP_MARKETS).split(",")
            if m.strip()]


def api_key() -> str | None:
    return os.environ.get("THE_ODDS_API_KEY")
