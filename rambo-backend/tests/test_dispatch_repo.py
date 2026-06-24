import pytest
import pytest_asyncio
import aiosqlite
from dispatch_repo import DispatchRepo


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = DispatchRepo(db_path=tmp_path / "test_dispatch.db")
    await r.init_db()
    return r


@pytest.mark.asyncio
async def test_table_and_columns(repo):
    async with aiosqlite.connect(repo._db_path) as db:
        rows = await db.execute_fetchall("PRAGMA table_info(dispatches)")
        cols = {r[1] for r in rows}
    assert cols == {
        "id", "goal", "plan", "status", "summary",
        "created_at", "updated_at", "completed_at",
    }


@pytest.mark.asyncio
async def test_register_creates_working_row(repo):
    did = await repo.register("build a landing page", "architect; engineer")
    assert isinstance(did, int)
    active = await repo.get_active()
    assert len(active) == 1
    assert active[0]["goal"] == "build a landing page"
    assert active[0]["status"] == "working"
    assert active[0]["completed_at"] is None


@pytest.mark.asyncio
async def test_update_status_completes_row(repo):
    did = await repo.register("research X")
    await repo.update_status(did, "completed", "Found 3 sources")
    assert await repo.get_active() == []
    recent = await repo.get_recent()
    assert recent[0]["status"] == "completed"
    assert recent[0]["summary"] == "Found 3 sources"
    assert recent[0]["completed_at"] is not None


@pytest.mark.asyncio
async def test_failed_status_sets_completed_at(repo):
    did = await repo.register("do thing")
    await repo.update_status(did, "failed", "boom")
    recent = await repo.get_recent()
    assert recent[0]["status"] == "failed"
    assert recent[0]["completed_at"] is not None


@pytest.mark.asyncio
async def test_get_recent_orders_newest_first_and_limits(repo):
    for i in range(7):
        await repo.register(f"goal {i}")
    recent = await repo.get_recent(limit=5)
    assert len(recent) == 5
    assert recent[0]["goal"] == "goal 6"


@pytest.mark.asyncio
async def test_init_db_idempotent(tmp_path):
    r = DispatchRepo(db_path=tmp_path / "d.db")
    await r.init_db()
    await r.init_db()
    await r.register("g")
    assert len(await r.get_active()) == 1


@pytest.mark.asyncio
async def test_format_for_prompt_empty(repo):
    assert await repo.format_for_prompt() == ""


@pytest.mark.asyncio
async def test_format_for_prompt_active(repo):
    await repo.register("build the dashboard")
    out = await repo.format_for_prompt()
    assert "CURRENTLY WORKING ON:" in out
    assert "build the dashboard" in out


@pytest.mark.asyncio
async def test_format_for_prompt_completed(repo):
    did = await repo.register("research pricing")
    await repo.update_status(did, "completed", "Compared 3 vendors")
    out = await repo.format_for_prompt()
    assert "RECENTLY COMPLETED:" in out
    assert "Compared 3 vendors" in out
