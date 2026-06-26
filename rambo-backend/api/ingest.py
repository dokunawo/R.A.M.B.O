"""
R.A.M.B.O. MLB Betting Agent — Ingestion API (Step 5)
api/ingest.py

POST /ingest/run triggers a pull on demand (free statsapi or paid Apify). This
router imports ONLY data tools (source dispatcher, normalizer, migrations). It
deliberately imports nothing that can place, stake, or transmit a bet.

SENTINEL BOUNDARY: ingestion may write data freely. Any staking/outbound action
must route through the existing Sentinel approval path elsewhere — never added here.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db.migrate import apply_migrations, get_connection
from ingestion.normalize import normalize_pending
from ingestion.sources import SOURCES, pull_source

DB_PATH = os.environ.get("RAMBO_DB_PATH", "data/mlb_ingest.db")
MIGRATIONS_DIR = os.environ.get("RAMBO_MIGRATIONS_DIR", "db/migrations")

router = APIRouter(prefix="/ingest", tags=["ingestion"])


def get_db():
    conn = get_connection(DB_PATH)
    apply_migrations(conn, MIGRATIONS_DIR)  # idempotent; keeps schema current
    try:
        yield conn
    finally:
        conn.close()


class IngestRequest(BaseModel):
    source: str = Field(..., description="odds|props|roster|schedule|stats")
    date: Optional[str] = Field(default=None, description="YYYY-MM-DD (schedule/odds)")
    season: Optional[int] = None
    player_id: Optional[int] = Field(default=None, description="required for 'stats'")
    overrides: dict[str, Any] = Field(default_factory=dict)
    normalize: bool = Field(default=True, description="Run normalization after landing")


class IngestResponse(BaseModel):
    actor_id: str
    run_id: str
    items: int
    inserted: int
    skipped: int
    estimated_cost_usd: float
    normalized: Optional[dict[str, int]] = None


@router.post("/run", response_model=IngestResponse)
def ingest_run(req: IngestRequest, conn=Depends(get_db)) -> IngestResponse:
    if req.source not in SOURCES:
        raise HTTPException(status_code=404,
                            detail=f"unknown source '{req.source}' (valid: {SOURCES})")
    params = {"date": req.date, "season": req.season,
              "player_id": req.player_id, "overrides": req.overrides}
    try:
        summary = pull_source(conn, req.source, params)
    except Exception as e:  # guardrail breach, run failure, bad input...
        raise HTTPException(status_code=502, detail=f"ingest failed: {e}") from e

    norm = normalize_pending(conn) if req.normalize else None
    return IngestResponse(normalized=norm, **summary)


@router.get("/health")
def ingest_health(conn=Depends(get_db)) -> dict[str, Any]:
    unresolved = conn.execute(
        "SELECT COUNT(*) FROM prop_lines WHERE mlb_id IS NULL").fetchone()[0]
    pending = conn.execute(
        "SELECT COUNT(*) FROM player_review WHERE status='pending'").fetchone()[0]
    backlog = conn.execute(
        "SELECT COUNT(*) FROM raw_ingest WHERE normalized_at IS NULL").fetchone()[0]
    return {"unresolved_props": unresolved, "players_in_review": pending,
            "unnormalized_raw": backlog}
