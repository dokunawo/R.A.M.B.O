from __future__ import annotations

import hashlib
import logging
import os
import aiosqlite
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path(__file__).parent / "data" / "dispatch.db"


def _digest_threshold() -> int:
    """Number of completed items above which the completed block is compressed."""
    raw = os.environ.get("RAMBO_DIGEST_THRESHOLD", "6").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 6

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS dispatches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    goal         TEXT    NOT NULL,
    plan         TEXT    NOT NULL DEFAULT '',
    status       TEXT    NOT NULL DEFAULT 'working',
    summary      TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_dispatch_status     ON dispatches(status);
CREATE INDEX IF NOT EXISTS idx_dispatch_updated_at ON dispatches(updated_at DESC);
"""

_DONE = ("completed", "failed")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DispatchRepo:
    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB
        # Optional async digester(text) -> str, wired by the orchestrator (which
        # owns the LLM client). When set, long completed-history blocks are
        # compressed before injection. Cached by a hash of the underlying rows so
        # the LLM call only fires when dispatch state actually changes.
        self._digester = None
        self._digest_cache: tuple[str, str] | None = None  # (rows_hash, digest_text)

    def set_digester(self, digester) -> None:
        """Provide an async callable that compresses a completed-history block."""
        self._digester = digester

    async def init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_SCHEMA)

    async def register(self, goal: str, plan: str = "") -> int:
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                "INSERT INTO dispatches (goal, plan, status, created_at, updated_at) "
                "VALUES (?, ?, 'working', ?, ?)",
                (goal, plan, now, now),
            )
            await db.commit()
            return cur.lastrowid

    async def update_status(self, dispatch_id: int, status: str, summary: str = "") -> None:
        now = _now()
        completed_at = now if status in _DONE else None
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE dispatches SET status=?, summary=?, updated_at=?, completed_at=? "
                "WHERE id=?",
                (status, summary, now, completed_at, dispatch_id),
            )
            await db.commit()

    async def get_active(self) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT * FROM dispatches WHERE status='working' ORDER BY updated_at DESC"
            )
            return [dict(r) for r in rows]

    async def get_recent(self, limit: int = 5) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT * FROM dispatches ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )
            return [dict(r) for r in rows]

    async def get_recent_completed(self, limit: int = 2) -> list[dict]:
        """Most recently completed/failed dispatches, newest first."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT * FROM dispatches WHERE status IN ('completed','failed') "
                "ORDER BY completed_at DESC LIMIT ?",
                (limit,),
            )
            return [dict(r) for r in rows]

    async def format_for_prompt(self) -> str:
        active = await self.get_active()
        threshold = _digest_threshold()
        # Pull a wider completed window only when digestion can collapse it; with
        # no digester wired, behave exactly as before (last 2, raw).
        completed_limit = max(threshold + 2, 2) if self._digester else 2
        completed = await self.get_recent_completed(completed_limit)

        parts: list[str] = []
        if active:
            # Active dispatches stay verbatim — they're operationally important.
            now = datetime.now(timezone.utc)
            lines = []
            for r in active:
                try:
                    created = datetime.fromisoformat(r["created_at"])
                    elapsed = int((now - created).total_seconds())
                    lines.append(f"  - [working] {r['goal']} ({elapsed}s ago)")
                except Exception:
                    lines.append(f"  - [working] {r['goal']}")
            parts.append("CURRENTLY WORKING ON:\n" + "\n".join(lines))

        if completed:
            completed_block = await self._completed_block(completed, threshold)
            if completed_block:
                parts.append(completed_block)
        return "\n".join(parts)

    async def _completed_block(self, completed: list[dict], threshold: int) -> str:
        raw_lines = []
        for r in completed:
            tail = f": {r['summary']}" if r["summary"] else ""
            raw_lines.append(f"  - {r['goal']}{tail}")
        raw = "\n".join(raw_lines)

        # Below threshold, or no digester wired → show the raw recent block.
        if self._digester is None or len(completed) <= threshold:
            return "RECENTLY COMPLETED:\n" + "\n".join(raw_lines[:2])

        rows_hash = hashlib.sha1(raw.encode("utf-8")).hexdigest()
        if self._digest_cache and self._digest_cache[0] == rows_hash:
            return "RECENTLY (digest):\n  " + self._digest_cache[1]

        try:
            digest = await self._digester(raw)
        except Exception:
            logger.exception("Dispatch digest failed — falling back to raw recent")
            return "RECENTLY COMPLETED:\n" + "\n".join(raw_lines[:2])

        digest = (digest or "").strip()
        if not digest:
            return "RECENTLY COMPLETED:\n" + "\n".join(raw_lines[:2])
        self._digest_cache = (rows_hash, digest)
        return "RECENTLY (digest):\n  " + digest
