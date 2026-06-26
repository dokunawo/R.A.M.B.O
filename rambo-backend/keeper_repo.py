"""Keeper persistence — a SQLite-backed memory store with semantic recall.

Originally a plain key/value store (substring query). Now augmented with Voyage
embeddings so memories cluster into auto-split topics (à la isair/jarvis) and can
be recalled associatively (semantic_query), not just by substring.

Everything degrades gracefully: without VOYAGE_API_KEY, writes simply store a
NULL embedding and recall falls back to the substring query() — identical to the
pre-embedding behavior.
"""

from __future__ import annotations

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
    confidence TEXT    NOT NULL DEFAULT 'hint',
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
    """Minimum cosine for a semantic_query hit to count (else substring fallback).
    Set conservatively: short-text embeddings of *unrelated* phrases often score
    ~0.4-0.5, so a low floor returns false-positive recalls instead of 'nothing
    stored'. Tune live via RAMBO_RECALL_FLOOR."""
    try:
        return float(os.environ.get("RAMBO_RECALL_FLOOR", "0.55"))
    except ValueError:
        return 0.55


import math
import re as _re

_STOP = {
    "the", "a", "an", "my", "our", "your", "is", "are", "was", "were", "be",
    "to", "of", "in", "on", "for", "and", "or", "what", "whats", "about",
    "do", "you", "i", "me", "it", "that", "this", "with", "have", "has",
}


def _tokenize(text: str) -> list[str]:
    """Lowercase word tokens, stopwords dropped, length>2. Trailing 's' stripped
    so 'dogs' and 'dog' collide (cheap stemming)."""
    out = []
    for w in _re.findall(r"[a-z0-9]+", (text or "").lower()):
        if len(w) <= 2 or w in _STOP:
            continue
        if w.endswith("s") and len(w) > 3:
            w = w[:-1]
        out.append(w)
    return out


def _recency_score(updated_at: str, now: datetime) -> float:
    """1.0 for just-now, decaying smoothly with a ~30-day half-life, floored at 0."""
    try:
        ts = datetime.fromisoformat(updated_at)
    except (ValueError, TypeError):
        return 0.0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - ts).total_seconds() / 86400.0)
    return 0.5 ** (age_days / 30.0)


def _bm25_scores(query_terms: list[str], rows) -> list[float]:
    """BM25 over the candidate set, normalized to [0,1]. Each row's document is its
    key+value+tags. Returns 0.0 for every row when the query has no usable terms."""
    n = len(rows)
    if not query_terms or n == 0:
        return [0.0] * n
    docs = [_tokenize(f"{r['key']} {r['value']} {r['tags']}") for r in rows]
    lengths = [len(d) for d in docs]
    avgdl = (sum(lengths) / n) or 1.0
    qset = set(query_terms)

    # Document frequency per query term.
    df = {t: 0 for t in qset}
    for d in docs:
        seen = set(d)
        for t in qset:
            if t in seen:
                df[t] += 1

    k1, b = 1.5, 0.75
    raw: list[float] = []
    for i, d in enumerate(docs):
        if not d:
            raw.append(0.0)
            continue
        tf = {}
        for tok in d:
            if tok in qset:
                tf[tok] = tf.get(tok, 0) + 1
        score = 0.0
        for t, f in tf.items():
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            denom = f + k1 * (1 - b + b * lengths[i] / avgdl)
            score += idf * (f * (k1 + 1)) / denom
        raw.append(score)

    hi = max(raw) or 1.0
    return [s / hi for s in raw]


def _topic_name_from(key: str, value: str) -> str:
    base = (key or value or "general").strip().lower()
    return " ".join(base.split()[:3]) or "general"


# Cap the per-recall vector scan (no ANN index — cosine is computed in Python).
# Newest memories are scanned first; raise via RAMBO_RECALL_SCAN_LIMIT if needed.
def _recall_scan_limit() -> int:
    try:
        return max(1, int(os.environ.get("RAMBO_RECALL_SCAN_LIMIT", "1000")))
    except ValueError:
        return 1000


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
        if "confidence" not in cols:
            await db.execute(
                "ALTER TABLE memories ADD COLUMN confidence TEXT NOT NULL DEFAULT 'hint'"
            )
            # Pre-existing memories predate the confidence concept; treat them as
            # verified so recall phrasing doesn't suddenly hedge on trusted facts.
            await db.execute("UPDATE memories SET confidence='verified'")

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

    async def _new_topic(self, db, key: str, value: str, blob, now: str) -> str:
        """Create a fresh topic seeded by this memory, with a collision-free name so
        an unrelated cluster sharing a 3-word key prefix can't merge into it."""
        base = _topic_name_from(key, value)
        name, n = base, 2
        while True:
            cur = await db.execute("SELECT 1 FROM topics WHERE name=?", (name,))
            if await cur.fetchone() is None:
                break
            name, n = f"{base} ({n})", n + 1
        await db.execute(
            "INSERT INTO topics (name, embedding, created_at) VALUES (?, ?, ?)",
            (name, blob, now),
        )
        return name

    # (a) write -----------------------------------------------------------
    async def write(self, key: str, value: str, tags: str = "",
                    confidence: str = "verified") -> int:
        """Store (or update) an entry by key. Embeds the value and assigns a topic
        when embeddings are available; otherwise stores NULL (legacy behavior).

        ``confidence`` is 'verified' (an explicit, trusted fact — the default for
        direct user saves) or 'hint' (inferred/uncertain — recall hedges on it)."""
        if confidence not in ("verified", "hint"):
            confidence = "hint"
        now = _now()
        vec = await embeddings.embed_one(value, input_type="document")
        blob = _pack(vec)

        async with aiosqlite.connect(self._db_path) as db:
            topic = await self._assign_topic(db, vec)
            if topic is None and vec is not None:
                # No semantic match — auto-split into a genuinely new topic.
                topic = await self._new_topic(db, key, value, blob, now)
            await db.execute(
                "INSERT INTO memories (key, value, tags, embedding, topic, confidence, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET "
                "  value=excluded.value, tags=excluded.tags, "
                "  embedding=excluded.embedding, topic=excluded.topic, "
                "  confidence=excluded.confidence, "
                "  updated_at=excluded.updated_at",
                (key, value, tags, blob, topic, confidence, now, now),
            )
            if vec is not None:
                # GC topics no longer referenced (e.g. this memory moved clusters
                # on update) so the topic table stays bounded.
                await db.execute(
                    "DELETE FROM topics WHERE name NOT IN "
                    "(SELECT topic FROM memories WHERE topic IS NOT NULL)"
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
                "SELECT id, key, value, tags, topic, confidence, created_at, updated_at "
                "FROM memories WHERE key=?", (key,)
            )
            return dict(rows[0]) if rows else None

    async def delete(self, key: str) -> bool:
        """Remove a memory by exact key. Returns True if a row was deleted.
        Orphaned topics are left for the next write's GC pass."""
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute("DELETE FROM memories WHERE key=?", (key,))
            await db.commit()
            return cur.rowcount > 0

    async def query(self, search: str = "", limit: int = 50) -> list[dict]:
        """Substring search across key/value/tags (case-insensitive), newest first.
        Empty search returns the latest rows. The original, always-available recall."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            select = ("SELECT id, key, value, tags, topic, confidence, created_at, updated_at "
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
                "SELECT id, key, value, tags, topic, confidence, embedding, updated_at FROM memories "
                "WHERE embedding IS NOT NULL ORDER BY updated_at DESC LIMIT ?",
                (_recall_scan_limit(),),
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

    # (b2) hybrid recall --------------------------------------------------
    async def recall(self, text: str, limit: int = 5) -> list[dict]:
        """Hybrid recall: blend keyword (BM25-lite), semantic cosine, recency, and
        confidence into a single ranking. Degrades to keyword+recency when Voyage
        is unavailable, so quality no longer collapses to raw substring matching.

        A candidate must have *some* lexical or semantic signal to appear — pure
        recency never surfaces an unrelated memory."""
        terms = _tokenize(text)
        qvec = await embeddings.embed_one(text, input_type="query") if text else None

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT id, key, value, tags, topic, confidence, embedding, "
                "       created_at, updated_at "
                "FROM memories ORDER BY updated_at DESC LIMIT ?",
                (_recall_scan_limit(),),
            )
        if not rows:
            return []

        kw_scores = _bm25_scores(terms, rows)
        floor = _recall_floor()
        now = datetime.now(timezone.utc)
        scored: list[tuple[float, dict]] = []
        for i, r in enumerate(rows):
            kw = kw_scores[i]
            sem = 0.0
            if qvec is not None:
                vec = _unpack(r["embedding"])
                if vec is not None:
                    c = embeddings.cosine(qvec, vec)
                    sem = c if c >= floor else 0.0
            # Require lexical or semantic evidence; recency/confidence only re-rank.
            if kw <= 0.0 and sem <= 0.0:
                continue
            rec = _recency_score(r["updated_at"], now)
            conf = 1.0 if (r["confidence"] or "verified") != "hint" else 0.6
            blended = (0.5 * sem) + (0.35 * kw) + (0.1 * rec) + (0.05 * conf)
            d = {k: r[k] for k in r.keys() if k != "embedding"}
            d["score"] = round(blended, 4)
            scored.append((blended, d))

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
                "SELECT id, key, value, tags, topic, confidence, created_at, updated_at "
                "FROM memories ORDER BY updated_at DESC LIMIT ?", (recent,)
            )
            return {"count": count, "recent": [dict(r) for r in rows]}
