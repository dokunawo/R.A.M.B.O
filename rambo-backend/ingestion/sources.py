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
STATSAPI_SOURCES = {"roster", "schedule", "stats"}
SOURCES = sorted(APIFY_SOURCES | STATSAPI_SOURCES)


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
    else:
        raise KeyError(f"unknown source {source!r} (valid: {SOURCES})")

    return _summary(run, land_raw(conn, run))             # free
