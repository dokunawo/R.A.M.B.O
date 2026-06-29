"""Direct PrizePicks public-API client (free, no auth). Pulls MLB projections,
joins each to its new_player from the JSON:API `included`, and emits flat per-prop
items. Never raises — returns 0 items on any error so prep can warn and move on."""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from config import prizepicks as cfg
from ingestion.apify_client_wrapper import RunResult

logger = logging.getLogger("rambo.ingestion.prizepicks")

_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_MAX_PAGES = 10


def fetch_mlb_props(*, client: Optional[httpx.Client] = None) -> RunResult:
    own = client is None
    client = client or httpx.Client(timeout=30)
    items: list[dict] = []
    try:
        url = f"{cfg.BASE}/projections"
        params = {"league_id": cfg.LEAGUE_ID, "per_page": 1000}
        for _ in range(_MAX_PAGES):
            resp = client.get(url, params=params, headers=_HEADERS)
            resp.raise_for_status()
            body = resp.json() or {}
            data = body.get("data") or []
            players = {x["id"]: (x.get("attributes") or {})
                       for x in (body.get("included") or [])
                       if x.get("type") == "new_player"}
            for proj in data:
                attrs = proj.get("attributes") or {}
                rel = (((proj.get("relationships") or {}).get("new_player") or {}).get("data") or {})
                pl = players.get(rel.get("id"), {})
                items.append({
                    "projection_id": proj.get("id"),
                    "player_name": pl.get("name") or pl.get("display_name"),
                    "team": pl.get("team"),
                    "position": pl.get("position"),
                    "stat_type": attrs.get("stat_type"),
                    "line": attrs.get("line_score"),
                    "odds_type": attrs.get("odds_type"),
                    "start_time": attrs.get("start_time"),
                    "game_id": attrs.get("game_id"),
                })
            nxt = ((body.get("links") or {}).get("next"))
            if not nxt:
                break
            url, params = (nxt if nxt.startswith("http") else f"{cfg.BASE}{nxt}"), None
        logger.info("prizepicks: %d projections", len(items))
    except Exception:
        logger.exception("prizepicks fetch failed")
        items = []
    finally:
        if own:
            client.close()
    rid = f"{cfg.SOURCE_ID}:mlb"
    return RunResult(actor_id=cfg.SOURCE_ID, run_id=rid, dataset_id=rid,
                     items=items, item_count=len(items), estimated_cost_usd=0.0)
