"""Backfill historical moneyline snapshots (The Odds API historical endpoint) so the
walk-forward backtest can grade ROI/CLV against the real lines. For each final game
we pull two instants — an early line (commence-4h, starters usually confirmed) and a
closing line (commence-5min). Snapshot instants are deduped across the slate so each
distinct instant is a single API call. Idempotent (odds_lines UPSERT on snapshot_key)."""
from __future__ import annotations

import datetime as _dt
import logging
import sqlite3

logger = logging.getLogger("rambo.ingestion.odds_backfill")

EARLY_BEFORE = _dt.timedelta(hours=4)
CLOSE_BEFORE = _dt.timedelta(minutes=5)


def snapshot_times(commence_iso: str) -> tuple[str, str]:
    """(early, closing) ISO instants for a game's commence time."""
    t = _dt.datetime.fromisoformat(commence_iso)
    return (t - EARLY_BEFORE).isoformat(), (t - CLOSE_BEFORE).isoformat()


def backfill_odds(conn: sqlite3.Connection, start: str, end: str, *, pull=None) -> dict:
    """Pull early+closing historical moneylines for every final game in [start,end].
    `pull` defaults to sources.pull_source (injectable for tests)."""
    if pull is None:
        from ingestion.sources import pull_source as pull
    rows = conn.execute(
        "SELECT game_pk, game_datetime FROM games "
        "WHERE official_date BETWEEN ? AND ? "
        "AND home_score IS NOT NULL AND away_score IS NOT NULL "
        "ORDER BY official_date, game_pk", (start, end)).fetchall()

    instants: set[str] = set()
    skipped = 0
    for r in rows:
        dt = r["game_datetime"] if isinstance(r, sqlite3.Row) else r[1]
        if not dt:
            skipped += 1
            continue
        early, close = snapshot_times(dt)
        instants.add(early)
        instants.add(close)

    events = 0
    for snap in sorted(instants):
        try:
            res = pull(conn, "odds_api_historical", {"snapshot": snap})
            events += int(res.get("items") or 0)
        except Exception as exc:                 # one bad instant shouldn't abort
            logger.warning("historical odds backfill failed for %s: %s", snap, exc)
    from ingestion.normalize import normalize_pending
    normalize_pending(conn)
    return {"snapshots": len(instants), "events": events,
            "skipped_no_datetime": skipped}
