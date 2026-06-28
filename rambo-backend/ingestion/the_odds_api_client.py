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


def fetch_events(*, client: Optional[httpx.Client] = None) -> list[dict]:
    """List upcoming MLB events (id + teams + commence_time). FREE — the events
    endpoint doesn't count against quota."""
    key = cfg.api_key()
    if not key:
        raise RuntimeError("THE_ODDS_API_KEY not set in .env")
    own = client is None
    client = client or httpx.Client(timeout=DEFAULT_TIMEOUT)
    try:
        resp = client.get(f"{cfg.BASE}/sports/{cfg.SPORT}/events", params={"apiKey": key})
        resp.raise_for_status()
        return resp.json() or []
    finally:
        if own:
            client.close()


def fetch_props(date: Optional[str] = None, *, max_events: Optional[int] = None,
                client: Optional[httpx.Client] = None) -> RunResult:
    """Per-event player props across US books. Lists events (free), then pulls each
    event's odds for PROP_MARKETS — cost = events × markets credits. `max_events`
    caps the spend (use 1 for a ~len(markets)-credit smoke test). Each event is one
    raw item carrying its bookmakers; the normalizer expands them to prop_lines."""
    key = cfg.api_key()
    if not key:
        raise RuntimeError("THE_ODDS_API_KEY not set in .env")
    own = client is None
    client = client or httpx.Client(timeout=DEFAULT_TIMEOUT)
    try:
        events = fetch_events(client=client)
        if date:                                    # keep events whose ET-ish day matches
            events = [e for e in events if (e.get("commence_time") or "")[:10] == date] or events
        if max_events is not None:
            events = events[:max_events]
        markets = ",".join(cfg.prop_markets())
        captured = _now_iso()
        items, remaining = [], None
        for e in events:
            try:
                r = client.get(f"{cfg.BASE}/sports/{cfg.SPORT}/events/{e['id']}/odds",
                               params={"apiKey": key, "regions": cfg.REGIONS,
                                       "markets": markets, "oddsFormat": cfg.ODDS_FORMAT})
                r.raise_for_status()
            except Exception as exc:                # one bad event shouldn't abort the slate
                logger.warning("the-odds-api props failed for %s: %s", e.get("id"), exc)
                continue
            remaining = r.headers.get("x-requests-remaining", remaining)
            ev = r.json() or {}
            ev["_captured_at"] = captured
            items.append(ev)
        logger.info("the-odds-api props: %d events (requests remaining: %s)", len(items), remaining)
        run_id = f"{cfg.PROPS_SOURCE_ID}:{captured}"
        return RunResult(actor_id=cfg.PROPS_SOURCE_ID, run_id=run_id, dataset_id=run_id,
                         items=items, item_count=len(items), estimated_cost_usd=0.0)
    finally:
        if own:
            client.close()


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


def fetch_moneyline_historical(snapshot_iso: str, *,
                               client: Optional[httpx.Client] = None) -> RunResult:
    """Historical MLB moneylines at a past instant. The Odds API wraps events in
    {timestamp, data:[...]}; we unwrap `data` and stamp each event's _captured_at
    from the response timestamp so the existing live normalizer handles them
    verbatim. Costs the historical credit multiplier — logs requests-remaining."""
    key = cfg.api_key()
    if not key:
        raise RuntimeError("THE_ODDS_API_KEY not set in .env")
    own = client is None
    client = client or httpx.Client(timeout=DEFAULT_TIMEOUT)
    try:
        url = f"{cfg.BASE}/historical/sports/{cfg.SPORT}/odds"
        # Normalize +00:00 UTC offset to Z form for The Odds API compatibility
        date_param = snapshot_iso.replace("+00:00", "Z")
        params = {"apiKey": key, "regions": cfg.REGIONS, "markets": cfg.MARKETS,
                  "oddsFormat": cfg.ODDS_FORMAT, "date": date_param}
        resp = client.get(url, params=params)
        resp.raise_for_status()
        body = resp.json() or {}
        snap_ts = body.get("timestamp") or snapshot_iso
        events = body.get("data") or []
        for e in events:
            e["_captured_at"] = snap_ts
        remaining = resp.headers.get("x-requests-remaining")
        logger.info("the-odds-api historical %s: %d events (requests remaining: %s)",
                    snapshot_iso, len(events), remaining)
        run_id = f"{cfg.SOURCE_ID}:hist:{snap_ts}"
        return RunResult(actor_id=cfg.SOURCE_ID, run_id=run_id, dataset_id=run_id,
                         items=events, item_count=len(events), estimated_cost_usd=0.0)
    finally:
        if own:
            client.close()
