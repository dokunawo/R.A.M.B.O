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
def get_daily_edge(market: str = "hr", date: Optional[str] = None,
                   threshold: float = 0.0) -> dict:
    """Ranked picks for one market. Default `threshold=0.0` returns only +edge
    plays. Pass a negative threshold (e.g. -1.0) to include −EV candidates — the
    CMC card uses this to show props the model is steering AWAY from, flagged
    honestly rather than hidden as empty."""
    if market not in REGISTRY:
        raise HTTPException(status_code=404,
                            detail=f"unknown market '{market}' (valid: {sorted(REGISTRY)})")
    d = date or datetime.date.today().isoformat()
    try:
        picks = daily_edge(d, market, threshold=threshold)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"daily_edge failed: {e}") from e
    return {"market": market, "date": d, "count": len(picks),
            "picks": [asdict(p) for p in picks]}
