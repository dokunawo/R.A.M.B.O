"""Tests for factory repo — tables, transitions, caps, and CRUD."""

import pytest
import pytest_asyncio
from pathlib import Path
from factory.repo import FactoryRepo, State, RESERVED_SLUGS, DAILY_SPAWN_CAP


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = FactoryRepo(db_path=tmp_path / "test_factory.db")
    await r.init_db()
    return r


@pytest.mark.asyncio
async def test_create_and_get_task(repo):
    result = await repo.create_task(
        task_id="t1", name_hint="doc-helper",
        role_description="summarizes docs",
    )
    assert result["status"] == "pending"
    task = await repo.get_task("t1")
    assert task["name_hint"] == "doc-helper"
    assert task["status"] == "pending"


@pytest.mark.asyncio
async def test_valid_transition(repo):
    await repo.create_task(task_id="t2", name_hint="x", role_description="y")
    await repo.transition("t2", State.RESEARCHING)
    task = await repo.get_task("t2")
    assert task["status"] == "researching"


@pytest.mark.asyncio
async def test_invalid_transition_raises(repo):
    await repo.create_task(task_id="t3", name_hint="x", role_description="y")
    with pytest.raises(ValueError, match="Invalid transition"):
        await repo.transition("t3", State.APPROVED)


@pytest.mark.asyncio
async def test_terminal_states_block_transitions(repo):
    await repo.create_task(task_id="t4", name_hint="x", role_description="y")
    await repo.transition("t4", State.FAILED)
    with pytest.raises(ValueError, match="Invalid transition"):
        await repo.transition("t4", State.RESEARCHING)


@pytest.mark.asyncio
async def test_daily_cap(repo):
    for i in range(DAILY_SPAWN_CAP):
        await repo.create_task(
            task_id=f"cap-{i}", name_hint="x", role_description="y",
        )
    with pytest.raises(ValueError, match="cap"):
        await repo.create_task(
            task_id="cap-over", name_hint="x", role_description="y",
        )


@pytest.mark.asyncio
async def test_proposed_manifest_roundtrip(repo):
    await repo.create_task(task_id="t5", name_hint="x", role_description="y")
    manifest = {"slug": "test-agent", "name": "Test", "model": "claude-sonnet-4"}
    await repo.set_proposed_manifest("t5", manifest)
    task = await repo.get_task("t5")
    assert task["proposed_manifest"] == manifest


@pytest.mark.asyncio
async def test_research_report_cache(repo):
    await repo.save_report(
        report_id="r1", query_key="pdf extraction",
        report={"domain": "pdf", "competencies": ["extract text"]},
    )
    cached = await repo.get_cached_report("pdf extraction")
    assert cached is not None
    assert cached["report_json"]["domain"] == "pdf"


@pytest.mark.asyncio
async def test_research_report_cache_miss(repo):
    cached = await repo.get_cached_report("nonexistent query")
    assert cached is None


@pytest.mark.asyncio
async def test_save_and_list_agents(repo):
    agent = {
        "id": "a1", "slug": "doc-helper", "name": "Doc Helper",
        "specialty": "docs", "system_prompt": "You are Doc Helper.",
        "tool_allowlist": ["read_file"], "model": "claude-sonnet-4",
        "status": "active", "created_by_task_id": None,
    }
    await repo.save_agent(agent)
    agents = await repo.list_active_agents()
    assert len(agents) == 1
    assert agents[0]["slug"] == "doc-helper"
    assert agents[0]["tool_allowlist"] == ["read_file"]


@pytest.mark.asyncio
async def test_archive_agent(repo):
    agent = {
        "id": "a2", "slug": "old-bot", "name": "Old Bot",
        "specialty": "nothing", "system_prompt": "You are old.",
        "tool_allowlist": [], "status": "active",
        "created_by_task_id": None,
    }
    await repo.save_agent(agent)
    await repo.archive_agent("old-bot")
    agents = await repo.list_active_agents()
    assert len(agents) == 0


@pytest.mark.asyncio
async def test_slug_uniqueness(repo):
    agent = {
        "id": "a3", "slug": "unique-slug", "name": "A",
        "specialty": "x", "system_prompt": "x",
        "tool_allowlist": [], "status": "active",
        "created_by_task_id": None,
    }
    await repo.save_agent(agent)
    agent2 = {**agent, "id": "a4"}
    with pytest.raises(Exception):
        await repo.save_agent(agent2)


@pytest.mark.asyncio
async def test_list_by_status(repo):
    await repo.create_task(task_id="s1", name_hint="a", role_description="b")
    await repo.create_task(task_id="s2", name_hint="c", role_description="d")
    await repo.transition("s1", State.FAILED)
    pending = await repo.list_by_status(State.PENDING)
    assert len(pending) == 1
    assert pending[0]["id"] == "s2"


@pytest.mark.asyncio
async def test_revision_feedback(repo):
    await repo.create_task(task_id="r1", name_hint="x", role_description="y")
    await repo.set_revision_feedback("r1", "make tone less formal")
    task = await repo.get_task("r1")
    assert task["revision_feedback"] == "make tone less formal"
    assert task["approval_iterations"] == 1


def test_reserved_slugs():
    assert "architect" in RESERVED_SLUGS
    assert "factory" in RESERVED_SLUGS
    assert len(RESERVED_SLUGS) == 13
