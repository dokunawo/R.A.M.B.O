"""
EV Brain read API (data-only). GET /betting/daily-edge?market=hr&date=YYYY-MM-DD
returns the ranked +EV picks for one market — the JSON the CMC card fetches.
Imports no bet-placement capability (Sentinel boundary by construction).
"""
from __future__ import annotations
import datetime
from dataclasses import asdict
from typing import Optional
from fastapi import APIRouter, HTTPException
from brains.ev.engine import daily_edge
from brains.ev.market import REGISTRY

router = APIRouter(prefix="/betting", tags=["betting"])


@router.get("/daily-edge")
def get_daily_edge(market: str = "hr", date: Optional[str] = None) -> dict:
    if market not in REGISTRY:
        raise HTTPException(status_code=404,
                            detail=f"unknown market '{market}' (valid: {sorted(REGISTRY)})")
    d = date or datetime.date.today().isoformat()
    try:
        picks = daily_edge(d, market)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"daily_edge failed: {e}") from e
    return {"market": market, "date": d, "count": len(picks),
            "picks": [asdict(p) for p in picks]}
