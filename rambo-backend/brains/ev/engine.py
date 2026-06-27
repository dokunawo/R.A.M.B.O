from __future__ import annotations
import os
from typing import Callable, Optional
from brains.ev.market import REGISTRY
from brains.ev.explainer import explain
from brains.ev.types import Pick

DB_PATH = os.environ.get("RAMBO_DB_PATH", "data/mlb_ingest.db")


def daily_edge(date: str, market: str = "hr", repo=None,
               threshold: float = 0.0,
               complete: Optional[Callable[[str], str]] = None) -> list[Pick]:
    model = REGISTRY[market]                      # KeyError on unknown market
    own_conn = None
    if repo is None:
        from db.migrate import get_connection
        from repositories.mlb_repo import MlbRepo
        own_conn = get_connection(DB_PATH)
        repo = MlbRepo(own_conn)
    try:
        picks = [pk for pk in model.raw_picks(repo, date) if pk.edge > threshold]
        if market == "ml":
            picks.sort(key=lambda pk: (pk.game_datetime or "~", pk.team))  # "~" sorts after any ISO datetime, so games with no start time go last
        else:
            picks.sort(key=lambda pk: pk.edge, reverse=True)
        explain(picks, market, complete=complete)
        return picks
    finally:
        if own_conn is not None:
            own_conn.close()
