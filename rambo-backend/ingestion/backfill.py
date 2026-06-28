"""Backfill past game results (free statsapi schedule) so the backtest harness
has real outcomes to grade against.

Pulls the schedule for each date in a range and normalizes — finished games land
with final scores in the `games` table. Free + idempotent (games UPSERT on
game_pk), so re-running just refreshes.
"""
from __future__ import annotations

import datetime as _dt
import logging
import sqlite3

from ingestion.sources import pull_source
from ingestion.normalize import normalize_pending

logger = logging.getLogger("rambo.ingestion.backfill")


def _dates(start: str, end: str):
    d, e = _dt.date.fromisoformat(start), _dt.date.fromisoformat(end)
    while d <= e:
        yield d.isoformat()
        d += _dt.timedelta(days=1)


def backfill_results(conn: sqlite3.Connection, start: str, end: str) -> dict:
    """Pull + normalize the schedule for every date in [start, end]. Returns a
    summary {days, games_pulled, finals} where finals = games now carrying a
    final score in the range."""
    days = pulled = 0
    for d in _dates(start, end):
        try:
            pulled += pull_source(conn, "schedule", {"date": d})["items"]
            days += 1
        except Exception as exc:                      # one bad date shouldn't abort
            logger.warning("schedule backfill failed for %s: %s", d, exc)
    normalize_pending(conn)
    finals = conn.execute(
        "SELECT COUNT(*) FROM games WHERE official_date BETWEEN ? AND ? "
        "AND home_score IS NOT NULL AND away_score IS NOT NULL", (start, end)
    ).fetchone()[0]
    return {"days": days, "games_pulled": pulled, "finals": finals}
