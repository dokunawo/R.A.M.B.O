"""Durable conversation history (SQLite).

ConversationManager is otherwise in-memory and wiped on restart. This repo
persists every turn so RAMBO's chat survives restarts and can be surfaced via
the /history endpoint. Best-effort: callers never let a write failure break the
voice path.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path(__file__).parent / "data" / "conversation.db"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS turns (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    role       TEXT    NOT NULL,
    content    TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_id ON turns(id DESC);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationRepo:
    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB

    async def init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    async def append(self, role: str, content: str) -> None:
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    "INSERT INTO turns (role, content, created_at) VALUES (?, ?, ?)",
                    (role, content, _now()),
                )
                await db.commit()
        except Exception:
            logger.exception("conversation append failed")

    async def recent(self, limit: int = 20) -> list[dict]:
        """Most recent `limit` turns in chronological order (oldest first)."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT id, role, content, created_at FROM turns ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = await cur.fetchall()
        return [dict(r) for r in reversed(rows)]

    async def all(self, limit: int = 200, offset: int = 0) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT id, role, content, created_at FROM turns "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = await cur.fetchall()
        return [dict(r) for r in reversed(rows)]

    async def clear(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM turns")
            await db.commit()
