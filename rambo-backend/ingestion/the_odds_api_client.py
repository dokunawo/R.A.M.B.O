"""The Odds API client — one GET returns every MLB game + each book's moneyline.
Returns the same `RunResult` shape as the other ingestion clients so raw_store lands
it uniformly. Each event is one raw item (the normalizer expands it to odds_lines)."""
from __future__ import annotations

import datetime as _dt
import logging
from typing import Optional

import httpx

from config import the_odds_api as cfg
from ingestion.apify_client_wrapper import RunResult

logger = logging.getLogger("rambo.ingestion.the_odds_api")
DEFAULT_TIMEOUT = 20.0


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def fetch_moneyline(date: Optional[str] = None, *,
                    client: Optional[httpx.Client] = None) -> RunResult:
    """Pull current MLB moneylines (all games, all US books). `date` is accepted for
    signature parity but filtering happens at match time (events are upcoming)."""
    key = cfg.api_key()
    if not key:
        raise RuntimeError("THE_ODDS_API_KEY not set in .env")
    own = client is None
    client = client or httpx.Client(timeout=DEFAULT_TIMEOUT)
    try:
        url = f"{cfg.BASE}/sports/{cfg.SPORT}/odds"
        params = {"apiKey": key, "regions": cfg.REGIONS, "markets": cfg.MARKETS,
                  "oddsFormat": cfg.ODDS_FORMAT}
        resp = client.get(url, params=params)
        resp.raise_for_status()
        events = resp.json() or []
        captured = _now_iso()
        for e in events:
            e["_captured_at"] = captured
        remaining = resp.headers.get("x-requests-remaining")
        logger.info("the-odds-api: %d events (requests remaining: %s)", len(events), remaining)
        run_id = f"the-odds-api:{captured}"
        return RunResult(actor_id=cfg.SOURCE_ID, run_id=run_id, dataset_id=run_id,
                         items=events, item_count=len(events), estimated_cost_usd=0.0)
    finally:
        if own:
            client.close()
