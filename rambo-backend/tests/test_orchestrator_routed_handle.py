"""Tests for the smart-routed Orchestrator.handle() flow."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from orchestrator.orchestrator import Orchestrator
from orchestrator.routing import RoutingDecision, RouteStep


def _orch():
    orch = Orchestrator()
    orch.llm = MagicMock()
    orch._speak = AsyncMock(side_effect=lambda goal, plan, results: " | ".join(str(r) for r in results))
    return orch


@pytest.mark.asyncio
async def test_clarify_returns_question_without_dispatch():
    orch = _orch()
    orch.router.route = AsyncMock(return_value=RoutingDecision(mode="clarify", question="A or B?"))
    orch._run_target = AsyncMock()

    result = await orch.handle("ambiguous request")
    assert result["clarify"] is True
    assert result["response"] == "A or B?"
    orch._run_target.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_runs_each_step_in_order():
    orch = _orch()
    orch.router.route = AsyncMock(return_value=RoutingDecision(
        mode="dispatch",
        steps=[RouteStep(target="architect", task="plan"), RouteStep(target="orchestrate", task="build")],
    ))
    calls = []
    async def fake_run_target(target, task, ctx):
        calls.append(target)
        return f"{target}-done"
    orch._run_target = fake_run_target

    result = await orch.handle("plan then build")
    assert calls == ["architect", "orchestrate"]
    assert "architect-done" in result["response"]
    assert "orchestrate-done" in result["response"]


@pytest.mark.asyncio
async def test_fallback_to_legacy_when_router_punts():
    orch = _orch()
    orch.router.route = AsyncMock(return_value=None)
    orch._legacy_handle = AsyncMock(return_value={"response": "legacy", "agent": "rambo"})

    result = await orch.handle("something")
    assert result["response"] == "legacy"
    orch._legacy_handle.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_target_skill(monkeypatch):
    orch = _orch()
    orch._run_skill = AsyncMock(return_value="weather result")
    # weather is a real skill name in SKILLS
    out = await orch._run_target("weather", "weather in Detroit", {})
    assert out == "weather result"


@pytest.mark.asyncio
async def test_run_target_orchestrate():
    orch = _orch()
    orch._orchestrate = AsyncMock(return_value=(["plan"], ["r1", "r2"]))
    out = await orch._run_target("orchestrate", "build a thing", {})
    assert "r1" in out and "r2" in out


@pytest.mark.asyncio
async def test_run_target_isolates_errors():
    orch = _orch()
    orch._orchestrate = AsyncMock(side_effect=RuntimeError("kaboom"))
    out = await orch._run_target("orchestrate", "x", {})
    assert "error" in out.lower()


@pytest.mark.asyncio
async def test_build_roster_includes_core_and_skills():
    orch = _orch()
    lines, targets = await orch._build_roster()
    assert "architect" in targets
    assert "orchestrate" in targets
    assert "weather" in targets
    assert any("core agent" in ln for ln in lines)
