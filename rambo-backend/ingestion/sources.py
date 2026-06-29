"""
R.A.M.B.O. MLB Betting Agent — Source dispatcher (Step 5)
ingestion/sources.py

One entry point — pull_source() — that the API and CLI both call. It routes a
source name to either the FREE statsapi client or the PAID Apify wrapper, lands
the result into raw_ingest, and returns a small summary. Normalization runs
separately (normalize_pending) against raw_ingest.

  Free (statsapi, no key):  roster | schedule | stats
  Paid (Apify, spend-capped): odds | props
"""

from __future__ import annotations

import datetime as _dt
import sqlite3
from typing import Any, Optional

from config.apify import ACTORS, DEFAULT_INPUTS
from ingestion import statsapi_client as sapi
from ingestion.raw_store import land_raw, pull_and_land

APIFY_SOURCES = set(ACTORS.keys())                       # {'odds', 'props'}
STATSAPI_SOURCES = {"roster", "schedule", "stats", "team_stats", "recent_stats",
                    "lineups", "weather"}
OTHER_SOURCES = {"odds_api", "odds_props", "statcast", "odds_api_historical", "prizepicks", "prizepicks_paid"}   # The Odds API (ml + props + historical) + Baseball Savant + PrizePicks + PrizePicks Paid
SOURCES = sorted(APIFY_SOURCES | STATSAPI_SOURCES | OTHER_SOURCES)


def _season(params: dict) -> int:
    return int(params.get("season") or _dt.date.today().year)


def _date(params: dict) -> str:
    return params.get("date") or _dt.date.today().isoformat()


def _summary(run, landed: dict[str, int]) -> dict[str, Any]:
    return {
        "actor_id": run.actor_id,
        "run_id": run.run_id,
        "items": run.item_count,
        "estimated_cost_usd": run.estimated_cost_usd,
        **landed,
    }


def pull_source(conn: sqlite3.Connection, source: str,
                params: Optional[dict] = None) -> dict[str, Any]:
    """Pull one source and land it raw. `params` may carry date / season /
    player_id / overrides depending on the source."""
    params = params or {}

    if source in APIFY_SOURCES:
        cfg = ACTORS[source]
        run_input = {**DEFAULT_INPUTS.get(source, {}), **(params.get("overrides") or {})}
        date = params.get("date")
        if source == "odds" and date:                    # odds wants YYYYMMDD
            run_input.setdefault("dates", date.replace("-", ""))
        return pull_and_land(conn, cfg, run_input)        # paid: spend-capped

    if source == "roster":
        run = sapi.fetch_active_players(_season(params))
    elif source == "schedule":
        run = sapi.fetch_schedule(_date(params))
    elif source == "stats":
        pid = params.get("player_id")
        if pid is None:
            raise ValueError("stats source requires player_id")
        group = params.get("group", "hitting")   # "hitting" | "pitching"
        run = sapi.fetch_player_stats(int(pid), _season(params), group=group)
    elif source == "team_stats":
        run = sapi.fetch_team_stats(_season(params))
    elif source == "recent_stats":
        group = params.get("group", "hitting")            # "hitting" | "pitching"
        end = params.get("end_date") or _date(params)
        days = int(params.get("days", 14))                # 15-day window inclusive
        start = params.get("start_date") or (
            _dt.date.fromisoformat(end) - _dt.timedelta(days=days)).isoformat()
        run = sapi.fetch_daterange_stats(start, end, group)
    elif source == "lineups":
        gp = params.get("game_pk")
        if gp is None:
            raise ValueError("lineups source requires game_pk")
        run = sapi.fetch_boxscore(int(gp))
    elif source == "weather":
        gp = params.get("game_pk")
        if gp is None:
            raise ValueError("weather source requires game_pk")
        run = sapi.fetch_live_feed(int(gp))
    elif source == "odds_api":
        from ingestion import the_odds_api_client as toa
        run = toa.fetch_moneyline(params.get("date"))
    elif source == "odds_props":
        from ingestion import the_odds_api_client as toa
        mx = params.get("max_events")
        run = toa.fetch_props(params.get("date"),
                              max_events=int(mx) if mx is not None else None)
    elif source == "odds_api_historical":
        from ingestion import the_odds_api_client as toa
        snap = params.get("snapshot")
        if not snap:
            raise ValueError("odds_api_historical source requires snapshot (ISO 8601)")
        run = toa.fetch_moneyline_historical(snap)
    elif source == "statcast":
        from ingestion import savant_client as sv
        run = sv.fetch_statcast(_season(params))
    elif source == "prizepicks":
        from ingestion import prizepicks_client as pp
        run = pp.fetch_mlb_props()
    elif source == "prizepicks_paid":
        from ingestion import prizepicks_apify_client as ppa
        run = ppa.fetch_mlb_props_paid()
    else:
        raise KeyError(f"unknown source {source!r} (valid: {SOURCES})")

    return _summary(run, land_raw(conn, run))             # free
