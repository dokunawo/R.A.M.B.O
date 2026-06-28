"""Tests for the shutdown farewell + task-history backend pieces."""
import asyncio

import pytest
import pytest_asyncio

import agent_tracker as at
import greeting
from dev_agent.repo import DevRepo


# ── agent_tracker.get_all_recent ──────────────────────────────────────────────
def test_get_all_recent_aggregates_tags_and_orders(monkeypatch):
    at._activity.clear()
    at._stats.clear()
    at._activity["seeker"] = [{"time": "10:00:00", "text": "A", "status": "completed"}]
    at._activity["engineer"] = [{"time": "11:30:00", "text": "B", "status": "pending"}]

    out = at.get_all_recent(limit=10)
    assert [o["text"] for o in out] == ["B", "A"]      # newest first
    assert out[0]["agent"] == "engineer"               # tagged with its agent
    assert out[1]["agent"] == "seeker"


def test_get_all_recent_respects_limit(monkeypatch):
    at._activity.clear()
    at._stats.clear()
    at._activity["seeker"] = [
        {"time": f"10:00:0{i}", "text": str(i), "status": "completed"} for i in range(5)
    ]
    assert len(at.get_all_recent(limit=2)) == 2


# ── DevRepo.list_recent ───────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def repo(tmp_path):
    r = DevRepo(db_path=tmp_path / "dev_changes.db")
    await r.init_db()
    return r


@pytest.mark.asyncio
async def test_list_recent_returns_all_statuses(repo):
    await repo.create("c1", "first change")
    await repo.create("c2", "second change")
    await repo.set_status("c2", "merged")          # different terminal status

    recent = await repo.list_recent(limit=10)
    ids = {r["id"] for r in recent}
    assert ids == {"c1", "c2"}                     # list_pending would miss c2
    statuses = {r["id"]: r["status"] for r in recent}
    assert statuses["c2"] == "merged"


@pytest.mark.asyncio
async def test_list_recent_respects_limit(repo):
    for i in range(4):
        await repo.create(f"c{i}", f"change {i}")
    assert len(await repo.list_recent(limit=2)) == 2


# ── greeting.generate_farewell (template fallback, no LLM) ─────────────────────
class _NoLLMOrch:
    llm = None
    keeper_repo = None


def test_generate_farewell_template_fallback(monkeypatch):
    # No pending facts → clean sign-off; no LLM → deterministic template.
    async def _no_pending(_orch):
        return []
    monkeypatch.setattr("proactive_nudges._pending_parts", _no_pending)

    out = asyncio.run(greeting.generate_farewell(_NoLLMOrch()))
    assert isinstance(out, str) and out
    assert "standby" in out.lower()
    assert ("goodbye" in out.lower() or "good night" in out.lower())
