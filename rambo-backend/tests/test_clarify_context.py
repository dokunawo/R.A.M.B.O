"""Clarify context continuity: the answer to a clarify question routes WITH the
question + original request as context (consume-once)."""

import pytest

from orchestrator.orchestrator import Orchestrator
from orchestrator.routing import RoutingDecision, RouteStep


class _StubRouter:
    """Turn 1 → clarify; turn 2 → a converse dispatch. Captures the goal text the
    router is given each turn so we can assert the clarify context is folded in."""
    def __init__(self):
        self.calls = 0
        self.seen = []

    async def route(self, goal, roster_lines, valid_targets, history=None):
        self.calls += 1
        self.seen.append(goal)
        if self.calls == 1:
            return RoutingDecision(mode="clarify",
                                   question="Did you mean the attorney or the athlete?")
        return RoutingDecision(mode="dispatch",
                               steps=[RouteStep(target="converse", task="answer it")])


@pytest.mark.asyncio
async def test_clarify_answer_routes_with_context():
    o = Orchestrator()
    o.llm = None            # _speak takes the no-LLM path; no network
    o.keeper_repo = None     # operator-context block stays empty
    o.router = _StubRouter()

    # Turn 1: ambiguous request → clarify.
    r1 = await o.handle("search up Christin DewBerry")
    assert r1.get("clarify") is True
    assert o._pending_clarify is not None
    assert o._pending_clarify["goal"] == "search up Christin DewBerry"
    # The question was persisted to conversation history.
    msgs = o.conversation.get_messages_for_api()
    assert any(m["role"] == "assistant" and "attorney or the athlete" in m["content"]
               for m in msgs)

    # Turn 2: the answer. The router must see the question + original request + answer.
    await o.handle("the attorney")
    ctx_goal = o.router.seen[1]
    assert "Christin DewBerry" in ctx_goal          # original subject carried in
    assert "attorney or the athlete" in ctx_goal     # the question
    assert "the attorney" in ctx_goal                # this turn's answer
    assert o._pending_clarify is None                # consumed once


@pytest.mark.asyncio
async def test_no_pending_clarify_leaves_goal_clean():
    o = Orchestrator()
    o.llm = None
    o.keeper_repo = None
    o.router = _StubRouter()
    # Skip straight to a normal turn (calls==1 returns clarify, but assert the
    # first routed goal has no clarify CONTEXT prefix since nothing was pending).
    await o.handle("what's the weather")
    assert "CONTEXT: You earlier asked" not in o.router.seen[0]
