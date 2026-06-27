"""Baseball Savant client — one CSV pull = every qualified batter's barrel% +
hard-hit%. Returns the standard RunResult; one item per player."""
from __future__ import annotations

import csv
import datetime as _dt
import io
import logging
from typing import Optional

import httpx

from config import savant as cfg
from ingestion.apify_client_wrapper import RunResult

logger = logging.getLogger("rambo.ingestion.savant")


def _f(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_statcast(year: int, *, client: Optional[httpx.Client] = None) -> RunResult:
    own = client is None
    client = client or httpx.Client(timeout=30.0, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = client.get(cfg.csv_url(year))
        resp.raise_for_status()
        items = []
        for r in csv.DictReader(io.StringIO(resp.text)):
            pid = r.get("player_id")
            if not pid:
                continue
            try:
                mlb_id = int(pid)
            except ValueError:
                continue
            items.append({"mlb_id": mlb_id, "season": int(year),
                          "barrel_rate": _f(r.get("barrel_batted_rate")),
                          "hard_hit": _f(r.get("hard_hit_percent"))})
        logger.info("savant statcast %s: %d batters", year, len(items))
        run_id = f"savant:{_dt.datetime.now(_dt.timezone.utc).isoformat()}"
        return RunResult(actor_id=cfg.SOURCE_ID, run_id=run_id, dataset_id=run_id,
                         items=items, item_count=len(items), estimated_cost_usd=0.0)
    finally:
        if own:
            client.close()
