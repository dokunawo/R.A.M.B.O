"""Tests for Tier 1 — Smart routing."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from orchestrator.routing import SmartRouter, RoutingDecision


def _emit(decision_input):
    block = MagicMock()
    block.type = "tool_use"
    block.name = "emit_routing_decision"
    block.input = decision_input
    resp = MagicMock()
    resp.content = [block]
    return resp


def _client(decision_input):
    c = MagicMock()
    c.messages.create = AsyncMock(return_value=_emit(decision_input))
    return c


ROSTER = ["- engineer (core agent): building", "- weather (live skill): weather", "- orchestrate (pipeline): builds"]
TARGETS = {"engineer", "weather", "orchestrate"}


@pytest.mark.asyncio
async def test_clarify_decision():
    client = _client({"mode": "clarify", "question": "Do you mean A or B?"})
    router = SmartRouter(client)
    d = await router.route("ambiguous", ROSTER, TARGETS)
    assert d.mode == "clarify"
    assert d.question == "Do you mean A or B?"


@pytest.mark.asyncio
async def test_dispatch_single_step():
    client = _client({"mode": "dispatch", "steps": [{"target": "weather", "task": "weather in Detroit"}]})
    router = SmartRouter(client)
    d = await router.route("weather in Detroit", ROSTER, TARGETS)
    assert d.mode == "dispatch"
    assert len(d.steps) == 1
    assert d.steps[0].target == "weather"


@pytest.mark.asyncio
async def test_dispatch_multi_step_ordered():
    client = _client({"mode": "dispatch", "steps": [
        {"target": "engineer", "task": "build it"},
        {"target": "orchestrate", "task": "wire it up"},
    ]})
    router = SmartRouter(client)
    d = await router.route("build and wire", ROSTER, TARGETS)
    assert [s.target for s in d.steps] == ["engineer", "orchestrate"]


@pytest.mark.asyncio
async def test_unknown_target_becomes_orchestrate():
    client = _client({"mode": "dispatch", "steps": [{"target": "nonexistent", "task": "do it"}]})
    router = SmartRouter(client)
    d = await router.route("x", ROSTER, TARGETS)
    assert d.steps[0].target == "orchestrate"


@pytest.mark.asyncio
async def test_no_llm_returns_none():
    router = SmartRouter(None)
    assert await router.route("x", ROSTER, TARGETS) is None


@pytest.mark.asyncio
async def test_llm_error_returns_none():
    client = MagicMock()
    client.messages.create = AsyncMock(side_effect=RuntimeError("boom"))
    router = SmartRouter(client)
    assert await router.route("x", ROSTER, TARGETS) is None


@pytest.mark.asyncio
async def test_clarify_without_question_falls_back():
    client = _client({"mode": "clarify", "question": "  "})
    router = SmartRouter(client)
    assert await router.route("x", ROSTER, TARGETS) is None


@pytest.mark.asyncio
async def test_empty_steps_falls_back():
    client = _client({"mode": "dispatch", "steps": []})
    router = SmartRouter(client)
    assert await router.route("x", ROSTER, TARGETS) is None


@pytest.mark.asyncio
async def test_no_emit_block_returns_none():
    block = MagicMock()
    block.type = "text"
    block.text = "i refuse"
    resp = MagicMock()
    resp.content = [block]
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=resp)
    router = SmartRouter(client)
    assert await router.route("x", ROSTER, TARGETS) is None
