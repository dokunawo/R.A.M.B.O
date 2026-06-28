"""
EV Brain read API (data-only). GET /betting/daily-edge + /betting/slip return the
ranked picks / slip; POST /betting/prep sources the full multi-feed board for a date.
Every read carries provenance (data-as-of + book + product label + stale guard) so
this engine never quietly serves stale lines and its product is never mistaken for a
cowork sportsbook-prop play. Imports no bet-placement capability (Sentinel boundary).
"""
from __future__ import annotations
import datetime
import os
from dataclasses import asdict
from typing import Optional
from fastapi import APIRouter, HTTPException
from brains.ev.engine import daily_edge
from brains.ev.market import REGISTRY
from brains.ev.slip import build_slip, PRODUCT
from brains.ev.watch import player_watch, moneyline_board, strikeout_watch

router = APIRouter(prefix="/betting", tags=["betting"])

_DB = os.environ.get("RAMBO_DB_PATH", "data/mlb_ingest.db")
_MAX_AGE_H = float(os.environ.get("RAMBO_ODDS_MAX_AGE_H", "6"))


def _data_as_of(market: str) -> Optional[str]:
    from db.migrate import get_connection
    from repositories.mlb_repo import MlbRepo
    try:
        conn = get_connection(_DB)
        try:
            return MlbRepo(conn).latest_capture("moneyline" if market == "ml" else "prop")
        finally:
            conn.close()
    except Exception:
        return None


def _provenance(market: str) -> dict:
    as_of = _data_as_of(market)
    book = "DraftKings" if market == "ml" else "DraftKings Pick6"
    now = datetime.datetime.now(datetime.timezone.utc)
    stale, age_h = False, None
    if as_of:
        try:
            t = datetime.datetime.fromisoformat(as_of.replace("Z", "+00:00"))
            age_h = (now - t).total_seconds() / 3600
            stale = age_h > _MAX_AGE_H
        except ValueError:
            pass
    prov = {"generated_at": now.isoformat(), "data_as_of": as_of, "book": book,
            "product": PRODUCT.get(market, market.upper()), "stale": stale}
    if stale and age_h is not None:
        prov["warning"] = f"⚠ lines are {age_h:.0f}h old — re-pull before betting"
    return prov, as_of, book


@router.get("/daily-edge")
def get_daily_edge(market: str = "hr", date: Optional[str] = None,
                   threshold: float = 0.0) -> dict:
    """Ranked picks for one market (+ provenance). `threshold=-1.0` includes −EV."""
    if market not in REGISTRY:
        raise HTTPException(status_code=404,
                            detail=f"unknown market '{market}' (valid: {sorted(REGISTRY)})")
    d = date or datetime.date.today().isoformat()
    try:
        picks = daily_edge(d, market, threshold=threshold)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"daily_edge failed: {e}") from e
    prov, _, _ = _provenance(market)
    return {"market": market, "date": d, "count": len(picks),
            "picks": [asdict(p) for p in picks], "provenance": prov}


@router.get("/slip")
def get_slip(market: str = "hr", date: Optional[str] = None,
             count: Optional[int] = None) -> dict:
    """Fixed-size slip roster + a ready-to-paste ChatGPT prompt (+ provenance)."""
    if market not in REGISTRY:
        raise HTTPException(status_code=404,
                            detail=f"unknown market '{market}' (valid: {sorted(REGISTRY)})")
    d = date or datetime.date.today().isoformat()
    try:
        prov, as_of, book = _provenance(market)
        picks = daily_edge(d, market, threshold=-1.0)
        slip = build_slip(picks, market, count=count, as_of=as_of, book=book)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"slip failed: {e}") from e
    return {"market": market, "date": d, **slip, "provenance": prov}


@router.get("/player-watch")
def get_player_watch(date: Optional[str] = None) -> dict:
    """Top-11 HR board + a ready-to-paste ChatGPT image prompt (+ provenance)."""
    d = date or datetime.date.today().isoformat()
    try:
        prov, as_of, _ = _provenance("hr")
        watch = player_watch(d, as_of=as_of, book="DraftKings Pick6")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"player_watch failed: {e}") from e
    return {"date": d, **watch, "provenance": prov}


@router.get("/moneyline-board")
def get_moneyline_board(date: Optional[str] = None) -> dict:
    """Every slate game (book odds + model %) + a ChatGPT image prompt (+ provenance)."""
    d = date or datetime.date.today().isoformat()
    try:
        prov, as_of, book = _provenance("ml")
        board = moneyline_board(d, as_of=as_of, book=book)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"moneyline_board failed: {e}") from e
    return {"date": d, **board, "provenance": prov}


@router.get("/strikeout-watch")
def get_strikeout_watch(date: Optional[str] = None) -> dict:
    """Top-11 probable starters by P(9+ K) for alt-strikeout parlays (+ prompt)."""
    d = date or datetime.date.today().isoformat()
    try:
        prov, as_of, _ = _provenance("k")
        board = strikeout_watch(d, as_of=as_of, book=None)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"strikeout_watch failed: {e}") from e
    return {"date": d, **board, "provenance": prov}


@router.post("/prep")
def post_prep(date: Optional[str] = None, with_props: bool = True) -> dict:
    """Pull + normalize the full multi-source board for `date` (schedule, The Odds API,
    last-15 recency, lineups, team stats, Pick6 props) and top up player stats."""
    from db.migrate import get_connection
    from ingestion.prep import prep_slate
    d = date or datetime.date.today().isoformat()
    conn = get_connection(_DB)
    try:
        return prep_slate(conn, d, with_props=with_props)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"prep failed: {e}") from e
    finally:
        conn.close()
