import pytest
import pytest_asyncio
import todos_skill
from todos_repo import TodosRepo
from todos_watch import compose_nudge, check_once


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = TodosRepo(db_path=tmp_path / "watch_todos.db")
    await r.init_db()
    todos_skill.set_repo(r)
    yield r
    todos_skill.set_repo(None)


class FakeOrchestrator:
    def __init__(self):
        self.responses = []
        self.broadcasts = []
        self.spoken = []

    async def _response(self, agent, msg):
        self.responses.append((agent, msg))

    async def broadcast(self, msg):
        self.broadcasts.append(msg)

    async def _voice_text(self, msg):
        self.spoken.append(msg)


def test_compose_nudge_overdue():
    msg = compose_nudge({"text": "call the vet", "due_date": "2026-06-01"})
    assert "call the vet" in msg


@pytest.mark.asyncio
async def test_check_once_nudges_due_today_and_overdue(repo, monkeypatch):
    monkeypatch.setattr("todos_watch._today_str", lambda: "2026-07-01")
    await repo.add("today task", due="2026-07-01")
    await repo.add("overdue task", due="2026-06-01")
    await repo.add("future task", due="2026-08-01")
    orch = FakeOrchestrator()
    fired = await check_once(orch)
    fired_texts = {t["text"] for t in fired}
    assert fired_texts == {"today task", "overdue task"}
    assert len(orch.spoken) == 2


@pytest.mark.asyncio
async def test_check_once_does_not_renotify_same_day(repo, monkeypatch):
    monkeypatch.setattr("todos_watch._today_str", lambda: "2026-07-01")
    await repo.add("today task", due="2026-07-01")
    orch = FakeOrchestrator()
    notified = set()
    await check_once(orch, notified_today=notified)
    await check_once(orch, notified_today=notified)
    assert len(orch.spoken) == 1


@pytest.mark.asyncio
async def test_check_once_no_repo_is_graceful():
    todos_skill.set_repo(None)
    orch = FakeOrchestrator()
    fired = await check_once(orch)
    assert fired == []
