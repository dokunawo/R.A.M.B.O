"""Persistence layer for the Factory sub-agent spawner.

Three tables: spawn_tasks, spawned_agents, research_reports.
Follows the same CREATE-TABLE-IF-NOT-EXISTS pattern as usage_repo.py.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "factory.db"


class State(str, Enum):
    PENDING = "pending"
    RESEARCHING = "researching"
    DRAFTING_SPEC = "drafting_spec"
    WRITING_PROMPT = "writing_prompt"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


_TRANSITIONS: dict[State, set[State]] = {
    State.PENDING:            {State.RESEARCHING, State.FAILED},
    State.RESEARCHING:        {State.DRAFTING_SPEC, State.FAILED},
    State.DRAFTING_SPEC:      {State.WRITING_PROMPT, State.FAILED},
    State.WRITING_PROMPT:     {State.AWAITING_APPROVAL, State.FAILED},
    State.AWAITING_APPROVAL:  {State.APPROVED, State.REJECTED,
                               State.WRITING_PROMPT, State.FAILED},
    State.APPROVED:           set(),
    State.REJECTED:           set(),
    State.FAILED:             set(),
}

RESERVED_SLUGS = frozenset({
    "architect", "engineer", "seeker", "analyst", "sentinel",
    "steward", "link", "keeper", "echo", "pilot",
    "rambo", "overseer", "factory",
})

DAILY_SPAWN_CAP = 5

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS research_reports (
    id              TEXT PRIMARY KEY,
    query_key       TEXT NOT NULL,
    report_json     TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rr_query ON research_reports(query_key);

CREATE TABLE IF NOT EXISTS spawn_tasks (
    id                  TEXT PRIMARY KEY,
    requested_by        TEXT NOT NULL DEFAULT 'operator',
    name_hint           TEXT NOT NULL,
    role_description    TEXT NOT NULL,
    special_requirements TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'pending',
    research_report_id  TEXT,
    proposed_manifest   TEXT,
    approval_iterations INTEGER NOT NULL DEFAULT 0,
    revision_feedback   TEXT,
    error               TEXT,
    created_at          TEXT NOT NULL,
    FOREIGN KEY (research_report_id) REFERENCES research_reports(id)
);
CREATE INDEX IF NOT EXISTS idx_st_status ON spawn_tasks(status);
CREATE INDEX IF NOT EXISTS idx_st_created ON spawn_tasks(created_at);

CREATE TABLE IF NOT EXISTS spawned_agents (
    id                  TEXT PRIMARY KEY,
    slug                TEXT NOT NULL UNIQUE,
    name                TEXT NOT NULL,
    specialty           TEXT NOT NULL,
    system_prompt       TEXT NOT NULL,
    tool_allowlist      TEXT NOT NULL DEFAULT '[]',
    model               TEXT NOT NULL DEFAULT 'claude-sonnet-4-6',
    status              TEXT NOT NULL DEFAULT 'active',
    created_by_task_id  TEXT,
    created_at          TEXT NOT NULL,
    FOREIGN KEY (created_by_task_id) REFERENCES spawn_tasks(id)
);
"""


class FactoryRepo:
    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB

    async def init_db(self):
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_SCHEMA)

    # ── spawn tasks ──────────────────────────────────────────────

    async def create_task(
        self, *, task_id: str, name_hint: str, role_description: str,
        special_requirements: str = "", requested_by: str = "operator",
    ) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0,
        ).isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            row = await db.execute_fetchall(
                "SELECT COUNT(*) FROM spawn_tasks "
                "WHERE requested_by = ? AND created_at >= ?",
                (requested_by, today_start),
            )
            if row[0][0] >= DAILY_SPAWN_CAP:
                raise ValueError(
                    f"Daily spawn cap ({DAILY_SPAWN_CAP}) reached for {requested_by}"
                )
            await db.execute(
                "INSERT INTO spawn_tasks "
                "(id, requested_by, name_hint, role_description, "
                "special_requirements, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (task_id, requested_by, name_hint, role_description,
                 special_requirements, State.PENDING.value, now),
            )
            await db.commit()
        return {"id": task_id, "status": State.PENDING.value}

    async def get_task(self, task_id: str) -> dict | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT * FROM spawn_tasks WHERE id = ?", (task_id,),
            )
            if not rows:
                return None
            d = dict(rows[0])
            if d.get("proposed_manifest"):
                d["proposed_manifest"] = json.loads(d["proposed_manifest"])
            return d

    async def transition(self, task_id: str, new_state: State) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT status FROM spawn_tasks WHERE id = ?", (task_id,),
            )
            if not rows:
                raise ValueError(f"Task {task_id} not found")
            current = State(rows[0]["status"])
            if new_state not in _TRANSITIONS[current]:
                raise ValueError(
                    f"Invalid transition {current.value} → {new_state.value}"
                )
            await db.execute(
                "UPDATE spawn_tasks SET status = ? WHERE id = ?",
                (new_state.value, task_id),
            )
            await db.commit()

    async def set_research_report(self, task_id: str, report_id: str) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE spawn_tasks SET research_report_id = ? WHERE id = ?",
                (report_id, task_id),
            )
            await db.commit()

    async def set_proposed_manifest(self, task_id: str, manifest: dict) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE spawn_tasks SET proposed_manifest = ? WHERE id = ?",
                (json.dumps(manifest), task_id),
            )
            await db.commit()

    async def set_error(self, task_id: str, error: str) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE spawn_tasks SET error = ? WHERE id = ?",
                (error, task_id),
            )
            await db.commit()

    async def set_revision_feedback(
        self, task_id: str, feedback: str,
    ) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE spawn_tasks SET revision_feedback = ?, "
                "approval_iterations = approval_iterations + 1 WHERE id = ?",
                (feedback, task_id),
            )
            await db.commit()

    async def list_by_status(self, status: State) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT * FROM spawn_tasks WHERE status = ? "
                "ORDER BY created_at DESC",
                (status.value,),
            )
            result = []
            for r in rows:
                d = dict(r)
                if d.get("proposed_manifest"):
                    d["proposed_manifest"] = json.loads(d["proposed_manifest"])
                result.append(d)
            return result

    # ── research reports ─────────────────────────────────────────

    async def save_report(
        self, *, report_id: str, query_key: str, report: dict,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO research_reports "
                "(id, query_key, report_json, created_at) VALUES (?, ?, ?, ?)",
                (report_id, query_key, json.dumps(report), now),
            )
            await db.commit()

    async def get_cached_report(self, query_key: str, max_age_hours: int = 24) -> dict | None:
        cutoff = datetime.now(timezone.utc)
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT * FROM research_reports "
                "WHERE query_key = ? ORDER BY created_at DESC LIMIT 1",
                (query_key,),
            )
            if not rows:
                return None
            r = dict(rows[0])
            created = datetime.fromisoformat(r["created_at"])
            age_hours = (cutoff - created).total_seconds() / 3600
            if age_hours > max_age_hours:
                return None
            r["report_json"] = json.loads(r["report_json"])
            return r

    # ── spawned agents ───────────────────────────────────────────

    async def save_agent(self, agent: dict) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO spawned_agents "
                "(id, slug, name, specialty, system_prompt, tool_allowlist, "
                "model, status, created_by_task_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    agent["id"], agent["slug"], agent["name"],
                    agent["specialty"], agent["system_prompt"],
                    json.dumps(agent.get("tool_allowlist", [])),
                    agent.get("model", "claude-sonnet-4-6"),
                    agent.get("status", "active"),
                    agent.get("created_by_task_id"),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()

    async def list_active_agents(self) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT * FROM spawned_agents WHERE status = 'active' ORDER BY slug",
            )
            result = []
            for r in rows:
                d = dict(r)
                d["tool_allowlist"] = json.loads(d["tool_allowlist"])
                result.append(d)
            return result

    async def get_agent_by_slug(self, slug: str) -> dict | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT * FROM spawned_agents WHERE slug = ?", (slug,),
            )
            if not rows:
                return None
            d = dict(rows[0])
            d["tool_allowlist"] = json.loads(d["tool_allowlist"])
            return d

    async def archive_agent(self, slug: str) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE spawned_agents SET status = 'archived' WHERE slug = ?",
                (slug,),
            )
            await db.commit()
