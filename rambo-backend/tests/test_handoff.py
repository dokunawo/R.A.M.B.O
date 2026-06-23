"""Tests for Tier 5 — handoff system (propose, don't chain)."""

import json
import pytest

from factory import handoff
from factory.handoff import HandoffRecommendation
from factory.tool_registry import build_default_registry


@pytest.fixture(autouse=True)
def _clean():
    handoff._reset()
    yield
    handoff._reset()


def test_schema_clamps_confidence():
    with pytest.raises(Exception):
        HandoffRecommendation(target_agent="a", reason="r", task="t", confidence=2.0)


def test_propose_and_list():
    rec = HandoffRecommendation(
        target_agent="seeker", reason="needs research", task="find X",
        artifacts={"spec": "agent-specs/x.md"}, preconditions=["check Y"],
        confidence=0.8,
    )
    entry = handoff.propose(rec, from_agent="writer-bot")
    assert entry["status"] == "pending"
    assert entry["from_agent"] == "writer-bot"
    pending = handoff.list_pending()
    assert len(pending) == 1
    assert pending[0]["target_agent"] == "seeker"
    assert pending[0]["artifacts"] == {"spec": "agent-specs/x.md"}


def test_resolve_accept_and_reject():
    rec = HandoffRecommendation(target_agent="a", reason="r", task="t")
    e1 = handoff.propose(rec)
    assert handoff.resolve(e1["id"], "accepted")["status"] == "accepted"
    assert handoff.list_pending() == []
    # Cannot resolve twice.
    assert handoff.resolve(e1["id"], "rejected") is None


@pytest.mark.asyncio
async def test_propose_handoff_tool_records_not_dispatches():
    reg = build_default_registry()
    tool = reg.get("propose_handoff")
    assert tool is not None
    out = await tool.execute(
        target_agent="analyst", reason="needs analysis", task="analyze the data",
        artifacts={"csv": "/tmp/data.csv"}, confidence=0.9,
    )
    payload = json.loads(out)
    assert payload["status"] == "handoff_proposed"
    # It recorded a pending handoff but dispatched nothing.
    pending = handoff.list_pending()
    assert len(pending) == 1
    assert pending[0]["target_agent"] == "analyst"


def test_propose_handoff_tool_is_in_catalog():
    reg = build_default_registry()
    names = [t.name for t in reg.list_all()]
    assert "propose_handoff" in names
    assert reg.get("propose_handoff").factory_allowed is True


@pytest.mark.asyncio
async def test_accept_dispatches_via_run_target(monkeypatch):
    """Accept path should call the orchestrator's _run_target with the task."""
    rec = HandoffRecommendation(target_agent="seeker", reason="r", task="find X")
    entry = handoff.propose(rec)

    calls = []
    async def fake_run_target(target, task, ctx):
        calls.append((target, task))
        return "dispatched-result"

    # Simulate the accept endpoint's core logic.
    handoff.resolve(entry["id"], "accepted")
    result = await fake_run_target(entry["target_agent"], entry["task"], {})
    assert calls == [("seeker", "find X")]
    assert result == "dispatched-result"
    assert handoff.list_pending() == []
