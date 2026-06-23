"""Tests for Tier 4 — Approval gate."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from factory.repo import FactoryRepo, State
from factory.approval import handle_approve, handle_reject, MAX_REVISIONS


MANIFEST = {
    "slug": "test-bot",
    "name": "Test Bot",
    "specialty": "testing",
    "system_prompt": "You are Test Bot.",
    "tool_allowlist": ["read_file"],
    "model": "claude-sonnet-4-6",
}


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = FactoryRepo(db_path=tmp_path / "test.db")
    await r.init_db()
    return r


async def _create_approvable_task(repo, task_id="t1"):
    await repo.create_task(
        task_id=task_id, name_hint="Test Bot",
        role_description="A test bot",
    )
    await repo.transition(task_id, State.RESEARCHING)
    await repo.transition(task_id, State.DRAFTING_SPEC)
    await repo.transition(task_id, State.WRITING_PROMPT)
    await repo.set_proposed_manifest(task_id, MANIFEST)
    await repo.transition(task_id, State.AWAITING_APPROVAL)


@pytest.mark.asyncio
async def test_approve_creates_agent(repo):
    await _create_approvable_task(repo)
    result = await handle_approve(task_id="t1", repo=repo)
    assert result["status"] == "approved"
    assert result["slug"] == "test-bot"

    agents = await repo.list_active_agents()
    assert len(agents) == 1
    assert agents[0]["slug"] == "test-bot"
    assert agents[0]["created_by_task_id"] == "t1"

    task = await repo.get_task("t1")
    assert task["status"] == "approved"


@pytest.mark.asyncio
async def test_approve_emits_event(repo):
    await _create_approvable_task(repo)
    events = []
    await handle_approve(
        task_id="t1", repo=repo,
        emit_event=lambda **kw: events.append(kw),
    )
    assert len(events) == 1
    assert events[0]["kind"] == "agent_added"
    assert events[0]["event"]["created_by_task_id"] == "t1"


@pytest.mark.asyncio
async def test_approve_calls_notify_registry(repo):
    await _create_approvable_task(repo)
    notify = AsyncMock()
    await handle_approve(task_id="t1", repo=repo, notify_registry=notify)
    notify.assert_called_once_with("test-bot")


@pytest.mark.asyncio
async def test_approve_wrong_state_raises(repo):
    await repo.create_task(task_id="t2", name_hint="X", role_description="Y")
    with pytest.raises(ValueError, match="not in approvable"):
        await handle_approve(task_id="t2", repo=repo)


@pytest.mark.asyncio
async def test_reject_no_feedback_terminal(repo):
    await _create_approvable_task(repo, "t3")
    result = await handle_reject(task_id="t3", repo=repo)
    assert result["status"] == "rejected"
    task = await repo.get_task("t3")
    assert task["status"] == "rejected"


@pytest.mark.asyncio
async def test_reject_with_feedback_triggers_revision(repo):
    await _create_approvable_task(repo, "t4")
    result = await handle_reject(
        task_id="t4", repo=repo, feedback="make it friendlier",
    )
    assert result["status"] == "revision_requested"
    assert result["iteration"] == 1
    task = await repo.get_task("t4")
    assert task["status"] == "writing_prompt"
    assert task["revision_feedback"] == "make it friendlier"


@pytest.mark.asyncio
async def test_reject_max_revisions_fails(repo):
    await _create_approvable_task(repo, "t5")
    # Simulate having already used all revision attempts
    for i in range(MAX_REVISIONS):
        await repo.set_revision_feedback("t5", f"feedback {i}")

    task = await repo.get_task("t5")
    assert task["approval_iterations"] >= MAX_REVISIONS

    # Task is still in awaiting_approval from _create_approvable_task
    result = await handle_reject(
        task_id="t5", repo=repo, feedback="one more try",
    )
    assert result["status"] == "failed"
    assert result["reason"] == "max_revisions_exceeded"


@pytest.mark.asyncio
async def test_reject_not_found_raises(repo):
    with pytest.raises(ValueError, match="not found"):
        await handle_reject(task_id="nonexistent", repo=repo)
