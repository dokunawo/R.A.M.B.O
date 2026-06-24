import pytest
import pytest_asyncio
from orchestrator.orchestrator import Orchestrator
from orchestrator.routing import RoutingDecision, RouteStep
from dispatch_repo import DispatchRepo


@pytest_asyncio.fixture
async def orch(tmp_path):
    o = Orchestrator()
    repo = DispatchRepo(db_path=tmp_path / "d.db")
    await repo.init_db()
    o.set_dispatch_repo(repo)
    return o, repo


@pytest.mark.asyncio
async def test_dispatch_turn_logs_completed_row(orch, monkeypatch):
    o, repo = orch

    async def fake_route(goal, roster_lines, valid_targets):
        return RoutingDecision(mode="dispatch", steps=[RouteStep(target="seeker", task="look up X")])
    monkeypatch.setattr(o.router, "route", fake_route)

    async def fake_run_target(target, task, ctx):
        return "did the thing"
    monkeypatch.setattr(o, "_run_target", fake_run_target)

    async def fake_speak(goal, plan, results):
        return "All done."
    monkeypatch.setattr(o, "_speak", fake_speak)

    await o.handle("find X")

    recent = await repo.get_recent()
    assert len(recent) == 1
    assert recent[0]["status"] == "completed"
    assert await repo.get_active() == []


@pytest.mark.asyncio
async def test_no_repo_is_noop(monkeypatch):
    o = Orchestrator()  # dispatch_repo defaults to None

    async def fake_route(goal, roster_lines, valid_targets):
        return RoutingDecision(mode="dispatch", steps=[RouteStep(target="seeker", task="t")])
    monkeypatch.setattr(o.router, "route", fake_route)

    async def fake_run_target(target, task, ctx):
        return "ok"
    monkeypatch.setattr(o, "_run_target", fake_run_target)

    async def fake_speak(goal, plan, results):
        return "done"
    monkeypatch.setattr(o, "_speak", fake_speak)

    result = await o.handle("do it")  # must not raise
    assert result["agent"] == "rambo"
