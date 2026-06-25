from __future__ import annotations

import aiosqlite
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_DB = Path(__file__).parent / "data" / "usage.db"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS usage (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    model       TEXT    NOT NULL,
    input_tokens              INTEGER NOT NULL DEFAULT 0,
    output_tokens             INTEGER NOT NULL DEFAULT 0,
    cache_creation_input_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_input_tokens   INTEGER NOT NULL DEFAULT 0,
    cost_usd    REAL    NOT NULL DEFAULT 0.0,
    source      TEXT    NOT NULL DEFAULT 'conversation',
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_created_at ON usage(created_at);
"""


class UsageRepo:
    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB

    async def init_db(self):
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_SCHEMA)

    async def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_creation_input_tokens: int,
        cache_read_input_tokens: int,
        cost_usd: float,
        source: str = "conversation",
    ):
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO usage "
                "(model, input_tokens, output_tokens, cache_creation_input_tokens, "
                "cache_read_input_tokens, cost_usd, source, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (model, input_tokens, output_tokens,
                 cache_creation_input_tokens, cache_read_input_tokens,
                 cost_usd, source, now),
            )
            await db.commit()

    async def usage_since(
        self, start: str, end: str | None = None,
    ) -> dict:
        end = end or datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            row = await db.execute_fetchall(
                "SELECT "
                "  COALESCE(SUM(input_tokens), 0)                AS total_input, "
                "  COALESCE(SUM(output_tokens), 0)               AS total_output, "
                "  COALESCE(SUM(cache_creation_input_tokens), 0) AS total_cache_write, "
                "  COALESCE(SUM(cache_read_input_tokens), 0)     AS total_cache_read, "
                "  COALESCE(SUM(cost_usd), 0.0)                  AS total_cost, "
                "  COUNT(*)                                      AS call_count "
                # Exclude Voyage embeddings — they have their own EMBED chip and
                # live in the free tier; counting them here would show phantom spend.
                "FROM usage WHERE created_at >= ? AND created_at <= ? "
                "  AND model NOT LIKE 'voyage%'",
                (start, end),
            )
            totals = dict(row[0])

            models = await db.execute_fetchall(
                "SELECT model, "
                "  COALESCE(SUM(cost_usd), 0.0) AS cost, "
                "  COUNT(*) AS calls "
                "FROM usage WHERE created_at >= ? AND created_at <= ? "
                "  AND model NOT LIKE 'voyage%' "
                "GROUP BY model ORDER BY cost DESC",
                (start, end),
            )
            totals["by_model"] = [dict(r) for r in models]

            daily = await db.execute_fetchall(
                "SELECT DATE(created_at) AS day, "
                "  COALESCE(SUM(cost_usd), 0.0) AS cost, "
                "  COALESCE(SUM(input_tokens), 0) AS input_tokens, "
                "  COALESCE(SUM(output_tokens), 0) AS output_tokens, "
                "  COUNT(*) AS calls "
                "FROM usage WHERE created_at >= ? AND created_at <= ? "
                "  AND model NOT LIKE 'voyage%' "
                "GROUP BY DATE(created_at) ORDER BY day DESC",
                (start, end),
            )
            totals["by_day"] = [dict(r) for r in daily]
        return totals

    async def voyage_totals(self, start: str | None = None) -> dict:
        """Aggregate embedding usage (model LIKE 'voyage%'). `start` (ISO) limits
        to a window; omit for all-time totals. Used by the EMBED credit HUD."""
        clause = "WHERE model LIKE 'voyage%'"
        params: tuple = ()
        if start:
            clause += " AND created_at >= ?"
            params = (start,)
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT "
                "  COALESCE(SUM(input_tokens), 0) AS tokens, "
                "  COALESCE(SUM(cost_usd), 0.0)   AS cost, "
                "  COUNT(*)                       AS calls "
                f"FROM usage {clause}",
                params,
            )
            return dict(rows[0]) if rows else {"tokens": 0, "cost": 0.0, "calls": 0}
