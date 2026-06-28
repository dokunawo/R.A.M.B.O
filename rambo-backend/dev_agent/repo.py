"""Persistence for RAMBO self-code changes.

One table, `code_changes`, tracking each proposed self-modification from draft
through to its terminal state. Follows the same aiosqlite / CREATE-IF-NOT-EXISTS
pattern as factory/repo.py.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "dev_changes.db"

# Status lifecycle:
#   drafting -> pending_review -> {merged | rejected | escalated}
#   drafting -> failed
STATUSES = ("drafting", "pending_review", "merged", "rejected", "escalated", "failed")

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS code_changes (
    id              TEXT PRIMARY KEY,
    goal            TEXT NOT NULL,
    branch          TEXT,
    worktree_path   TEXT,
    base_branch     TEXT,
    diff            TEXT,
    stat            TEXT,
    impact_json     TEXT,
    recommendation  TEXT,
    summary         TEXT,
    status          TEXT NOT NULL DEFAULT 'drafting',
    error           TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cc_status ON code_changes(status);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DevRepo:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB

    async def init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    async def create(self, change_id: str, goal: str) -> dict:
        ts = _now()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO code_changes (id, goal, status, created_at, updated_at) "
                "VALUES (?, ?, 'drafting', ?, ?)",
                (change_id, goal, ts, ts),
            )
            await db.commit()
        return {"id": change_id, "goal": goal, "status": "drafting"}

    async def set_proposal(self, change_id: str, *, branch: str, worktree_path: str,
                           base_branch: str, diff: str, stat: str,
                           impact: dict) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE code_changes SET branch=?, worktree_path=?, base_branch=?, "
                "diff=?, stat=?, impact_json=?, recommendation=?, summary=?, "
                "status='pending_review', updated_at=? WHERE id=?",
                (branch, worktree_path, base_branch, diff, stat,
                 json.dumps(impact), impact.get("recommendation"),
                 impact.get("summary"), _now(), change_id),
            )
            await db.commit()

    async def set_status(self, change_id: str, status: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE code_changes SET status=?, updated_at=? WHERE id=?",
                (status, _now(), change_id),
            )
            await db.commit()

    async def set_error(self, change_id: str, error: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE code_changes SET status='failed', error=?, updated_at=? WHERE id=?",
                (error, _now(), change_id),
            )
            await db.commit()

    async def get(self, change_id: str) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM code_changes WHERE id=?", (change_id,))
            row = await cur.fetchone()
        return _hydrate(row) if row else None

    async def list_pending(self) -> list[dict]:
        return await self._list_status("pending_review")

    async def list_recent(self, limit: int = 50) -> list[dict]:
        """All self-changes across every status, newest first — for the task-
        history panel's 'Changes' tab."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM code_changes ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )
            rows = await cur.fetchall()
        return [_hydrate(r) for r in rows]

    async def _list_status(self, status: str) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM code_changes WHERE status=? ORDER BY created_at DESC",
                (status,),
            )
            rows = await cur.fetchall()
        return [_hydrate(r) for r in rows]


def _hydrate(row: aiosqlite.Row) -> dict:
    d: dict[str, Any] = dict(row)
    if d.get("impact_json"):
        try:
            d["impact"] = json.loads(d["impact_json"])
        except Exception:
            d["impact"] = None
    else:
        d["impact"] = None
    return d
