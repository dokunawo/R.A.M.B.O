"""Tests for durable conversation history + hydrate-on-restart + recall context."""

import pytest
import pytest_asyncio

from conversation_repo import ConversationRepo
from conversation import ConversationManager


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = ConversationRepo(db_path=tmp_path / "conversation.db")
    await r.init_db()
    return r


@pytest.mark.asyncio
async def test_append_recent_clear(repo):
    await repo.append("user", "hello")
    await repo.append("assistant", "hi there")
    rows = await repo.recent(10)
    assert [r["role"] for r in rows] == ["user", "assistant"]      # chronological
    assert rows[0]["content"] == "hello"

    await repo.clear()
    assert await repo.recent(10) == []


@pytest.mark.asyncio
async def test_recent_limit_is_newest(repo):
    for i in range(5):
        await repo.append("user", f"m{i}")
    rows = await repo.recent(2)
    # newest two, still oldest-first within the window
    assert [r["content"] for r in rows] == ["m3", "m4"]


@pytest.mark.asyncio
async def test_manager_persists_and_hydrates(repo):
    # First "session": messages flow into the repo.
    m1 = ConversationManager()
    m1.set_repo(repo)
    m1.add_user_message("remember my favorite language is Python")
    m1.add_assistant_message("Noted.")
    # The fire-and-forget tasks need a tick to flush.
    import asyncio
    await asyncio.sleep(0.05)

    # Second "session" (simulated restart): a fresh manager hydrates from the repo.
    m2 = ConversationManager()
    m2.set_repo(repo)
    await m2.hydrate()
    contents = [m["content"] for m in m2.get_messages_for_api()]
    assert "remember my favorite language is Python" in contents
    assert "Noted." in contents


@pytest.mark.asyncio
async def test_build_operator_context_formats(monkeypatch):
    """_build_operator_context pulls the profile + recalled memories into a block."""
    from orchestrator.orchestrator import Orchestrator

    class _StubKeeper:
        async def read(self, key):
            return {"value": "You prefer terse answers and ship fast."} if key == "operator_profile" else None
        async def recall(self, text, limit=3):
            return [{"key": "fav_language", "value": "Python"}]

    o = Orchestrator()
    o.keeper_repo = _StubKeeper()
    ctx = await o._build_operator_context("what language should I use?")
    assert "operator" in ctx.lower()
    assert "terse answers" in ctx
    assert "fav_language: Python" in ctx


@pytest.mark.asyncio
async def test_build_operator_context_empty_without_keeper():
    from orchestrator.orchestrator import Orchestrator
    o = Orchestrator()
    o.keeper_repo = None
    assert await o._build_operator_context("anything") == ""
