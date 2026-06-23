"""Tests for Tier 5 — ConfigDrivenAgent + RegistryWatcher."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from factory.config_agent import ConfigDrivenAgent
from factory.tool_registry import ToolRegistry, ToolDef, build_default_registry
from factory.registry_watcher import RegistryWatcher, build_dispatch_tool
from factory.repo import FactoryRepo


def _make_text_response(text):
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    resp.stop_reason = "end_turn"
    return resp


def _make_tool_use_response(tool_name, tool_input, tool_id="tu_1"):
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.id = tool_id
    block.input = tool_input
    resp = MagicMock()
    resp.content = [block]
    resp.stop_reason = "tool_use"
    return resp


ROW = {
    "slug": "test-bot",
    "name": "Test Bot",
    "specialty": "testing",
    "system_prompt": "You are Test Bot.",
    "tool_allowlist": ["read_file"],
    "model": "claude-sonnet-4-6",
}


@pytest.mark.asyncio
async def test_simple_text_response():
    client = MagicMock()
    client.messages.create = AsyncMock(
        return_value=_make_text_response("Hello from Test Bot!"),
    )
    reg = build_default_registry()
    agent = ConfigDrivenAgent(row=ROW, tool_registry=reg, llm_client=client)
    result = await agent.run("Hi")
    assert "Hello from Test Bot" in result


@pytest.mark.asyncio
async def test_tool_use_loop():
    client = MagicMock()
    client.messages.create = AsyncMock(side_effect=[
        _make_tool_use_response("read_file", {"path": "test.txt"}),
        _make_text_response("File contents: hello"),
    ])
    reg = build_default_registry()
    agent = ConfigDrivenAgent(row=ROW, tool_registry=reg, llm_client=client)
    result = await agent.run("Read test.txt")
    assert "File contents" in result
    assert client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_disallowed_tool_returns_error():
    client = MagicMock()
    client.messages.create = AsyncMock(side_effect=[
        _make_tool_use_response("write_file", {"path": "x", "content": "y"}),
        _make_text_response("Got an error"),
    ])
    row = {**ROW, "tool_allowlist": ["read_file"]}
    reg = build_default_registry()
    agent = ConfigDrivenAgent(row=row, tool_registry=reg, llm_client=client)
    result = await agent.run("Write something")
    assert client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_uses_row_system_prompt():
    client = MagicMock()
    client.messages.create = AsyncMock(
        return_value=_make_text_response("ok"),
    )
    reg = build_default_registry()
    agent = ConfigDrivenAgent(row=ROW, tool_registry=reg, llm_client=client)
    await agent.run("test")
    call_kwargs = client.messages.create.call_args.kwargs
    # Caching on by default → system is a cached text block carrying the prompt.
    import cache_config
    system = call_kwargs["system"]
    assert isinstance(system, list)
    assert system[0]["text"] == "You are Test Bot."
    assert system[0]["cache_control"] == cache_config.cache_control()
    assert system[0]["cache_control"]["type"] == "ephemeral"
    assert call_kwargs["model"] == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_cache_on_sends_cached_block():
    import cache_config
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=_make_text_response("ok"))
    reg = build_default_registry()
    agent = ConfigDrivenAgent(row=ROW, tool_registry=reg, llm_client=client, cache_prompt=True)
    await agent.run("hi")
    system = client.messages.create.call_args.kwargs["system"]
    assert isinstance(system, list)
    assert system[0]["cache_control"] == cache_config.cache_control()


@pytest.mark.asyncio
async def test_cache_off_sends_bare_string():
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=_make_text_response("ok"))
    reg = build_default_registry()
    agent = ConfigDrivenAgent(row=ROW, tool_registry=reg, llm_client=client, cache_prompt=False)
    await agent.run("hi")
    system = client.messages.create.call_args.kwargs["system"]
    assert system == "You are Test Bot."


# ── RegistryWatcher tests ───────────────────────────────────────

@pytest_asyncio.fixture
async def repo(tmp_path):
    r = FactoryRepo(db_path=tmp_path / "test.db")
    await r.init_db()
    return r


@pytest.mark.asyncio
async def test_watcher_registers_new_agents(repo):
    reg = build_default_registry()
    client = MagicMock()
    watcher = RegistryWatcher(repo=repo, tool_registry=reg, llm_client=client)

    await repo.save_agent({
        "id": "a1", "slug": "new-bot", "name": "New Bot",
        "specialty": "new things", "system_prompt": "You are New Bot.",
        "tool_allowlist": ["read_file"], "status": "active",
        "created_by_task_id": None,
    })

    await watcher.refresh()
    assert reg.get("dispatch_to_new-bot") is not None
    assert "dispatch_to_new-bot" not in reg.names_factory_allowed()


@pytest.mark.asyncio
async def test_watcher_unregisters_archived_agents(repo):
    reg = build_default_registry()
    client = MagicMock()
    watcher = RegistryWatcher(repo=repo, tool_registry=reg, llm_client=client)

    await repo.save_agent({
        "id": "a2", "slug": "old-bot", "name": "Old Bot",
        "specialty": "old things", "system_prompt": "You are Old Bot.",
        "tool_allowlist": [], "status": "active",
        "created_by_task_id": None,
    })
    await watcher.refresh()
    assert reg.get("dispatch_to_old-bot") is not None

    await repo.archive_agent("old-bot")
    await watcher.refresh()
    assert reg.get("dispatch_to_old-bot") is None


def test_dispatch_tool_is_not_factory_allowed():
    reg = build_default_registry()
    client = MagicMock()
    tool = build_dispatch_tool("x", ROW, reg, client)
    assert tool.factory_allowed is False


def test_dispatch_tool_schema():
    reg = build_default_registry()
    client = MagicMock()
    tool = build_dispatch_tool("my-agent", ROW, reg, client)
    assert tool.name == "dispatch_to_my-agent"
    assert "message" in tool.input_schema["properties"]
