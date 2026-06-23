"""Tests for Tier 4 — tool confirmation gate."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from factory import confirmations
from factory.config_agent import ConfigDrivenAgent
from factory.tool_registry import build_default_registry, ToolDef


@pytest.fixture(autouse=True)
def _clean():
    confirmations._reset()
    yield
    confirmations._reset()


def _tool_use(name, inp, tid="t1"):
    b = MagicMock()
    b.type = "tool_use"; b.name = name; b.id = tid; b.input = inp
    r = MagicMock(); r.content = [b]; r.stop_reason = "tool_use"
    return r


def _text(t):
    b = MagicMock(); b.type = "text"; b.text = t
    r = MagicMock(); r.content = [b]; r.stop_reason = "end_turn"
    return r


ROW = {
    "slug": "writer-bot", "name": "Writer", "specialty": "x",
    "system_prompt": "You are Writer.", "tool_allowlist": ["write_file", "read_file"],
    "model": "claude-sonnet-4-20250514",
}


def test_store_request_and_resolve():
    rec = confirmations.request_confirmation("write_file", {"path": "a", "content": "b"})
    assert rec["status"] == "pending"
    assert len(confirmations.list_pending()) == 1
    resolved = confirmations.resolve(rec["id"], "approved")
    assert resolved["status"] == "approved"
    assert confirmations.list_pending() == []


def test_resolve_unknown_returns_none():
    assert confirmations.resolve("nope", "approved") is None


@pytest.mark.asyncio
async def test_gated_tool_is_not_executed():
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=_tool_use("write_file", {"path": "x.txt", "content": "hi"}))
    reg = build_default_registry()
    agent = ConfigDrivenAgent(row=ROW, tool_registry=reg, llm_client=client)

    out = await agent.run("write a file")
    # Loop stopped awaiting confirmation; the write did not happen.
    assert "confirmation" in out.lower()
    pending = confirmations.list_pending()
    assert len(pending) == 1
    assert pending[0]["tool_name"] == "write_file"


@pytest.mark.asyncio
async def test_ungated_tool_still_runs():
    client = MagicMock()
    client.messages.create = AsyncMock(side_effect=[
        _tool_use("read_file", {"path": "x.txt"}),
        _text("done"),
    ])
    reg = build_default_registry()
    agent = ConfigDrivenAgent(row=ROW, tool_registry=reg, llm_client=client)
    out = await agent.run("read a file")
    assert out == "done"
    assert confirmations.list_pending() == []


@pytest.mark.asyncio
async def test_approve_executes_once(tmp_path):
    reg = build_default_registry()
    target = tmp_path / "out.txt"
    rec = confirmations.request_confirmation("write_file", {"path": str(target), "content": "hello"})

    # Simulate the approve endpoint's execution path.
    tool = reg.get(rec["tool_name"])
    confirmations.resolve(rec["id"], "approved")
    result = await tool.execute(**rec["tool_input"])

    assert target.read_text() == "hello"
    assert "written" in result
    # Already resolved → cannot resolve again.
    assert confirmations.resolve(rec["id"], "approved") is None


def test_write_file_flagged_requires_confirmation():
    reg = build_default_registry()
    assert reg.get("write_file").requires_confirmation is True
    assert reg.get("read_file").requires_confirmation is False
