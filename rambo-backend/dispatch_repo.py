from __future__ import annotations

import aiosqlite
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_DB = Path(__file__).parent / "data" / "dispatch.db"

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
        completed = await self.get_recent_completed(2)

        parts: list[str] = []
        if active:
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
            lines = []
            for r in completed:
                tail = f": {r['summary']}" if r["summary"] else ""
                lines.append(f"  - {r['goal']}{tail}")
            parts.append("RECENTLY COMPLETED:\n" + "\n".join(lines))
        return "\n".join(parts)
