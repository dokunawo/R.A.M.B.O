"""Persistence for standalone projects RAMBO builds (the `builds/` folder).

Distinct from `dev_agent/repo.py` (which tracks self-edits to RAMBO's own code):
this tracks NEW standalone apps/scripts the operator asked RAMBO to build, which
land in `<repo>/builds/<slug>/` and are opened on the desktop rather than merged.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "builds.db"

STATUSES = ("building", "ready", "failed")

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS builds (
    id          TEXT PRIMARY KEY,
    slug        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    goal        TEXT NOT NULL,
    rel_path    TEXT,
    host_path   TEXT,
    files_json  TEXT,
    summary     TEXT,
    status      TEXT NOT NULL DEFAULT 'building',
    error       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BuildsRepo:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB

    async def init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    async def create(self, build_id: str, slug: str, name: str, goal: str) -> dict:
        ts = _now()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO builds (id, slug, name, goal, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'building', ?, ?)",
                (build_id, slug, name, goal, ts, ts),
            )
            await db.commit()
        return {"id": build_id, "slug": slug, "status": "building"}

    async def set_ready(self, slug: str, *, rel_path: str, host_path: str,
                        files: list[str], summary: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE builds SET rel_path=?, host_path=?, files_json=?, summary=?, "
                "status='ready', updated_at=? WHERE slug=?",
                (rel_path, host_path, json.dumps(files), summary, _now(), slug),
            )
            await db.commit()

    async def set_error(self, slug: str, error: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE builds SET status='failed', error=?, updated_at=? WHERE slug=?",
                (error, _now(), slug),
            )
            await db.commit()

    async def get_by_slug(self, slug: str) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM builds WHERE slug=?", (slug,))
            row = await cur.fetchone()
        return _hydrate(row) if row else None

    async def slug_taken(self, slug: str) -> bool:
        return (await self.get_by_slug(slug)) is not None

    async def list_all(self) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM builds ORDER BY created_at DESC")
            rows = await cur.fetchall()
        return [_hydrate(r) for r in rows]

    async def delete(self, slug: str) -> None:
        """Remove a build's DB record. Does NOT touch files on disk — the project
        folder under builds/<slug>/ stays put; only the dock entry goes away."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM builds WHERE slug=?", (slug,))
            await db.commit()

    async def delete_all(self) -> int:
        """Remove all build DB records (dock entries). Files on disk are kept.
        Returns the number of records removed."""
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM builds")
            (n,) = await cur.fetchone()
            await db.execute("DELETE FROM builds")
            await db.commit()
        return int(n)


def _hydrate(row: aiosqlite.Row) -> dict:
    d: dict[str, Any] = dict(row)
    if d.get("files_json"):
        try:
            d["files"] = json.loads(d["files_json"])
        except Exception:
            d["files"] = []
    else:
        d["files"] = []
    return d
