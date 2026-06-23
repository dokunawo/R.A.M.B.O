"""Tests for orchestrator dispatch to Factory-spawned agents."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from orchestrator.orchestrator import Orchestrator
from factory.repo import FactoryRepo
from factory.tool_registry import build_default_registry


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = FactoryRepo(db_path=tmp_path / "test.db")
    await r.init_db()
    await r.save_agent({
        "id": "a1", "slug": "doc-summarizer", "name": "DocSummarizer",
        "specialty": "summarizing documents",
        "system_prompt": "You are DocSummarizer.",
        "tool_allowlist": ["read_file"], "status": "active",
        "created_by_task_id": None,
    })
    return r


def _make_orchestrator(repo, run_result="Summary done."):
    orch = Orchestrator()
    # Stub out LLM so _speak returns the raw results block.
    orch.llm = None
    orch.set_factory(repo, build_default_registry())
    return orch


@pytest.mark.asyncio
async def test_dispatch_matches_by_slug(repo, monkeypatch):
    orch = Orchestrator()
    orch.llm = MagicMock()  # truthy so dispatch is enabled
    orch.set_factory(repo, build_default_registry())

    async def fake_run(self, msg):
        return "Summary produced."
    monkeypatch.setattr(
        "factory.config_agent.ConfigDrivenAgent.run", fake_run,
    )
    # Stub _speak to avoid real LLM streaming.
    orch._speak = AsyncMock(return_value="voiced summary")

    result = await orch._dispatch_spawned("hey doc-summarizer, summarize this")
    assert result is not None
    assert result["agent"] == "rambo"
    orch._speak.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_matches_by_name(repo, monkeypatch):
    orch = Orchestrator()
    orch.llm = MagicMock()
    orch.set_factory(repo, build_default_registry())

    async def fake_run(self, msg):
        return "ok"
    monkeypatch.setattr("factory.config_agent.ConfigDrivenAgent.run", fake_run)
    orch._speak = AsyncMock(return_value="voiced")

    result = await orch._dispatch_spawned("ask DocSummarizer to help")
    assert result is not None


@pytest.mark.asyncio
async def test_no_match_returns_none(repo):
    orch = Orchestrator()
    orch.llm = MagicMock()
    orch.set_factory(repo, build_default_registry())
    result = await orch._dispatch_spawned("what's the weather in Detroit")
    assert result is None


@pytest.mark.asyncio
async def test_dispatch_disabled_without_factory():
    orch = Orchestrator()
    orch.llm = MagicMock()
    # set_factory never called
    result = await orch._dispatch_spawned("doc-summarizer do thing")
    assert result is None


@pytest.mark.asyncio
async def test_dispatch_disabled_without_llm(repo):
    orch = Orchestrator()
    orch.llm = None
    orch.set_factory(repo, build_default_registry())
    result = await orch._dispatch_spawned("doc-summarizer do thing")
    assert result is None
