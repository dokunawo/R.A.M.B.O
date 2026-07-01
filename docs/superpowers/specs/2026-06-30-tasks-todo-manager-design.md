# R.A.M.B.O Tasks / To-Do Manager — Design

**Date:** 2026-06-30
**Status:** Approved (design)

## Context

R.A.M.B.O has calendar, reminders-as-watchlist, and proactive nudges, but no real
**to-do list** — a place to capture "I need to do X", set a priority/due date, list
what's open, and check things off. This adds that capability, voice-first, surfaced in
the morning brief and as due-today nudges, with a kiosk panel. It closes a genuine gap
(see the capability audit) with no overlap with existing features.

## Goal

Let the operator manage a prioritized to-do list by voice ("add a task…", "what's on my
list", "mark X done"), with optional due dates and recurrence; surface open/overdue tasks
in the Chief-of-Staff brief and as spoken nudges; and show them on a kiosk panel.

## Non-Goals
- No external sync (Notion/Todoist/etc.) — local SQLite only.
- No LLM-based parsing in v1 (deterministic keywords + existing `resolve_temporal`).
- No bet/finance coupling. No multi-user.

## Decisions (from interview)
- **Scope:** full CRUD + priority + due date + **recurrence**.
- **Surfacing:** morning brief **and** due-today/overdue nudges.
- **UI:** voice/REST **and** a kiosk tasks panel.

## Architecture

### 1. Storage — `rambo-backend/tasks_repo.py`
aiosqlite, `data/tasks.db`, mirroring the existing `*_repo.py` pattern (e.g.
`usage_repo.py`). Single table:

```sql
CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    text         TEXT    NOT NULL,
    priority     TEXT    NOT NULL DEFAULT 'normal',   -- high | normal | low
    status       TEXT    NOT NULL DEFAULT 'open',      -- open | done
    due_date     TEXT,                                  -- ISO date (YYYY-MM-DD) | NULL
    recurrence   TEXT,                                  -- NULL | daily | weekdays | weekly:<dow> | monthly
    created_at   TEXT    NOT NULL,
    completed_at TEXT,
    source       TEXT    NOT NULL DEFAULT 'voice'       -- voice | api
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, due_date);
```

`TasksRepo` methods (all async): `init_db`; `add(text, priority='normal', due=None,
recurrence=None, source='voice') -> dict`; `list_open() -> list[dict]` (sorted high→low
priority, then due ascending with nulls last, then created); `get(id)`; `complete(id) ->
dict|None` (sets done + completed_at; if `recurrence`, also inserts the next occurrence
with `due_date` rolled forward by the recurrence rule); `delete(id) -> bool`;
`due_on_or_before(date) -> list[dict]` (open tasks due that date or earlier — for nudges
and the brief).

**Recurrence roll** is a pure helper `next_due(due_date, recurrence) -> str` (next ISO
date): daily +1d; weekdays → next weekday; `weekly:<dow>` → next matching weekday;
monthly → same day next month (clamped to month length). Unit-tested in isolation.

### 2. Skill — `rambo-backend/tasks_skill.py`
Deterministic parser + async runner, registered in `skills.py` `SKILLS`.

- **Intent** (first match wins): *complete* / *delete* / *list* / *add* — keyword sets:
  - add: `add a task`, `new task`, `remind me to`, `i need to`, `i have to`, `put … on my (to-do )?list`, `to-do`/`todo`
  - list: `what'?s on my list`, `my tasks`, `task list`, `what do i need to do`, `to-?do list`
  - complete: `mark … (as )?done`, `complete …`, `finished …`, `check off …`, `i did …`
  - delete: `remove … task`, `delete … task`, `drop … from my list`
- **Field extraction** (add): strip the verb phrase to get the task `text`; priority from
  `urgent|important|high priority` → high, `low priority|whenever|someday` → low; due via
  the existing **`resolve_temporal`** (returns explicit dates for "tomorrow"/"Friday"/…);
  recurrence from `every day|daily`, `weekdays|every weekday`, `every <dow>|weekly`,
  `monthly|every month`.
- **Complete/delete** resolve the target by fuzzy match (case-insensitive substring, then
  closest) against `list_open()`. **No match** → "I don't see a task like that." **Multiple
  matches** → read the candidates back and ask which, rather than guessing.
- **Runner** returns a short spoken-style string (RAMBO voices it through the normal
  pipeline): e.g. add → "Added: call the vet, high priority, due tomorrow." list →
  enumerated open tasks. Empty list → "Nothing on your to-do list."

**Watchlist boundary (no collision):** "keep an eye on X" / "let me know when X is due"
stays the **watchlist** (`_is_watchlist_command` fast-path in `orchestrator.handle`).
Tasks own "task / to-do / my list / I need to / mark … done". This split is documented in
both matchers and covered by a routing test.

### 3. Endpoints — `rambo-backend/api/tasks.py` (router, mounted in `main.py`)
- `GET /tasks` → open tasks (the panel polls this).
- `POST /tasks` `{text, priority?, due?, recurrence?}` → created task.
- `POST /tasks/{id}/complete` → completed (+ next occurrence if recurring).
- `DELETE /tasks/{id}` → deleted.

A single shared `TasksRepo` instance is created at startup (like the other repos) and
`init_db()` is awaited in the existing startup hook.

### 4. Surfacing
- **Brief:** `chief_of_staff_skill` appends an **OPEN TASKS** section — top items by
  priority then due (and a count), pulled from `list_open()`. Best-effort: a repo error
  never breaks the brief.
- **Nudges:** `rambo-backend/tasks_watch.py` mirrors `calendar_watch` — a scheduler that
  once per day (and on the existing poll) speaks **due-today / overdue** open tasks via the
  same nudge delivery path, gated by the existing `proactive_nudges` activity guard and a
  per-day "already notified" set so it doesn't repeat. Started alongside the other
  schedulers in `main.py`.

### 5. Frontend — `rambo-frontend/src/components/TasksPanel.js` (+ `.css`)
A kiosk panel in the existing board aesthetic (gold accent, mono, `t-` class prefix):
open tasks grouped by priority with due/overdue badges and a recurrence mark. Fetches
`GET /tasks` on mount and on a slow interval (e.g. 30s), and **re-fetches immediately** on
a `tasks_changed` WebSocket event emitted by the skill + endpoints after any add/complete/
delete (reusing the existing activity WS the frontend already listens on). Mounted in the
app layout.

### 6. Data flow
```
voice "add a task to call the vet tomorrow, important"
  -> skills match (tasks) -> tasks_skill parse {add, text, high, due} -> TasksRepo.add
  -> spoken confirm via normal voice pipeline ; WS tasks_changed -> TasksPanel refetch
brief / nudge:
  TasksRepo.list_open()/due_on_or_before(today) -> brief section / spoken nudge
```

## Error handling
- Empty list → friendly "nothing on your list", not an error.
- Complete/delete with no/ambiguous match → ask, never act on a guess.
- Unparseable due/recurrence → task created without it (never blocks the add).
- Repo/DB error in brief or nudge path → caught and skipped (never breaks prep/brief).

## Testing
- `tests/test_tasks_repo.py` — CRUD, ordering, `due_on_or_before`, recurrence roll
  (`next_due` for daily/weekdays/weekly/monthly incl. month-length clamp).
- `tests/test_tasks_skill.py` — intent detection, field extraction (priority/due/
  recurrence), fuzzy complete (match / no-match / ambiguous), empty-list message, and the
  watchlist-vs-tasks routing boundary.
- `tests/test_tasks_api.py` — the four endpoints (TestClient).
- Brief section + due-today selection asserted in their tests.
- Frontend: panel verified by the CRA build + a smoke render against `GET /tasks`.

## Conventions
- aiosqlite repo pattern; deterministic parsing; reuse `resolve_temporal`. No new deps.
- Skill = matcher + async runner registered in `SKILLS`. Scheduler mirrors
  `calendar_watch`. Frontend follows the existing board components.

## Future (out of scope)
- LLM-structured parsing for messier phrasings; external sync; snooze/defer; sub-tasks.
