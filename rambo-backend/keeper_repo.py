"""Keeper persistence — a SQLite-backed memory store with semantic recall.

Originally a plain key/value store (substring query). Now augmented with Voyage
embeddings so memories cluster into auto-split topics (à la isair/jarvis) and can
be recalled associatively (semantic_query), not just by substring.

Everything degrades gracefully: without VOYAGE_API_KEY, writes simply store a
NULL embedding and recall falls back to the substring query() — identical to the
pre-embedding behavior.
"""

from __future__ import annotations

import json
import logging
import os
import struct
import aiosqlite
from datetime import datetime, timezone
from pathlib import Path

import embeddings

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path(__file__).parent / "data" / "keeper.db"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS memories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    key        TEXT    NOT NULL UNIQUE,
    value      TEXT    NOT NULL DEFAULT '',
    tags       TEXT    NOT NULL DEFAULT '',
    embedding  BLOB,
    topic      TEXT,
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_updated_at ON memories(updated_at DESC);
CREATE TABLE IF NOT EXISTS topics (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL UNIQUE,
    embedding  BLOB,
    created_at TEXT    NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pack(vec: list[float] | None) -> bytes | None:
    if not vec:
        return None
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack(blob: bytes | None) -> list[float] | None:
    if not blob:
        return None
    return list(struct.unpack(f"{len(blob) // 4}f", blob))


def _topic_threshold() -> float:
    """Cosine floor for joining an existing topic; below it, spawn a new topic."""
    try:
        return float(os.environ.get("RAMBO_TOPIC_THRESHOLD", "0.6"))
    except ValueError:
        return 0.6


def _recall_floor() -> float:
    """Minimum cosine for a semantic_query hit to count (else substring fallback)."""
    try:
        return float(os.environ.get("RAMBO_RECALL_FLOOR", "0.4"))
    except ValueError:
        return 0.4


def _topic_name_from(key: str, value: str) -> str:
    base = (key or value or "general").strip().lower()
    return " ".join(base.split()[:3]) or "general"


class KeeperRepo:
    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB

    async def init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_SCHEMA)
            await self._migrate(db)
            await db.commit()

    async def _migrate(self, db) -> None:
        """Add embedding/topic columns to pre-existing memories tables."""
        cur = await db.execute("PRAGMA table_info(memories)")
        cols = {row[1] for row in await cur.fetchall()}
        if "embedding" not in cols:
            await db.execute("ALTER TABLE memories ADD COLUMN embedding BLOB")
        if "topic" not in cols:
            await db.execute("ALTER TABLE memories ADD COLUMN topic TEXT")

    # ── topic assignment ─────────────────────────────────────────────
    async def _assign_topic(self, db, vec: list[float] | None) -> str | None:
        """Return the topic name for a memory vector: nearest existing topic above
        threshold, else a freshly created topic. None when embeddings are off."""
        if vec is None:
            return None
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall("SELECT name, embedding FROM topics")
        best_name, best_score = None, -1.0
        for r in rows:
            tvec = _unpack(r["embedding"])
            if tvec is None:
                continue
            score = embeddings.cosine(vec, tvec)
            if score > best_score:
                best_name, best_score = r["name"], score
        if best_name is not None and best_score >= _topic_threshold():
            return best_name
        return None  # caller creates a new topic (it knows key/value for naming)

    # (a) write -----------------------------------------------------------
    async def write(self, key: str, value: str, tags: str = "") -> int:
        """Store (or update) an entry by key. Embeds the value and assigns a topic
        when embeddings are available; otherwise stores NULL (legacy behavior)."""
        now = _now()
        vec = await embeddings.embed_one(value, input_type="document")
        blob = _pack(vec)

        async with aiosqlite.connect(self._db_path) as db:
            topic = await self._assign_topic(db, vec)
            if topic is None and vec is not None:
                # No matching topic — auto-split: create a new one seeded by this memory.
                topic = _topic_name_from(key, value)
                await db.execute(
                    "INSERT OR IGNORE INTO topics (name, embedding, created_at) "
                    "VALUES (?, ?, ?)",
                    (topic, blob, now),
                )
            await db.execute(
                "INSERT INTO memories (key, value, tags, embedding, topic, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET "
                "  value=excluded.value, tags=excluded.tags, "
                "  embedding=excluded.embedding, topic=excluded.topic, "
                "  updated_at=excluded.updated_at",
                (key, value, tags, blob, topic, now, now),
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
            rows = await db.execute_fetchall(
                "SELECT id, key, value, tags, topic, created_at, updated_at "
                "FROM memories WHERE key=?", (key,)
            )
            return dict(rows[0]) if rows else None

    async def query(self, search: str = "", limit: int = 50) -> list[dict]:
        """Substring search across key/value/tags (case-insensitive), newest first.
        Empty search returns the latest rows. The original, always-available recall."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            select = ("SELECT id, key, value, tags, topic, created_at, updated_at "
                      "FROM memories")
            if search:
                like = f"%{search.lower()}%"
                rows = await db.execute_fetchall(
                    f"{select} WHERE "
                    "  LOWER(key) LIKE ? OR LOWER(value) LIKE ? OR LOWER(tags) LIKE ? "
                    "ORDER BY updated_at DESC LIMIT ?",
                    (like, like, like, limit),
                )
            else:
                rows = await db.execute_fetchall(
                    f"{select} ORDER BY updated_at DESC LIMIT ?", (limit,)
                )
            return [dict(r) for r in rows]

    async def semantic_query(self, text: str, limit: int = 5) -> list[dict]:
        """Embed `text` and return the closest memories by cosine, above the recall
        floor, newest-first on ties. Empty list when embeddings are unavailable or
        nothing clears the floor — callers should then fall back to query()."""
        qvec = await embeddings.embed_one(text, input_type="query")
        if qvec is None:
            return []
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT id, key, value, tags, topic, embedding, updated_at FROM memories "
                "WHERE embedding IS NOT NULL"
            )
        floor = _recall_floor()
        scored: list[tuple[float, dict]] = []
        for r in rows:
            vec = _unpack(r["embedding"])
            if vec is None:
                continue
            score = embeddings.cosine(qvec, vec)
            if score >= floor:
                d = {k: r[k] for k in r.keys() if k != "embedding"}
                d["score"] = round(score, 4)
                scored.append((score, d))
        scored.sort(key=lambda s: (s[0], s[1]["updated_at"]), reverse=True)
        return [d for _s, d in scored[:limit]]

    # (c) confirm ---------------------------------------------------------
    async def confirm(self, recent: int = 5) -> dict:
        """Confirm what's stored: total count + the most recent entries."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            count_rows = await db.execute_fetchall("SELECT COUNT(*) AS n FROM memories")
            count = int(count_rows[0]["n"]) if count_rows else 0
            rows = await db.execute_fetchall(
                "SELECT id, key, value, tags, topic, created_at, updated_at "
                "FROM memories ORDER BY updated_at DESC LIMIT ?", (recent,)
            )
            return {"count": count, "recent": [dict(r) for r in rows]}
