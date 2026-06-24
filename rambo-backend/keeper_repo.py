"""Keeper persistence — a real SQLite-backed key/value memory store.

Replaces the in-memory dict stub (memory/sqlite_store.py) with durable storage,
mirroring usage_repo.py / dispatch_repo.py conventions (async aiosqlite,
data/*.db). Clean API: write(), read(), query(), confirm().
"""

from __future__ import annotations

import aiosqlite
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_DB = Path(__file__).parent / "data" / "keeper.db"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS memories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    key        TEXT    NOT NULL UNIQUE,
    value      TEXT    NOT NULL DEFAULT '',
    tags       TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_updated_at ON memories(updated_at DESC);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class KeeperRepo:
    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB

    async def init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_SCHEMA)

    # (a) write -----------------------------------------------------------
    async def write(self, key: str, value: str, tags: str = "") -> int:
        """Store (or update) an entry by key. Returns the row id."""
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO memories (key, value, tags, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET "
                "  value=excluded.value, tags=excluded.tags, updated_at=excluded.updated_at",
                (key, value, tags, now, now),
            )
            await db.commit()
            cur = await db.execute("SELECT id FROM memories WHERE key=?", (key,))
            row = await cur.fetchone()
            return int(row[0])

    # (b) read / query ----------------------------------------------------
    async def read(self, key: str) -> dict | None:
        """Read a single entry by exact key, or None."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall("SELECT * FROM memories WHERE key=?", (key,))
            return dict(rows[0]) if rows else None

    async def query(self, search: str = "", limit: int = 50) -> list[dict]:
        """Return entries matching `search` across key/value/tags (substring,
        case-insensitive), newest first. Empty search returns the latest rows."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if search:
                like = f"%{search.lower()}%"
                rows = await db.execute_fetchall(
                    "SELECT * FROM memories WHERE "
                    "  LOWER(key) LIKE ? OR LOWER(value) LIKE ? OR LOWER(tags) LIKE ? "
                    "ORDER BY updated_at DESC LIMIT ?",
                    (like, like, like, limit),
                )
            else:
                rows = await db.execute_fetchall(
                    "SELECT * FROM memories ORDER BY updated_at DESC LIMIT ?", (limit,)
                )
            return [dict(r) for r in rows]

    # (c) confirm ---------------------------------------------------------
    async def confirm(self, recent: int = 5) -> dict:
        """Confirm what's stored: total count + the most recent entries."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            count_rows = await db.execute_fetchall("SELECT COUNT(*) AS n FROM memories")
            count = int(count_rows[0]["n"]) if count_rows else 0
            rows = await db.execute_fetchall(
                "SELECT * FROM memories ORDER BY updated_at DESC LIMIT ?", (recent,)
            )
            return {"count": count, "recent": [dict(r) for r in rows]}
