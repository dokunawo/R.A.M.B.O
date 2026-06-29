"""Paid PrizePicks fallback via a configurable Apify actor. Runs the actor
through the spend-guarded run_actor, adapts each item to the free public-API
client's flat shape, and returns a RunResult tagged actor_id="prizepicks" so the
existing map_prizepicks normalizer handles it. Never raises — 0 items on error."""
from __future__ import annotations

import logging
from typing import Optional

from config import prizepicks as cfg
from ingestion.apify_client_wrapper import RunResult

logger = logging.getLogger("rambo.ingestion.prizepicks_apify")

_MLB = {"mlb", "baseball", "baseball_mlb"}


def _first(raw: dict, *names: str):
    for n in names:
        if n in raw and raw[n] is not None:
            return raw[n]
    return None


def _adapt_item(raw: dict) -> Optional[dict]:
    """Map a raw actor item to the free client's flat shape. None if a required
    field (player_name/line/stat_type) is missing or a present league is non-MLB."""
    league = _first(raw, "league", "sport")
    if league is not None and str(league).lower() not in _MLB:
        return None
    player = _first(raw, "player_name", "playerName", "name", "player")
    stat = _first(raw, "stat_type", "statType", "stat", "market")
    line_raw = _first(raw, "line", "line_score", "lineScore", "value", "points")
    if player is None or stat is None or line_raw is None:
        return None
    try:
        line = float(line_raw)
    except (ValueError, TypeError):
        return None
    return {
        "projection_id": _first(raw, "id", "projection_id", "projectionId"),
        "player_name": player,
        "team": _first(raw, "team", "team_abbreviation", "teamName"),
        "position": _first(raw, "position", "pos"),
        "stat_type": stat,
        "line": line,
        "odds_type": _first(raw, "odds_type", "oddsType", "tier") or "standard",
        "start_time": _first(raw, "start_time", "startTime", "start", "game_time"),
        "game_id": _first(raw, "game_id", "gameId", "game"),
    }
