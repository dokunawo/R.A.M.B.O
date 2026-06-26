"""Routing context: the router gets recent conversation history, unknown targets
fall back to converse (not orchestrate), and handle() accumulates recent turns."""

import pytest

from orchestrator.routing import SmartRouter, RoutingDecision, RouteStep
from orchestrator.orchestrator import Orchestrator


# ── SmartRouter.route passes history as conversation messages ─────
class _FakeToolBlock:
    type = "tool_use"
    name = "emit_routing_decision"
    input = {"mode": "dispatch", "steps": [{"target": "web_search", "task": "x"}]}


class _FakeResp:
    content = [_FakeToolBlock()]


class _FakeMessages:
    def __init__(self): self.captured = None
    async def create(self, **kw):
        self.captured = kw
        return _FakeResp()


class _FakeLLM:
    def __init__(self): self.messages = _FakeMessages()


@pytest.mark.asyncio
async def test_route_includes_history_then_request():
    llm = _FakeLLM()
    r = SmartRouter(llm, model="m")
    history = [
        {"role": "user", "content": "what teams are playing today"},
        {"role": "assistant", "content": "Want me to web search today's games?"},
    ]
    await r.route("yes", ["- web_search (live skill): action"], {"web_search"}, history=history)
    msgs = llm.messages.captured["messages"]
    # history first, then the route request as the final user message
    assert msgs[0]["content"] == "what teams are playing today"
    assert msgs[1]["content"].startswith("Want me to")
    assert msgs[-1] == {"role": "user", "content": "Route this request: yes"}


def test_sanitize_unknown_target_becomes_converse():
    d = RoutingDecision(mode="dispatch", steps=[RouteStep(target="bogus", task="t")])
    out = SmartRouter._sanitize(d, {"web_search", "converse"})
    assert out.steps[0].target == "converse"   # not "orchestrate"


# ── handle() accumulates recent turns and feeds them to the router ─
class _StubRouter:
    def __init__(self): self.seen_history = []
    async def route(self, goal, roster_lines, valid_targets, history=None):
        self.seen_history.append(list(history or []))
        return RoutingDecision(mode="dispatch",
                               steps=[RouteStep(target="converse", task="answer")])


@pytest.mark.asyncio
async def test_handle_feeds_prior_turns_as_history():
    o = Orchestrator()
    o.llm = None
    o.keeper_repo = None
    o.router = _StubRouter()

    await o.handle("what teams are playing today")
    await o.handle("yes")

    # First call had no history; second call saw the first turn.
    assert o.router.seen_history[0] == []
    joined = " ".join(m["content"] for m in o.router.seen_history[1])
    assert "what teams are playing today" in joined
    # recent_turns holds both turns (user+assistant each).
    assert len(o._recent_turns) == 4
