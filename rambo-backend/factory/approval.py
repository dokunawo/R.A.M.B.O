"""Tier 4 — Approval gate.

Approve or reject proposed agents. Rejection with feedback re-runs
prompt generation (capped at MAX_REVISIONS). Approval inserts a row
into spawned_agents and notifies the registry watcher.
"""

from __future__ import annotations

import logging
import uuid

from factory.repo import FactoryRepo, State

logger = logging.getLogger(__name__)

MAX_REVISIONS = 3


async def handle_approve(
    *,
    task_id: str,
    repo: FactoryRepo,
    notify_registry=None,
    emit_event=None,
) -> dict:
    task = await repo.get_task(task_id)
    if task is None:
        raise ValueError(f"Task {task_id} not found")
    if task["status"] != State.AWAITING_APPROVAL.value:
        raise ValueError(f"Task not in approvable state (is {task['status']})")

    p = task["proposed_manifest"]
    agent = {
        "id": uuid.uuid4().hex,
        "slug": p["slug"],
        "name": p["name"],
        "specialty": p["specialty"],
        "system_prompt": p["system_prompt"],
        "tool_allowlist": p.get("tool_allowlist", []),
        "model": p.get("model", "claude-sonnet-4-20250514"),
        "status": "active",
        "created_by_task_id": task_id,
    }
    await repo.save_agent(agent)
    await repo.transition(task_id, State.APPROVED)

    if notify_registry:
        await notify_registry(agent["slug"])

    if emit_event:
        emit_event(kind="agent_added", event={
            "slug": agent["slug"],
            "name": agent["name"],
            "created_by_task_id": task_id,
        })

    logger.info("Approved agent '%s' (slug=%s)", agent["name"], agent["slug"])
    return {"status": "approved", "slug": agent["slug"]}


async def handle_reject(
    *,
    task_id: str,
    repo: FactoryRepo,
    feedback: str | None = None,
    pipeline=None,
    emit_event=None,
) -> dict:
    task = await repo.get_task(task_id)
    if task is None:
        raise ValueError(f"Task {task_id} not found")
    if task["status"] != State.AWAITING_APPROVAL.value:
        raise ValueError(f"Task not in rejectable state (is {task['status']})")

    if not feedback:
        await repo.transition(task_id, State.REJECTED)
        if emit_event:
            emit_event(kind="factory_update", event={
                "task_id": task_id, "status": "rejected",
            })
        return {"status": "rejected", "task_id": task_id}

    if task["approval_iterations"] >= MAX_REVISIONS:
        await repo.set_error(task_id, f"Max revisions ({MAX_REVISIONS}) exceeded")
        await repo.transition(task_id, State.FAILED)
        return {"status": "failed", "reason": "max_revisions_exceeded"}

    await repo.set_revision_feedback(task_id, feedback)
    await repo.transition(task_id, State.WRITING_PROMPT)

    if pipeline:
        await pipeline.run_revision(task_id)

    return {"status": "revision_requested", "iteration": task["approval_iterations"] + 1}
