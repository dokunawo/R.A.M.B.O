"""Local ElevenLabs character-usage log.

Records how many characters R.A.M.B.O sent to ElevenLabs per synth so the HUD can
show month-to-date voice-credit usage without needing the User:Read permission on
the API key. Mirrors usage_repo.py conventions (async aiosqlite, data/*.db).
"""

from __future__ import annotations

import aiosqlite
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_DB = Path(__file__).parent / "data" / "tts_usage.db"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS tts_usage (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    characters INTEGER NOT NULL DEFAULT 0,
    model      TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tts_usage_created_at ON tts_usage(created_at);
"""


class TTSUsageRepo:
    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB

    async def init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_SCHEMA)

    async def record(self, characters: int, model: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO tts_usage (characters, model, created_at) VALUES (?, ?, ?)",
                (int(characters), model, now),
            )
            await db.commit()

    async def characters_since(self, start: str, end: str | None = None) -> int:
        end = end or datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            rows = await db.execute_fetchall(
                "SELECT COALESCE(SUM(characters), 0) FROM tts_usage "
                "WHERE created_at >= ? AND created_at <= ?",
                (start, end),
            )
            return int(rows[0][0]) if rows else 0
