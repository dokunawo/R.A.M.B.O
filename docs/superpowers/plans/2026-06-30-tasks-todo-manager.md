# R.A.M.B.O To-Do Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give R.A.M.B.O a real, prioritized to-do list — voice add/list/complete/delete with due dates and recurrence, surfaced in the Chief-of-Staff brief and as due-today/overdue nudges, plus a kiosk panel.

**Architecture:** A new `TodosRepo` (aiosqlite, mirrors the existing `*_repo.py` pattern) backs a deterministic `todos_skill.py` (matcher + async runner registered in `skills.py`, no LLM call) and a thin `api/todos.py` REST router. Surfacing reuses two existing patterns verbatim: `chief_of_staff.py` gets a new section, and a new `todos_watch.py` scheduler mirrors `calendar_watch.py`. The frontend adds one self-contained `TodosPanel` dropped into the existing dock rail, polling like every other dock (no new WebSocket wiring).

**Tech Stack:** Python (aiosqlite, stdlib `difflib`/`calendar`/`datetime`), FastAPI, pytest + pytest-asyncio. React (existing kiosk component conventions), no new frontend deps.

## Naming note (found during planning — read before Task 1)

The codebase **already has** a `/tasks/history` route and a `TaskHistoryDock` component for
*dispatched agent tasks* (a completely different concept — the Factory/dev-lane build
queue). To avoid confusion and any route/key collision, this feature is named **"todos"**
throughout: `todos_repo.py`, `todos_skill.py`, `todos_watch.py`, `api/todos.py` (prefix
`/todos`), `TodosPanel`, dock-open key `"todos"`. Nothing about the approved spec's scope
changes — this is a naming clarification only.

## Boundary note — todos vs. the existing watchlist "deadlines"

`orchestrator.py`'s `_run_watchlist` already supports **deadlines** ("remind me the report
is due Friday") — a fact-style, fire-once nudge with no priority/completion/recurrence. This
is intentionally a **different concept** from a to-do list (an actionable checklist you
check off, with priority and recurring items) and is **not being replaced or merged**.
`_is_watchlist_command` runs *before* skill matching in `Orchestrator.handle`, so phrases
containing "is due"/"are due"/"deadline" will always route to the watchlist, never to
todos — this is existing, working behavior, left untouched. The todos skill's own matchers
use different grammar ("add a task", "remind me **to** <verb>", "what's on my list") so the
two features don't compete for the same phrasing. A test in Task 3 pins this interaction so
a future change to either regex has to reconsider it.

## Global Constraints

- No new dependencies. Use aiosqlite (already a project dep) and stdlib only
  (`difflib`, `calendar`, `datetime`).
- Follow the existing `*_repo.py` pattern exactly (see `usage_repo.py`): a class with
  `__init__(self, db_path: str | Path | None = None)`, `async def init_db(self)`, a
  `_SCHEMA` string, `CREATE TABLE IF NOT EXISTS`.
- Follow the existing skill pattern: a matcher `lambda g: ...` + an async
  `run(goal, ctx) -> str`, appended to `SKILLS` in `skills.py`.
- Follow the existing scheduler pattern exactly (see `calendar_watch.py`): an
  `_enabled()`/env-gated `async def X_scheduler(orchestrator)` loop, started via
  `asyncio.create_task` in a `main.py` `@app.on_event("startup")` hook.
- Deterministic parsing only — no LLM calls in `todos_skill.py`.
- Reuse `resolve_temporal` from `temporal.py` for due-date parsing (do not write a new
  date parser).
- Backend tests run from `rambo-backend/`: `./.venv/Scripts/python.exe -m pytest -v <path>`.
  Async tests use `pytest_asyncio.fixture` + `@pytest.mark.asyncio` (see
  `tests/test_usage_repo.py` for the exact convention already in use).
- Frontend: no new CSS framework — reuse the existing dock chrome classes from
  `SharedHUD.css` (`hud-builds-wrap`, `hud-factory-face`, `hud-factory-panel`,
  `hud-factory-panel-header`) for the outer shell; only add new CSS for the
  todo-specific inner rows.
- Commit after every task.

---

### Task 1: `TodosRepo` — storage + recurrence roll

**Files:**
- Create: `rambo-backend/todos_repo.py`
- Test: `rambo-backend/tests/test_todos_repo.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `next_due(due_date: str, recurrence: str) -> str` — module-level pure function.
  - `class TodosRepo`: `__init__(self, db_path=None)`, `async init_db(self)`,
    `async add(self, text: str, priority: str = "normal", due: str | None = None, recurrence: str | None = None, source: str = "voice") -> dict`,
    `async list_open(self) -> list[dict]`,
    `async get(self, task_id: int) -> dict | None`,
    `async complete(self, task_id: int) -> dict | None`,
    `async delete(self, task_id: int) -> bool`,
    `async due_on_or_before(self, date_str: str) -> list[dict]`.
  - Row dict shape (all methods that return rows use this): `{"id": int, "text": str,
    "priority": str, "status": str, "due_date": str | None, "recurrence": str | None,
    "created_at": str, "completed_at": str | None, "source": str}`.

- [ ] **Step 1: Write the failing tests**

```python
# rambo-backend/tests/test_todos_repo.py
import pytest
import pytest_asyncio
import aiosqlite
from datetime import date
from todos_repo import TodosRepo, next_due


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = TodosRepo(db_path=tmp_path / "test_todos.db")
    await r.init_db()
    return r


@pytest.mark.asyncio
async def test_table_exists(repo):
    async with aiosqlite.connect(repo._db_path) as db:
        rows = await db.execute_fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='todos'")
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_init_db_idempotent(tmp_path):
    r = TodosRepo(db_path=tmp_path / "t.db")
    await r.init_db()
    await r.init_db()
    row = await r.add("smoke test")
    assert row["id"] == 1


@pytest.mark.asyncio
async def test_add_defaults(repo):
    row = await repo.add("call the vet")
    assert row["text"] == "call the vet"
    assert row["priority"] == "normal"
    assert row["status"] == "open"
    assert row["due_date"] is None
    assert row["recurrence"] is None
    assert row["source"] == "voice"
    assert row["id"] == 1


@pytest.mark.asyncio
async def test_add_recurring_without_due_defaults_due_to_today(repo):
    row = await repo.add("water plants", recurrence="daily")
    assert row["due_date"] == date.today().isoformat()


@pytest.mark.asyncio
async def test_list_open_orders_by_priority_then_due_then_created(repo):
    await repo.add("low prio", priority="low")
    await repo.add("high prio no due", priority="high")
    await repo.add("high prio due later", priority="high", due="2026-08-01")
    await repo.add("high prio due sooner", priority="high", due="2026-07-01")
    rows = await repo.list_open()
    texts = [r["text"] for r in rows]
    assert texts == [
        "high prio due sooner", "high prio due later", "high prio no due", "low prio",
    ]


@pytest.mark.asyncio
async def test_list_open_excludes_done(repo):
    row = await repo.add("finish this")
    await repo.complete(row["id"])
    assert await repo.list_open() == []


@pytest.mark.asyncio
async def test_get_returns_none_for_missing(repo):
    assert await repo.get(999) is None


@pytest.mark.asyncio
async def test_complete_marks_done_and_stamps_completed_at(repo):
    row = await repo.add("one-off task")
    done = await repo.complete(row["id"])
    assert done["status"] == "done"
    assert done["completed_at"] is not None
    assert await repo.get(row["id"]) == done


@pytest.mark.asyncio
async def test_complete_missing_returns_none(repo):
    assert await repo.complete(999) is None


@pytest.mark.asyncio
async def test_complete_recurring_inserts_next_occurrence(repo):
    row = await repo.add("daily standup", recurrence="daily", due="2026-07-01")
    await repo.complete(row["id"])
    open_rows = await repo.list_open()
    assert len(open_rows) == 1
    assert open_rows[0]["text"] == "daily standup"
    assert open_rows[0]["due_date"] == "2026-07-02"
    assert open_rows[0]["recurrence"] == "daily"


@pytest.mark.asyncio
async def test_delete_removes_task(repo):
    row = await repo.add("to be deleted")
    assert await repo.delete(row["id"]) is True
    assert await repo.get(row["id"]) is None


@pytest.mark.asyncio
async def test_delete_missing_returns_false(repo):
    assert await repo.delete(999) is False


@pytest.mark.asyncio
async def test_due_on_or_before(repo):
    await repo.add("future", due="2026-08-01")
    await repo.add("today", due="2026-07-01")
    await repo.add("overdue", due="2026-06-01")
    await repo.add("no due date")
    rows = await repo.due_on_or_before("2026-07-01")
    texts = {r["text"] for r in rows}
    assert texts == {"today", "overdue"}


# ── next_due (pure, no DB) ──────────────────────────────────────────
def test_next_due_daily():
    assert next_due("2026-07-01", "daily") == "2026-07-02"


def test_next_due_weekdays_skips_weekend():
    # 2026-07-03 is a Friday
    assert next_due("2026-07-03", "weekdays") == "2026-07-06"  # Monday


def test_next_due_weekly_specific_day():
    # 2026-07-01 is a Wednesday; next Friday is 2026-07-03
    assert next_due("2026-07-01", "weekly:friday") == "2026-07-03"


def test_next_due_monthly_clamps_short_month():
    # Jan 31 -> Feb has only 28 days in 2026 (not a leap year)
    assert next_due("2026-01-31", "monthly") == "2026-02-28"


def test_next_due_monthly_normal():
    assert next_due("2026-06-15", "monthly") == "2026-07-15"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd rambo-backend && ./.venv/Scripts/python.exe -m pytest tests/test_todos_repo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'todos_repo'`.

- [ ] **Step 3: Write the implementation**

```python
# rambo-backend/todos_repo.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd rambo-backend && ./.venv/Scripts/python.exe -m pytest tests/test_todos_repo.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/todos_repo.py rambo-backend/tests/test_todos_repo.py
git commit -m "feat(todos): TodosRepo storage + recurrence roll"
```

---

### Task 2: `todos_skill.py` — pure parsing (intent, priority, due, recurrence, fuzzy match)

**Files:**
- Create: `rambo-backend/todos_skill.py`
- Test: `rambo-backend/tests/test_todos_skill.py`

**Interfaces:**
- Consumes: `resolve_temporal` from `rambo-backend/temporal.py` (`resolve_temporal(text: str, now: datetime | None = None) -> list[TemporalRange]`, each with `.start: datetime`).
- Produces (all pure, no I/O):
  - `detect_intent(goal: str) -> str | None` — one of `"add" | "list" | "complete" | "delete"`, or `None`.
  - `extract_priority(text: str) -> str` — `"high" | "normal" | "low"`.
  - `extract_recurrence(text: str, now: date | None = None) -> str | None` — `"daily" | "weekdays" | "weekly:<dow>" | "monthly" | None`.
  - `extract_due(text: str, now: datetime | None = None) -> tuple[str | None, str | None]` — `(due_iso_or_None, matched_phrase_or_None)`.
  - `clean_task_text(intent: str, text: str, due_phrase: str | None = None, priority_phrase: str | None = None) -> str` — the task text with the trigger verb phrase and any matched due/priority substrings stripped.
  - `extract_target_phrase(intent: str, text: str) -> str` — for `"complete"`/`"delete"`, the spoken task-**name** portion with the trigger phrase and any trailing "task"/"from my list" wrapper stripped (via a narrow, non-greedy capture — NOT a blind `re.sub` of the broad intent regex, which can eat the task name itself; see the implementation's docstring for the exact failure case this avoids).
  - `find_match(spoken: str, open_tasks: list[dict]) -> tuple[dict | None, list[dict]]` — `(single_match, candidates)`; exactly one of them is non-empty when a match exists, both empty when nothing matches.

- [ ] **Step 1: Write the failing tests**

```python
# rambo-backend/tests/test_todos_skill.py
from datetime import date, datetime
from todos_skill import (
    detect_intent, extract_priority, extract_recurrence, extract_due,
    clean_task_text, extract_target_phrase, find_match,
)


# ── intent ──────────────────────────────────────────────────────────
def test_detect_intent_add():
    for g in ("add a task to call the vet", "new task: buy milk",
              "remind me to email Sarah", "i need to fix the sink",
              "put buy milk on my list", "put call mom on my to-do list"):
        assert detect_intent(g) == "add", g


def test_detect_intent_list():
    for g in ("what's on my list", "my tasks", "what do i need to do",
              "show me my to-do list"):
        assert detect_intent(g) == "list", g


def test_detect_intent_complete():
    for g in ("mark call the vet as done", "complete buy milk",
              "finished the sink", "check off call mom", "i did the laundry"):
        assert detect_intent(g) == "complete", g


def test_detect_intent_delete():
    for g in ("remove the call the vet task", "delete the buy milk task",
              "drop call mom from my list"):
        assert detect_intent(g) == "delete", g


def test_detect_intent_none_for_unrelated():
    assert detect_intent("what's the weather") is None
    assert detect_intent("what's on my calendar") is None


# ── priority ────────────────────────────────────────────────────────
def test_extract_priority_high():
    assert extract_priority("call the vet, urgent") == "high"
    assert extract_priority("important: renew passport") == "high"


def test_extract_priority_low():
    assert extract_priority("clean the garage whenever") == "low"


def test_extract_priority_default_normal():
    assert extract_priority("call the vet") == "normal"


# ── recurrence ──────────────────────────────────────────────────────
def test_extract_recurrence_daily():
    assert extract_recurrence("water the plants daily") == "daily"
    assert extract_recurrence("check email every day") == "daily"


def test_extract_recurrence_weekdays():
    assert extract_recurrence("stand-up every weekday") == "weekdays"


def test_extract_recurrence_weekly_named_day():
    assert extract_recurrence("trash out every monday") == "weekly:monday"


def test_extract_recurrence_bare_weekly_uses_now():
    now = date(2026, 7, 1)  # a Wednesday
    assert extract_recurrence("team sync weekly", now=now) == "weekly:wednesday"


def test_extract_recurrence_monthly():
    assert extract_recurrence("pay rent monthly") == "monthly"
    assert extract_recurrence("review budget every month") == "monthly"


def test_extract_recurrence_none():
    assert extract_recurrence("call the vet") is None


# ── due (wraps resolve_temporal) ──────────────────────────────────────
def test_extract_due_tomorrow():
    now = datetime(2026, 7, 1, 9, 0, 0)
    due, phrase = extract_due("call the vet tomorrow", now=now)
    assert due == "2026-07-02"
    assert phrase == "tomorrow"


def test_extract_due_none_when_no_date_phrase():
    due, phrase = extract_due("call the vet")
    assert due is None and phrase is None


# ── clean_task_text ─────────────────────────────────────────────────
def test_clean_task_text_strips_add_trigger_and_due_phrase():
    text = clean_task_text("add", "add a task to call the vet tomorrow",
                           due_phrase="tomorrow")
    assert text == "call the vet"


def test_clean_task_text_strips_put_on_my_list_wrapper():
    text = clean_task_text("add", "put buy milk on my to-do list")
    assert text == "buy milk"


def test_clean_task_text_strips_priority_phrase():
    text = clean_task_text("add", "call the vet, urgent", priority_phrase="urgent")
    assert text == "call the vet"


# ── extract_target_phrase ─────────────────────────────────────────────
def test_extract_target_phrase_mark_as_done_wrap():
    assert extract_target_phrase("complete", "mark call the vet as done") == "call the vet"


def test_extract_target_phrase_mark_done_no_as():
    assert extract_target_phrase("complete", "mark buy milk done") == "buy milk"


def test_extract_target_phrase_short_name_not_swallowed_by_trigger():
    # Regression case: a one-word task name ("call") must survive extraction even
    # though the word itself could also satisfy the trigger regex's wildcard.
    assert extract_target_phrase("complete", "mark call as done") == "call"


def test_extract_target_phrase_complete_prefix_forms():
    assert extract_target_phrase("complete", "complete buy milk") == "buy milk"
    assert extract_target_phrase("complete", "finished the sink") == "sink"
    assert extract_target_phrase("complete", "check off call mom") == "call mom"
    assert extract_target_phrase("complete", "i did the laundry") == "laundry"


def test_extract_target_phrase_delete_strips_task_suffix():
    assert extract_target_phrase("delete", "remove the call the vet task") == "call the vet"
    assert extract_target_phrase("delete", "delete the old idea task") == "old idea"


def test_extract_target_phrase_delete_strips_list_suffix():
    assert extract_target_phrase("delete", "drop call mom from my list") == "call mom"


# ── find_match ──────────────────────────────────────────────────────
def _tasks():
    return [
        {"id": 1, "text": "call the vet"},
        {"id": 2, "text": "buy milk"},
        {"id": 3, "text": "call mom about the trip"},
    ]


def test_find_match_single_substring_hit():
    match, candidates = find_match("vet", _tasks())
    assert match["id"] == 1 and candidates == []


def test_find_match_no_hit():
    match, candidates = find_match("clean the garage", _tasks())
    assert match is None and candidates == []


def test_find_match_ambiguous_multiple_substring_hits():
    match, candidates = find_match("call", _tasks())
    assert match is None
    assert {c["id"] for c in candidates} == {1, 3}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd rambo-backend && ./.venv/Scripts/python.exe -m pytest tests/test_todos_skill.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'todos_skill'`.

- [ ] **Step 3: Write the implementation**

```python
# rambo-backend/todos_skill.py
"""Deterministic (no LLM) to-do list skill: add / list / complete / delete, with
priority, due dates (via temporal.resolve_temporal), and recurrence. See the
"Boundary note" in docs/superpowers/plans/2026-06-30-tasks-todo-manager.md for why
this is a distinct concept from the existing watchlist "deadlines"."""
from __future__ import annotations

import difflib
import re
from datetime import date, datetime

from temporal import resolve_temporal

_DOW_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

_ADD_RE = re.compile(
    r"\b(add a task(?: to)?|add task(?: to)?|new task(?: to)?|remind me to|"
    r"i need to|i have to|i've got to|ive got to|put .+ on my (?:to-?do )?list)\b",
    re.IGNORECASE)
_LIST_RE = re.compile(
    r"\b(what'?s on my list|my tasks|task list|to-?do list|what do i need to do|"
    r"what'?s on my to-?do list)\b", re.IGNORECASE)
_COMPLETE_RE = re.compile(
    r"\b(mark .+ (?:as )?done|complete\b|finished\b|check off|i did\b)\b", re.IGNORECASE)
_DELETE_RE = re.compile(
    r"\b(remove .+ task|delete .+ task|drop .+ (?:from my )?list)\b", re.IGNORECASE)

_HIGH_RE = re.compile(r"\b(urgent|important|asap|critical|high priority)\b", re.IGNORECASE)
_LOW_RE = re.compile(r"\b(low priority|whenever|someday|no rush)\b", re.IGNORECASE)

_DAILY_RE = re.compile(r"\b(every ?day|daily)\b", re.IGNORECASE)
_WEEKDAYS_RE = re.compile(r"\b(every ?weekday|weekdays)\b", re.IGNORECASE)
_WEEKLY_NAMED_RE = re.compile(
    r"\bevery (monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.IGNORECASE)
_WEEKLY_BARE_RE = re.compile(r"\b(every ?week|weekly)\b", re.IGNORECASE)
_MONTHLY_RE = re.compile(r"\b(every ?month|monthly)\b", re.IGNORECASE)


def detect_intent(goal: str) -> str | None:
    g = goal or ""
    # Complete/delete/list are checked before add: "add" triggers are broader and
    # some phrasing overlaps ("i need to" vs "i did"), so the more specific,
    # action-on-existing-item intents win first.
    if _COMPLETE_RE.search(g):
        return "complete"
    if _DELETE_RE.search(g):
        return "delete"
    if _LIST_RE.search(g):
        return "list"
    if _ADD_RE.search(g):
        return "add"
    return None


def extract_priority(text: str) -> str:
    if _HIGH_RE.search(text or ""):
        return "high"
    if _LOW_RE.search(text or ""):
        return "low"
    return "normal"


def extract_recurrence(text: str, now: date | None = None) -> str | None:
    t = text or ""
    if _DAILY_RE.search(t):
        return "daily"
    if _WEEKDAYS_RE.search(t):
        return "weekdays"
    m = _WEEKLY_NAMED_RE.search(t)
    if m:
        return f"weekly:{m.group(1).lower()}"
    if _WEEKLY_BARE_RE.search(t):
        dow = _DOW_NAMES[(now or date.today()).weekday()]
        return f"weekly:{dow}"
    if _MONTHLY_RE.search(t):
        return "monthly"
    return None


def extract_due(text: str, now: datetime | None = None) -> tuple[str | None, str | None]:
    ranges = resolve_temporal(text or "", now=now)
    if not ranges:
        return None, None
    r = ranges[0]
    return r.start.date().isoformat(), r.phrase


def clean_task_text(intent: str, text: str, due_phrase: str | None = None,
                    priority_phrase: str | None = None) -> str:
    t = text or ""
    if intent == "add":
        m = re.search(r"put\s+(.+?)\s+on my (?:to-?do )?list", t, re.IGNORECASE)
        if m:
            t = m.group(1)
        else:
            t = _ADD_RE.sub("", t, count=1)
    if due_phrase:
        t = re.sub(re.escape(due_phrase), "", t, flags=re.IGNORECASE)
    if priority_phrase:
        t = re.sub(re.escape(priority_phrase), "", t, flags=re.IGNORECASE)
    t = re.sub(r"^[\s,:.\-]+|[\s,:.\-]+$", "", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t


_COMPLETE_WRAP_RE = re.compile(r"mark\s+(.+?)\s+(?:as\s+)?done\b", re.IGNORECASE)
_COMPLETE_PREFIX_RE = re.compile(
    r"^(?:complete|finished|check off|i did)\s+(?:the\s+)?(.+)$", re.IGNORECASE)
_DELETE_TARGET_RE = re.compile(
    r"^(?:remove|delete|drop)\s+(?:the\s+)?(.+?)"
    r"(?:\s+task|\s+from my (?:to-?do )?list)?$", re.IGNORECASE)


def extract_target_phrase(intent: str, text: str) -> str:
    """The spoken task-NAME portion of a complete/delete utterance, with the
    trigger phrase and any trailing 'task'/'from my list' wrapper stripped.

    Deliberately NOT implemented as re.sub(the broad intent-detection regex, "",
    text): that regex's `.+` wildcard is written to DETECT the intent (it doesn't
    care what it consumes), and blindly substituting it over the whole utterance
    can eat the task name itself. E.g. "mark call as done" — the broad complete
    regex `mark .+ (?:as )?done` matches the ENTIRE string (since "call" can
    satisfy the wildcard just as well as any longer phrase), so re.sub-ing it away
    leaves an EMPTY spoken string — silently breaking fuzzy match / the ambiguous-
    match ask. This function uses a NON-GREEDY, narrowly-scoped capture group
    instead, so "call" is captured, not consumed."""
    t = (text or "").strip()
    if intent == "complete":
        m = _COMPLETE_WRAP_RE.search(t)
        if m:
            return m.group(1).strip()
        m = _COMPLETE_PREFIX_RE.search(t)
        return m.group(1).strip() if m else t
    if intent == "delete":
        m = _DELETE_TARGET_RE.search(t)
        return m.group(1).strip() if m else t
    return t


def find_match(spoken: str, open_tasks: list[dict]) -> tuple[dict | None, list[dict]]:
    """(single_match, candidates). Substring containment first (either direction);
    falls back to a fuzzy close-match. Ambiguous or no hit -> match is None."""
    spoken_l = (spoken or "").lower().strip()
    if not spoken_l:
        return None, []
    contains = [t for t in open_tasks
               if spoken_l in t["text"].lower() or t["text"].lower() in spoken_l]
    if len(contains) == 1:
        return contains[0], []
    if len(contains) > 1:
        return None, contains
    texts = [t["text"] for t in open_tasks]
    close = difflib.get_close_matches(spoken, texts, n=3, cutoff=0.5)
    matches = [t for t in open_tasks if t["text"] in close]
    if len(matches) == 1:
        return matches[0], []
    return None, matches
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd rambo-backend && ./.venv/Scripts/python.exe -m pytest tests/test_todos_skill.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/todos_skill.py rambo-backend/tests/test_todos_skill.py
git commit -m "feat(todos): deterministic parsing (intent, priority, due, recurrence, fuzzy match)"
```

---

### Task 3: `todos_skill.py` — the async skill runner + repo wiring + registration

**Files:**
- Modify: `rambo-backend/todos_skill.py` (append)
- Modify: `rambo-backend/skills.py` (register)
- Test: `rambo-backend/tests/test_todos_skill.py` (append)
- Test: `rambo-backend/tests/test_todos_skill_routing.py`

**Interfaces:**
- Consumes: `TodosRepo` (Task 1), the pure parsers (Task 2).
- Produces:
  - `set_repo(repo) -> None`, `get_repo()` — module-level, same pattern as `dev_agent/builds.py`'s `set_repo`.
  - `async def todos_skill(goal: str, ctx: dict) -> str` — the registered skill runner.
  - `skills.SKILLS` gains one entry `{"name": "todos", "agent": "keeper", "match": ..., "run": todos_skill}`.

- [ ] **Step 1: Write the failing tests (append to test_todos_skill.py, new routing test file)**

```python
# append to rambo-backend/tests/test_todos_skill.py
import pytest
import pytest_asyncio
import todos_skill
from todos_repo import TodosRepo


@pytest_asyncio.fixture
async def wired_repo(tmp_path):
    r = TodosRepo(db_path=tmp_path / "skill_todos.db")
    await r.init_db()
    todos_skill.set_repo(r)
    yield r
    todos_skill.set_repo(None)


@pytest.mark.asyncio
async def test_skill_add_reports_fields(wired_repo):
    out = await todos_skill.todos_skill(
        "add a task to call the vet tomorrow, urgent", {})
    assert "call the vet" in out.lower()
    assert "high" in out.lower() or "urgent" in out.lower()
    rows = await wired_repo.list_open()
    assert len(rows) == 1
    assert rows[0]["text"] == "call the vet"
    assert rows[0]["priority"] == "high"
    assert rows[0]["due_date"] is not None


@pytest.mark.asyncio
async def test_skill_list_empty(wired_repo):
    out = await todos_skill.todos_skill("what's on my list", {})
    assert "nothing" in out.lower()


@pytest.mark.asyncio
async def test_skill_list_shows_open_tasks(wired_repo):
    await wired_repo.add("call the vet")
    await wired_repo.add("buy milk")
    out = await todos_skill.todos_skill("what's on my list", {})
    assert "call the vet" in out.lower()
    assert "buy milk" in out.lower()


@pytest.mark.asyncio
async def test_skill_complete_single_match(wired_repo):
    await wired_repo.add("call the vet")
    out = await todos_skill.todos_skill("mark call the vet as done", {})
    assert "done" in out.lower() or "call the vet" in out.lower()
    assert await wired_repo.list_open() == []


@pytest.mark.asyncio
async def test_skill_complete_no_match(wired_repo):
    out = await todos_skill.todos_skill("mark clean the garage as done", {})
    assert "don't see" in out.lower() or "not" in out.lower()


@pytest.mark.asyncio
async def test_skill_complete_ambiguous_asks(wired_repo):
    await wired_repo.add("call the vet")
    await wired_repo.add("call mom about the trip")
    out = await todos_skill.todos_skill("mark call as done", {})
    assert "which" in out.lower()
    assert len(await wired_repo.list_open()) == 2  # nothing completed on ambiguity


@pytest.mark.asyncio
async def test_skill_delete_removes_task(wired_repo):
    await wired_repo.add("old idea")
    out = await todos_skill.todos_skill("delete the old idea task", {})
    assert "removed" in out.lower() or "old idea" in out.lower()
    assert await wired_repo.list_open() == []


@pytest.mark.asyncio
async def test_skill_no_repo_configured_is_graceful():
    todos_skill.set_repo(None)
    out = await todos_skill.todos_skill("what's on my list", {})
    assert isinstance(out, str) and out  # never raises, always says something
```

```python
# rambo-backend/tests/test_todos_skill_routing.py
from skills import match_skill, SKILLS
from orchestrator.orchestrator import Orchestrator


def test_todos_registered_in_skills():
    assert any(s["name"] == "todos" for s in SKILLS)


def test_todos_matcher_routes_add_list_complete_delete():
    for g in ("add a task to call the vet", "what's on my list",
              "mark call the vet as done", "delete the old idea task"):
        s = match_skill(g)
        assert s is not None and s["name"] == "todos", g


def test_calendar_still_wins_its_own_phrasing():
    s = match_skill("what's on my calendar today")
    assert s is not None and s["name"] == "calendar"


def test_watchlist_still_owns_is_due_phrasing():
    # Documents the boundary from the plan: "is due"/"are due" phrasing is caught
    # by the orchestrator's watchlist fast-path BEFORE skill matching ever runs, so
    # it will never reach the todos skill regardless of how todos' matcher evolves.
    assert Orchestrator._WATCHLIST_RE.search("what tasks are due today")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd rambo-backend && ./.venv/Scripts/python.exe -m pytest tests/test_todos_skill.py tests/test_todos_skill_routing.py -v`
Expected: FAIL — `todos_skill` has no `set_repo`/`todos_skill` function; `SKILLS` has no `"todos"` entry.

- [ ] **Step 3: Write the implementation**

Append to `rambo-backend/todos_skill.py`:

```python
_REPO = None  # set at startup by main.py


def set_repo(repo) -> None:
    global _REPO
    _REPO = repo


def get_repo():
    return _REPO


def _format_task_line(i: int, t: dict) -> str:
    parts = [f"{i}. {t['text']}"]
    if t["priority"] != "normal":
        parts.append(f"({t['priority']})")
    if t["due_date"]:
        parts.append(f"— due {t['due_date']}")
    return " ".join(parts)


async def todos_skill(goal: str, ctx: dict) -> str:
    repo = get_repo()
    if repo is None:
        return "The to-do list isn't available right now."

    intent = detect_intent(goal)

    if intent == "list":
        open_tasks = await repo.list_open()
        if not open_tasks:
            return "Nothing on your to-do list."
        return "Here's your list: " + " ".join(
            _format_task_line(i, t) for i, t in enumerate(open_tasks, 1))

    if intent == "add":
        priority = extract_priority(goal)
        due, due_phrase = extract_due(goal)
        recurrence = extract_recurrence(goal)
        priority_phrase = None
        for rx in (_HIGH_RE, _LOW_RE):
            m = rx.search(goal)
            if m:
                priority_phrase = m.group(0)
                break
        text = clean_task_text("add", goal, due_phrase=due_phrase,
                               priority_phrase=priority_phrase)
        if not text:
            return "I didn't catch what to add — try 'add a task to <what you need to do>'."
        row = await repo.add(text, priority=priority, due=due, recurrence=recurrence)
        parts = [f"Added: {row['text']}."]
        if priority != "normal":
            parts.append(f"Priority: {priority}.")
        if due:
            parts.append(f"Due {due}.")
        if recurrence:
            parts.append(f"Repeats {recurrence}.")
        return " ".join(parts)

    if intent in ("complete", "delete"):
        open_tasks = await repo.list_open()
        spoken = extract_target_phrase(intent, goal)
        match, candidates = find_match(spoken, open_tasks)
        if match is None and candidates:
            names = "; ".join(c["text"] for c in candidates)
            return f"Which one — {names}?"
        if match is None:
            return "I don't see a task like that on your list."
        if intent == "complete":
            done = await repo.complete(match["id"])
            return f"Done: {done['text']}."
        await repo.delete(match["id"])
        return f"Removed: {match['text']}."

    return "I didn't catch a to-do command there."
```

Register in `rambo-backend/skills.py` — add near the other `SKILLS.append(...)` calls
(after the `drive` block, ~line 498), and add the import at the top of the file next to
the other skill imports:

```python
# near the top of skills.py, with the other imports
import todos_skill
from todos_skill import todos_skill as _todos_skill

# appended to the SKILLS list, after the drive skill's SKILLS.append(...) block
SKILLS.append({
    "name": "todos",
    "agent": "keeper",
    "match": lambda g: any(w in g.lower() for w in (
        "add a task", "add task", "new task", "remind me to", "i need to",
        "i have to", "on my list", "on my to-do list", "what's on my list",
        "whats on my list", "my tasks", "task list", "to-do list", "todo list",
        "what do i need to do", "mark", "complete", "finished", "check off",
        "i did", "remove the", "delete the", "drop the",
    )) and todos_skill.detect_intent(g) is not None,
    "run": _todos_skill,
})
```

Note: the `match` lambda does a cheap keyword pre-filter (so unrelated goals never even
call `detect_intent`), then confirms with the real intent detector so `match_skill`
returns `"todos"` only when `todos_skill.detect_intent` actually agrees. This mirrors how
`system_update`'s matcher guards a broad keyword ("an update") against a narrower
false-positive risk.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd rambo-backend && ./.venv/Scripts/python.exe -m pytest tests/test_todos_skill.py tests/test_todos_skill_routing.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/todos_skill.py rambo-backend/skills.py rambo-backend/tests/test_todos_skill.py rambo-backend/tests/test_todos_skill_routing.py
git commit -m "feat(todos): async skill runner + registration in SKILLS"
```

---

### Task 4: REST endpoints — `api/todos.py`

**Files:**
- Create: `rambo-backend/api/todos.py`
- Test: `rambo-backend/tests/test_todos_api.py`

**Interfaces:**
- Consumes: `TodosRepo` (Task 1) via `todos_skill.get_repo()`/`set_repo()` (Task 3) — the
  API reuses the **same shared repo instance** the skill uses (wired once at startup in
  Task 6), so a voice-added task and a panel-added task are the same data.
- Produces: `router = APIRouter(prefix="/todos", tags=["todos"])` with
  `GET /todos`, `POST /todos`, `POST /todos/{id}/complete`, `DELETE /todos/{id}`.

- [ ] **Step 1: Write the failing test**

```python
# rambo-backend/tests/test_todos_api.py
from fastapi import FastAPI
from fastapi.testclient import TestClient
import todos_skill
from todos_repo import TodosRepo
from api.todos import router


def _app(tmp_path):
    app = FastAPI()
    app.include_router(router)
    return app


def _client(tmp_path):
    import asyncio
    repo = TodosRepo(db_path=tmp_path / "api_todos.db")
    asyncio.run(repo.init_db())
    todos_skill.set_repo(repo)
    return TestClient(_app(tmp_path))


def test_get_todos_empty(tmp_path):
    client = _client(tmp_path)
    r = client.get("/todos")
    assert r.status_code == 200
    assert r.json() == []


def test_post_creates_todo(tmp_path):
    client = _client(tmp_path)
    r = client.post("/todos", json={"text": "call the vet", "priority": "high"})
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "call the vet"
    assert body["priority"] == "high"
    assert body["source"] == "api"
    r2 = client.get("/todos")
    assert len(r2.json()) == 1


def test_complete_endpoint(tmp_path):
    client = _client(tmp_path)
    created = client.post("/todos", json={"text": "buy milk"}).json()
    r = client.post(f"/todos/{created['id']}/complete")
    assert r.status_code == 200
    assert r.json()["status"] == "done"
    assert client.get("/todos").json() == []


def test_complete_missing_returns_404(tmp_path):
    client = _client(tmp_path)
    r = client.post("/todos/999/complete")
    assert r.status_code == 404


def test_delete_endpoint(tmp_path):
    client = _client(tmp_path)
    created = client.post("/todos", json={"text": "old idea"}).json()
    r = client.delete(f"/todos/{created['id']}")
    assert r.status_code == 200
    assert client.get("/todos").json() == []


def test_delete_missing_returns_404(tmp_path):
    client = _client(tmp_path)
    r = client.delete("/todos/999")
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rambo-backend && ./.venv/Scripts/python.exe -m pytest tests/test_todos_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.todos'`.

- [ ] **Step 3: Write the implementation**

```python
# rambo-backend/api/todos.py
"""Read/write REST surface for the to-do list, sharing the same TodosRepo instance
the voice skill uses (todos_skill.get_repo()/set_repo()) — a voice-added task and a
panel-added task are the same data."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import todos_skill

router = APIRouter(prefix="/todos", tags=["todos"])


class NewTodo(BaseModel):
    text: str
    priority: str = "normal"
    due: Optional[str] = None
    recurrence: Optional[str] = None


def _repo():
    repo = todos_skill.get_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="Todos repo not configured")
    return repo


@router.get("")
async def list_todos() -> list[dict]:
    return await _repo().list_open()


@router.post("")
async def create_todo(body: NewTodo) -> dict:
    return await _repo().add(body.text, priority=body.priority, due=body.due,
                             recurrence=body.recurrence, source="api")


@router.post("/{task_id}/complete")
async def complete_todo(task_id: int) -> dict:
    row = await _repo().complete(task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return row


@router.delete("/{task_id}")
async def delete_todo(task_id: int) -> dict:
    ok = await _repo().delete(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"deleted": task_id}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd rambo-backend && ./.venv/Scripts/python.exe -m pytest tests/test_todos_api.py -v`
Expected: all PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/api/todos.py rambo-backend/tests/test_todos_api.py
git commit -m "feat(todos): REST endpoints (GET/POST /todos, complete, delete)"
```

---

### Task 5: Wire into `main.py` (repo lifecycle + router mount)

**Files:**
- Modify: `rambo-backend/main.py`
- Test: `rambo-backend/tests/test_main_todos_wiring.py`

**Interfaces:**
- Consumes: `TodosRepo` (Task 1), `todos_skill.set_repo` (Task 3), `api.todos.router` (Task 4).
- Produces: on FastAPI startup, a single shared `TodosRepo` is initialized and handed to
  `todos_skill`; `/todos/*` routes are live on the running app.

- [ ] **Step 1: Write the failing test**

```python
# rambo-backend/tests/test_main_todos_wiring.py
from fastapi.testclient import TestClient
import main


def test_todos_routes_mounted():
    client = TestClient(main.app)
    r = client.get("/todos")
    assert r.status_code == 200   # repo initialized by the startup event


def test_todos_repo_shared_with_skill():
    import todos_skill
    assert todos_skill.get_repo() is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rambo-backend && ./.venv/Scripts/python.exe -m pytest tests/test_main_todos_wiring.py -v`
Expected: FAIL — 404 on `/todos` (router not mounted yet); `todos_skill.get_repo()` is `None`.

- [ ] **Step 3: Write the implementation**

In `rambo-backend/main.py`, add an import near the other repo imports (after
`from spotify_repo import SpotifyRepo`, ~line 44):

```python
from todos_repo import TodosRepo
import todos_skill
```

Add the repo instance near the other module-level repo instances (after
`_transcript_repo = TranscriptRepo()`, ~line 68):

```python
_todos_repo = TodosRepo()
```

Add a startup hook near the other `_init_*` hooks (after `_init_transcript`, ~line 145):

```python
@app.on_event("startup")
async def _init_todos():
    await _todos_repo.init_db()
    todos_skill.set_repo(_todos_repo)
```

Mount the router in the same defensive try/except style as the existing routers
(after the `betting` router block, ~line 94):

```python
try:
    from api.todos import router as _todos_router
    app.include_router(_todos_router)
except Exception as _todos_err:  # pragma: no cover
    print(f"[rambo] todos router not mounted: {_todos_err}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd rambo-backend && ./.venv/Scripts/python.exe -m pytest tests/test_main_todos_wiring.py -v`
Expected: both PASS.

- [ ] **Step 5: Run the full backend suite (regression check)**

Run: `cd rambo-backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: all prior tests still pass, plus the new ones from Tasks 1-5.

- [ ] **Step 6: Commit**

```bash
git add rambo-backend/main.py rambo-backend/tests/test_main_todos_wiring.py
git commit -m "feat(todos): wire TodosRepo + router into main.py startup"
```

---

### Task 6: Chief-of-Staff brief — OPEN TASKS section

**Files:**
- Modify: `rambo-backend/chief_of_staff.py`
- Test: `rambo-backend/tests/test_chief_of_staff_todos.py`

**Interfaces:**
- Consumes: `todos_skill.get_repo()` (Task 3), `TodosRepo.list_open()` (Task 1).
- Produces: `chief_of_staff_skill` output gains an `## OPEN TASKS` section when open
  todos exist; unchanged (no section, no error) when there are none or the repo isn't
  configured.

- [ ] **Step 1: Write the failing test**

```python
# rambo-backend/tests/test_chief_of_staff_todos.py
import pytest
import pytest_asyncio
import todos_skill
from todos_repo import TodosRepo
from chief_of_staff import chief_of_staff_skill

_DOC = """---
type: north-star
target: "$10K/mo"
product: Ops
last_reviewed: 2026-06-01
review_cadence_days: 90
filter: [sales, margin]
---

## Objective
Grow revenue.

## Operating Rules
- Say no to low-margin work.
"""


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = TodosRepo(db_path=tmp_path / "cos_todos.db")
    await r.init_db()
    todos_skill.set_repo(r)
    yield r
    todos_skill.set_repo(None)


@pytest.mark.asyncio
async def test_brief_includes_open_tasks_section(tmp_path, repo, monkeypatch):
    doc = tmp_path / "north-star.md"
    doc.write_text(_DOC, encoding="utf-8")
    monkeypatch.setattr("chief_of_staff.NORTH_STAR_PATHS", [doc])
    await repo.add("call the vet", priority="high")
    out = await chief_of_staff_skill("daily brief", {})
    assert "OPEN TASKS" in out
    assert "call the vet" in out


@pytest.mark.asyncio
async def test_brief_omits_section_when_no_open_tasks(tmp_path, repo, monkeypatch):
    doc = tmp_path / "north-star.md"
    doc.write_text(_DOC, encoding="utf-8")
    monkeypatch.setattr("chief_of_staff.NORTH_STAR_PATHS", [doc])
    out = await chief_of_staff_skill("daily brief", {})
    assert "OPEN TASKS" not in out


@pytest.mark.asyncio
async def test_brief_survives_repo_unconfigured(tmp_path, monkeypatch):
    todos_skill.set_repo(None)
    doc = tmp_path / "north-star.md"
    doc.write_text(_DOC, encoding="utf-8")
    monkeypatch.setattr("chief_of_staff.NORTH_STAR_PATHS", [doc])
    out = await chief_of_staff_skill("daily brief", {})
    assert "OPEN TASKS" not in out
    assert "Daily Revenue Brief" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rambo-backend && ./.venv/Scripts/python.exe -m pytest tests/test_chief_of_staff_todos.py -v`
Expected: FAIL — no `OPEN TASKS` section produced.

- [ ] **Step 3: Write the implementation**

In `rambo-backend/chief_of_staff.py`, add the import at the top:

```python
import todos_skill
```

Modify `chief_of_staff_skill`, inserting a new section right before the final
`brief_parts.append(f"\n---\nDoctrine: ...")` line:

```python
    try:
        repo = todos_skill.get_repo()
        open_tasks = await repo.list_open() if repo else []
    except Exception:
        open_tasks = []
    if open_tasks:
        brief_parts.append("\n## OPEN TASKS")
        for t in open_tasks[:10]:
            line = f"  - {t['text']}"
            if t["priority"] != "normal":
                line += f" ({t['priority']})"
            if t["due_date"]:
                line += f" — due {t['due_date']}"
            brief_parts.append(line)

    brief_parts.append(f"\n---\nDoctrine: {doc_path}  ·  Last reviewed: {fm.get('last_reviewed', 'unknown')}")
```

(Only the new block above `brief_parts.append(f"\n---\nDoctrine: ...")` is added — that
final line already exists and is not duplicated.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd rambo-backend && ./.venv/Scripts/python.exe -m pytest tests/test_chief_of_staff_todos.py -v`
Expected: all PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/chief_of_staff.py rambo-backend/tests/test_chief_of_staff_todos.py
git commit -m "feat(todos): surface open tasks in the Chief-of-Staff brief"
```

---

### Task 7: `todos_watch.py` — due-today/overdue nudge scheduler

**Files:**
- Create: `rambo-backend/todos_watch.py`
- Modify: `rambo-backend/main.py`
- Test: `rambo-backend/tests/test_todos_watch.py`

**Interfaces:**
- Consumes: `todos_skill.get_repo()` (Task 3), `TodosRepo.due_on_or_before()` (Task 1),
  `orchestrator._response` / `orchestrator.broadcast` / `orchestrator._voice_text` (same
  three calls `calendar_watch._deliver` already uses).
- Produces: `compose_nudge(task: dict) -> str`, `async check_once(orchestrator, notified_today: set[int] | None = None, today: str | None = None) -> list[dict]`, `async todos_watch_scheduler(orchestrator) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# rambo-backend/tests/test_todos_watch.py
import pytest
import pytest_asyncio
import todos_skill
from todos_repo import TodosRepo
from todos_watch import compose_nudge, check_once


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = TodosRepo(db_path=tmp_path / "watch_todos.db")
    await r.init_db()
    todos_skill.set_repo(r)
    yield r
    todos_skill.set_repo(None)


class FakeOrchestrator:
    def __init__(self):
        self.responses = []
        self.broadcasts = []
        self.spoken = []

    async def _response(self, agent, msg):
        self.responses.append((agent, msg))

    async def broadcast(self, msg):
        self.broadcasts.append(msg)

    async def _voice_text(self, msg):
        self.spoken.append(msg)


def test_compose_nudge_overdue():
    msg = compose_nudge({"text": "call the vet", "due_date": "2026-06-01"})
    assert "call the vet" in msg


@pytest.mark.asyncio
async def test_check_once_nudges_due_today_and_overdue(repo, monkeypatch):
    monkeypatch.setattr("todos_watch._today_str", lambda: "2026-07-01")
    await repo.add("today task", due="2026-07-01")
    await repo.add("overdue task", due="2026-06-01")
    await repo.add("future task", due="2026-08-01")
    orch = FakeOrchestrator()
    fired = await check_once(orch)
    fired_texts = {t["text"] for t in fired}
    assert fired_texts == {"today task", "overdue task"}
    assert len(orch.spoken) == 2


@pytest.mark.asyncio
async def test_check_once_does_not_renotify_same_day(repo, monkeypatch):
    monkeypatch.setattr("todos_watch._today_str", lambda: "2026-07-01")
    await repo.add("today task", due="2026-07-01")
    orch = FakeOrchestrator()
    notified = set()
    await check_once(orch, notified_today=notified)
    await check_once(orch, notified_today=notified)
    assert len(orch.spoken) == 1


@pytest.mark.asyncio
async def test_check_once_no_repo_is_graceful():
    todos_skill.set_repo(None)
    orch = FakeOrchestrator()
    fired = await check_once(orch)
    assert fired == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rambo-backend && ./.venv/Scripts/python.exe -m pytest tests/test_todos_watch.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'todos_watch'`.

- [ ] **Step 3: Write the implementation**

```python
# rambo-backend/todos_watch.py
"""Proactive to-do nudges: once per calendar day, speak any open task that's due
today or overdue. Mirrors calendar_watch.py's shape and delivery calls exactly.

Env:
  PROACTIVE_TODOS       "on"/"off" — enable the watch loop (default "on")
  TODOS_POLL_SECONDS    how often to poll (default 300)
  TODOS_SPEAK           "on"/"off" — speak the nudge via ElevenLabs (default "on")
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date

import todos_skill

log = logging.getLogger("rambo.todos_watch")

DISPLAY_AGENT = "keeper"


def _enabled() -> bool:
    return os.environ.get("PROACTIVE_TODOS", "on").strip().lower() not in ("off", "0", "false")


def _poll_seconds() -> int:
    try:
        return max(60, int(os.environ.get("TODOS_POLL_SECONDS", "300")))
    except ValueError:
        return 300


def _speak_enabled() -> bool:
    return os.environ.get("TODOS_SPEAK", "on").strip().lower() not in ("off", "0", "false")


def _today_str() -> str:
    return date.today().isoformat()


def compose_nudge(task: dict) -> str:
    due = task.get("due_date") or ""
    today = _today_str()
    when = "is due today" if due == today else f"was due {due}"
    return f'Heads up — "{task["text"]}" {when}.'


async def _deliver(orchestrator, task: dict) -> None:
    msg = compose_nudge(task)
    try:
        await orchestrator._response(DISPLAY_AGENT, msg)
        await orchestrator.broadcast(f"[{DISPLAY_AGENT.capitalize()}] {msg}")
    except Exception:
        log.exception("todo nudge display failed")
    if _speak_enabled():
        try:
            await orchestrator._voice_text(msg)
        except Exception:
            log.exception("todo nudge speech failed")


async def check_once(orchestrator, notified_today: set[int] | None = None,
                     today: str | None = None) -> list[dict]:
    """One poll: nudge any open task due today or overdue that hasn't been
    notified yet TODAY. `notified_today` is cleared by the caller when the date
    rolls over (see the scheduler below) so an overdue task re-nudges once daily."""
    if notified_today is None:
        notified_today = set()
    repo = todos_skill.get_repo()
    if repo is None:
        return []
    today = today or _today_str()
    try:
        due = await repo.due_on_or_before(today)
    except Exception:
        log.exception("todos watch: repo unavailable")
        return []
    fired = []
    for t in due:
        if t["id"] not in notified_today:
            await _deliver(orchestrator, t)
            notified_today.add(t["id"])
            fired.append(t)
    return fired


async def todos_watch_scheduler(orchestrator) -> None:
    """Poll every TODOS_POLL_SECONDS; re-arm the notified set at each new day so a
    still-open overdue task nudges again once daily until completed."""
    if not _enabled():
        log.info("todos watch disabled (PROACTIVE_TODOS=off)")
        return
    notified: set[int] = set()
    last_day = _today_str()
    log.info("todos watch on: poll=%ds", _poll_seconds())
    while True:
        try:
            today = _today_str()
            if today != last_day:
                notified.clear()
                last_day = today
            await check_once(orchestrator, notified, today=today)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("todos watch poll failed")
        await asyncio.sleep(_poll_seconds())
```

Wire the scheduler into `rambo-backend/main.py`: add the import near
`from calendar_watch import calendar_watch_scheduler, ...` (~line 29):

```python
from todos_watch import todos_watch_scheduler
```

Add a task handle near `_calendar_watch_task = None` (~line 148) and a startup hook
next to `_start_calendar_watch` (~line 165):

```python
_todos_watch_task = None


@app.on_event("startup")
async def _start_todos_watch():
    global _todos_watch_task
    _todos_watch_task = asyncio.create_task(todos_watch_scheduler(rambo))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd rambo-backend && ./.venv/Scripts/python.exe -m pytest tests/test_todos_watch.py -v`
Expected: all PASS (4 tests).

- [ ] **Step 5: Run the full backend suite (regression check)**

Run: `cd rambo-backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: all pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add rambo-backend/todos_watch.py rambo-backend/main.py rambo-backend/tests/test_todos_watch.py
git commit -m "feat(todos): due-today/overdue nudge scheduler (mirrors calendar_watch)"
```

---

### Task 8: Frontend — `TodosPanel` kiosk dock

**Files:**
- Create: `rambo-frontend/src/components/TodosPanel.js`
- Create: `rambo-frontend/src/components/TodosPanel.css`
- Modify: `rambo-frontend/src/components/SharedHUD.js` (export `useDockOpen`)
- Modify: `rambo-frontend/src/components/SplashScreen.js` (mount the panel)

**Interfaces:**
- Consumes: `GET /todos` (Task 4/5); `useDockOpen(id: string) -> [isOpen: bool, toggle: () => void]` exported from `SharedHUD.js`.
- Produces: a `<TodosPanel />` component rendered in the existing `hud-dock-rail`.

- [ ] **Step 1: Export `useDockOpen` (one-line change)**

In `rambo-frontend/src/components/SharedHUD.js`, change:

```javascript
function useDockOpen(id) {
```

to:

```javascript
export function useDockOpen(id) {
```

- [ ] **Step 2: Create the panel component**

```javascript
// rambo-frontend/src/components/TodosPanel.js
import React, { useState, useEffect, useCallback } from "react";
import { useDockOpen } from "./SharedHUD";
import "./TodosPanel.css";

const API = "http://localhost:8000";
const POLL_MS = 8000;

function TaskRow({ t }) {
  const overdue = t.due_date && t.due_date < new Date().toISOString().slice(0, 10);
  return (
    <div className={`tp-row tp-prio-${t.priority}`}>
      <span className="tp-dot" />
      <span className="tp-text">{t.text}</span>
      {t.recurrence && <span className="tp-badge tp-badge-recur">↻</span>}
      {t.due_date && (
        <span className={`tp-badge ${overdue ? "tp-badge-overdue" : "tp-badge-due"}`}>
          {t.due_date}
        </span>
      )}
    </div>
  );
}

export default function TodosPanel() {
  const [items, setItems] = useState([]);
  const [open, toggle] = useDockOpen("todos");

  const refresh = useCallback(async () => {
    if (document.hidden) return;
    try {
      const r = await fetch(`${API}/todos`);
      if (r.ok) setItems(await r.json());
    } catch { /* offline — keep showing the last-known list */ }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    const onVis = () => { if (!document.hidden) refresh(); };
    document.addEventListener("visibilitychange", onVis);
    return () => { clearInterval(id); document.removeEventListener("visibilitychange", onVis); };
  }, [refresh]);

  return (
    <div className="hud-builds-wrap">
      <div className="hud-factory-face" onClick={toggle}>
        <span className="hud-builds-tag">TO-DO</span>
        <span className={`hud-factory-count ${items.length ? "hud-count-hot" : ""}`}>
          {items.length}
        </span>
      </div>
      {open && (
        <div className="hud-factory-panel tp-panel">
          <div className="hud-factory-panel-header hud-dock-header">
            <span>◆ OPEN TASKS</span>
          </div>
          {items.length === 0
            ? <div className="hud-factory-empty">{"// nothing on your list"}</div>
            : items.map(t => <TaskRow key={t.id} t={t} />)}
        </div>
      )}
    </div>
  );
}
```

```css
/* rambo-frontend/src/components/TodosPanel.css */
.tp-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.tp-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-family: var(--mono, "JetBrains Mono", monospace);
  font-size: 12px;
  color: #d8d8d8;
}

.tp-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
  background: #6b7280;
}

.tp-prio-high .tp-dot { background: #ff4466; }
.tp-prio-normal .tp-dot { background: var(--accent, #e8b15a); }
.tp-prio-low .tp-dot { background: #6b7280; }

.tp-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tp-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  flex-shrink: 0;
}

.tp-badge-due { color: #9ca3af; }
.tp-badge-overdue { color: #ff4466; border-color: rgba(255, 68, 102, 0.4); }
.tp-badge-recur { color: var(--accent-glow, #ffd98a); }
```

- [ ] **Step 3: Write a smoke test (CRA already ships Jest + Testing Library — no new deps)**

```javascript
// rambo-frontend/src/components/TodosPanel.test.js
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import TodosPanel from "./TodosPanel";

beforeEach(() => {
  global.fetch = jest.fn(() =>
    Promise.resolve({
      ok: true,
      json: () => Promise.resolve([
        { id: 1, text: "call the vet", priority: "high", status: "open",
          due_date: null, recurrence: null, created_at: "x",
          completed_at: null, source: "voice" },
      ]),
    })
  );
});

afterEach(() => { jest.resetAllMocks(); });

test("renders the open-task count from GET /todos", async () => {
  render(<TodosPanel />);
  await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());
});

test("clicking the dock face expands and shows the task text", async () => {
  render(<TodosPanel />);
  await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());
  fireEvent.click(screen.getByText("TO-DO").closest(".hud-factory-face"));
  await waitFor(() => expect(screen.getByText("call the vet")).toBeInTheDocument());
});
```

Run: `cd rambo-frontend && CI=true npx react-scripts test src/components/TodosPanel.test.js --watchAll=false`
Expected: both tests PASS.

- [ ] **Step 4: Mount the panel**

In `rambo-frontend/src/components/SplashScreen.js`, add the import next to
`import SpotifyWidget from "./SpotifyWidget";` (~line 21):

```javascript
import TodosPanel from "./TodosPanel";
```

Add `<TodosPanel />` inside the existing `hud-dock-rail` div, next to the other docks
(after `<TaskHistoryDock />`, ~line 1373):

```jsx
            <TaskHistoryDock />
            <TodosPanel />
```

- [ ] **Step 5: Verify the build**

Run: `cd rambo-frontend && npm run build`
Expected: build succeeds with no new errors — a real compile check across every
JS/JSX file changed in this task, on top of the RTL smoke test in Step 3.

- [ ] **Step 6: Commit**

```bash
git add rambo-frontend/src/components/TodosPanel.js rambo-frontend/src/components/TodosPanel.css rambo-frontend/src/components/TodosPanel.test.js rambo-frontend/src/components/SharedHUD.js rambo-frontend/src/components/SplashScreen.js
git commit -m "feat(todos): TodosPanel kiosk dock"
```

---

### Task 9: Full-suite regression + finish

**Files:** none (verification only).

- [ ] **Step 1: Run the whole backend suite**

Run: `cd rambo-backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: all tests pass (baseline + every test added in Tasks 1-7). Investigate any
failure before proceeding — do not edit unrelated tests to force a pass.

- [ ] **Step 2: Live sanity-check (best effort, needs the backend running)**

```bash
curl -s -X POST http://localhost:8000/todos -H "Content-Type: application/json" \
  -d '{"text":"smoke test task","priority":"high"}'
curl -s http://localhost:8000/todos
```
Expected: the POST returns the created task (id, priority "high"); the GET lists it.
Clean up with `curl -X DELETE http://localhost:8000/todos/<id>`.

- [ ] **Step 3: Confirm clean tree + push branch**

```bash
git status -s
git push -u origin feat/tasks-todo
```

- [ ] **Step 4: Open the PR**

```bash
gh pr create --base main --head feat/tasks-todo --title "To-do manager: voice add/list/complete/delete, brief + nudges, kiosk panel" --body "$(cat <<'EOF'
Adds a real prioritized to-do list to R.A.M.B.O.

- TodosRepo (aiosqlite) — CRUD + priority + due date + recurrence (daily/weekdays/weekly:<dow>/monthly), with a tested recurrence roll
- todos_skill.py — deterministic voice parsing (add/list/complete/delete), reuses temporal.resolve_temporal for dates; fuzzy-matches on complete/delete and asks when ambiguous
- api/todos.py — REST endpoints shared with the voice skill (same TodosRepo instance)
- Chief-of-Staff brief gains an OPEN TASKS section; a new todos_watch scheduler (mirrors calendar_watch) speaks due-today/overdue nudges once per day
- TodosPanel kiosk dock, polling like every other dock (no new WS plumbing)

Named "todos" (not "tasks") throughout to avoid confusion with the existing /tasks/history
dispatched-agent-task dock. Deliberately kept distinct from the existing watchlist
"deadlines" feature — see the plan's boundary note; a test pins that "is due"/"are due"
phrasing still routes to the watchlist, unaffected by this change.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Notes for the implementer

- `todos_skill.py`'s module-level `_REPO` is the single shared instance between the
  voice skill (Task 3) and the REST API (Task 4) and the brief (Task 6) and the nudge
  scheduler (Task 7) — all reach it via `todos_skill.get_repo()`. `main.py` (Task 5) is
  the only place that calls `set_repo()`.
- The frontend panel intentionally uses **polling only** (matching every existing dock
  in `SharedHUD.js` — `HistoryDock`, `TaskHistoryDock`, `BuildsDock`, etc. all poll, none
  push over WebSocket for their own data). This is a deliberate, lower-risk choice versus
  the original design sketch's WebSocket-push idea: it avoids new orchestrator-to-skill
  plumbing and an 8s staleness window is imperceptible for a to-do list.
- Do not modify `_run_watchlist` or `_WATCHLIST_RE` in `orchestrator/orchestrator.py` —
  that's the existing, working deadline feature and is out of scope (see the boundary
  note at the top of this plan).
