"""Durable Q&A transcript (SQLite).

A clean, copy-pasteable record of every question the operator asked and RAMBO's
answer — separate from the verbose conversation history used for LLM context.
Surfaced via /transcript (the History page + dock). Best-effort writes: a failure
never breaks a turn.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path(__file__).parent / "data" / "transcript.db"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS entries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    question   TEXT    NOT NULL DEFAULT '',
    answer     TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entries_id ON entries(id DESC);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TranscriptRepo:
    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB

    async def init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    async def add(self, question: str, answer: str) -> None:
        if not (question or "").strip() and not (answer or "").strip():
            return
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    "INSERT INTO entries (question, answer, created_at) VALUES (?, ?, ?)",
                    (question or "", answer or "", _now()),
                )
                await db.commit()
        except Exception:
            logger.exception("transcript append failed")

    async def recent(self, limit: int = 100) -> list[dict]:
        """Most recent `limit` entries in chronological order (oldest first)."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT id, question, answer, created_at FROM entries "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = await cur.fetchall()
        return [dict(r) for r in reversed(rows)]

    async def all(self, limit: int = 500, offset: int = 0) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT id, question, answer, created_at FROM entries "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = await cur.fetchall()
        return [dict(r) for r in reversed(rows)]

    async def clear(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM entries")
            await db.commit()
