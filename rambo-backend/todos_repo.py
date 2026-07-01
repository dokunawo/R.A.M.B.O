from __future__ import annotations

import calendar
import aiosqlite
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

_DEFAULT_DB = Path(__file__).parent / "data" / "todos.db"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS todos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    text         TEXT    NOT NULL,
    priority     TEXT    NOT NULL DEFAULT 'normal',
    status       TEXT    NOT NULL DEFAULT 'open',
    due_date     TEXT,
    recurrence   TEXT,
    created_at   TEXT    NOT NULL,
    completed_at TEXT,
    source       TEXT    NOT NULL DEFAULT 'voice'
);
CREATE INDEX IF NOT EXISTS idx_todos_status ON todos(status, due_date);
"""

_DOW_INDEX = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
              "friday": 4, "saturday": 5, "sunday": 6}
_PRIORITY_RANK = {"high": 0, "normal": 1, "low": 2}


def next_due(due_date: str, recurrence: str) -> str:
    """Next ISO due date after `due_date` per `recurrence` ('daily' | 'weekdays' |
    'weekly:<dow>' | 'monthly'). Unknown recurrence returns `due_date` unchanged
    (defensive — should not happen for values this module writes itself)."""
    d = date.fromisoformat(due_date)
    if recurrence == "daily":
        return (d + timedelta(days=1)).isoformat()
    if recurrence == "weekdays":
        nd = d + timedelta(days=1)
        while nd.weekday() >= 5:
            nd += timedelta(days=1)
        return nd.isoformat()
    if recurrence and recurrence.startswith("weekly:"):
        target = _DOW_INDEX.get(recurrence.split(":", 1)[1])
        if target is None:
            return due_date
        nd = d + timedelta(days=1)
        while nd.weekday() != target:
            nd += timedelta(days=1)
        return nd.isoformat()
    if recurrence == "monthly":
        y, m = d.year, d.month
        y2, m2 = (y, m + 1) if m < 12 else (y + 1, 1)
        last_day = calendar.monthrange(y2, m2)[1]
        return date(y2, m2, min(d.day, last_day)).isoformat()
    return due_date


def _row_to_dict(row) -> dict:
    return {
        "id": row[0], "text": row[1], "priority": row[2], "status": row[3],
        "due_date": row[4], "recurrence": row[5], "created_at": row[6],
        "completed_at": row[7], "source": row[8],
    }


class TodosRepo:
    _COLUMNS = "id, text, priority, status, due_date, recurrence, created_at, completed_at, source"

    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB

    async def init_db(self):
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    async def add(self, text: str, priority: str = "normal", due: str | None = None,
                  recurrence: str | None = None, source: str = "voice") -> dict:
        # A recurring task always needs a rolling anchor date.
        if recurrence and not due:
            due = date.today().isoformat()
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                "INSERT INTO todos (text, priority, status, due_date, recurrence, "
                "created_at, source) VALUES (?, ?, 'open', ?, ?, ?, ?)",
                (text, priority, due, recurrence, now, source),
            )
            await db.commit()
            return await self.get(cur.lastrowid)

    async def get(self, task_id: int) -> dict | None:
        async with aiosqlite.connect(self._db_path) as db:
            row = await (await db.execute(
                f"SELECT {self._COLUMNS} FROM todos WHERE id=?", (task_id,))).fetchone()
            return _row_to_dict(row) if row else None

    async def list_open(self) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as db:
            rows = await db.execute_fetchall(
                f"SELECT {self._COLUMNS} FROM todos WHERE status='open'")
        items = [_row_to_dict(r) for r in rows]
        items.sort(key=lambda t: (
            _PRIORITY_RANK.get(t["priority"], 1),
            t["due_date"] is None,
            t["due_date"] or "",
            t["created_at"],
        ))
        return items

    async def complete(self, task_id: int) -> dict | None:
        task = await self.get(task_id)
        if task is None:
            return None
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE todos SET status='done', completed_at=? WHERE id=?",
                (now, task_id))
            await db.commit()
        if task["recurrence"] and task["due_date"]:
            await self.add(task["text"], priority=task["priority"],
                           due=next_due(task["due_date"], task["recurrence"]),
                           recurrence=task["recurrence"], source=task["source"])
        return await self.get(task_id)

    async def delete(self, task_id: int) -> bool:
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute("DELETE FROM todos WHERE id=?", (task_id,))
            await db.commit()
            return cur.rowcount > 0

    async def due_on_or_before(self, date_str: str) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as db:
            rows = await db.execute_fetchall(
                f"SELECT {self._COLUMNS} FROM todos WHERE status='open' "
                "AND due_date IS NOT NULL AND due_date<=? ORDER BY due_date ASC",
                (date_str,))
        return [_row_to_dict(r) for r in rows]
