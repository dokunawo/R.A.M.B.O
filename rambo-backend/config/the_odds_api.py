"""The Odds API config — complete, multi-book MLB odds (the source cowork uses, so
the two systems can't disagree on a line). Free tier 500 req/mo; one slate = 1 request.
Key from THE_ODDS_API_KEY (gitignored .env)."""
from __future__ import annotations
import os

BASE = "https://api.the-odds-api.com/v4"
SPORT = "baseball_mlb"
REGIONS = "us"
MARKETS = "h2h"          # moneyline; player props are per-event (Phase 2+)
ODDS_FORMAT = "american"
SOURCE_ID = "the-odds-api:odds"


def api_key() -> str | None:
    return os.environ.get("THE_ODDS_API_KEY")
