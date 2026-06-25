"""Spotify OAuth token storage — a single-row SQLite table holding the user's
refresh token plus the latest access token and its expiry. Mirrors the
usage_repo.py / keeper_repo.py conventions (async aiosqlite, data/*.db).

Only one Spotify account is connected at a time (the operator's), so the table
is keyed by a constant id=1.
"""

from __future__ import annotations

import aiosqlite
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_DB = Path(__file__).parent / "data" / "spotify.db"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS spotify_auth (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    refresh_token TEXT NOT NULL,
    access_token  TEXT NOT NULL DEFAULT '',
    expires_at    TEXT NOT NULL DEFAULT '',
    scope         TEXT NOT NULL DEFAULT '',
    updated_at    TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SpotifyRepo:
    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB

    async def init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_SCHEMA)

    async def save_tokens(
        self, refresh_token: str, access_token: str, expires_at: str, scope: str = "",
    ) -> None:
        """Upsert the single auth row. A refresh from Spotify may omit the refresh
        token — callers pass the existing one so it's never lost."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO spotify_auth (id, refresh_token, access_token, expires_at, scope, updated_at) "
                "VALUES (1, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "  refresh_token=excluded.refresh_token, access_token=excluded.access_token, "
                "  expires_at=excluded.expires_at, scope=excluded.scope, updated_at=excluded.updated_at",
                (refresh_token, access_token, expires_at, scope, _now()),
            )
            await db.commit()

    async def get(self) -> dict | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall("SELECT * FROM spotify_auth WHERE id=1")
            return dict(rows[0]) if rows else None

    async def clear(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM spotify_auth WHERE id=1")
            await db.commit()
