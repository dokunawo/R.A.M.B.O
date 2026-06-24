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


# ── new tests for fix-wave ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_format_completed_not_hidden_by_active_rows(repo):
    """Fix #1: 3 working rows must not crowd out a completed row."""
    c_id = await repo.register("completed goal")
    await repo.update_status(c_id, "completed", "done summary")
    for i in range(3):
        await repo.register(f"working goal {i}")
    out = await repo.format_for_prompt()
    assert "RECENTLY COMPLETED:" in out
    assert "completed goal" in out


@pytest.mark.asyncio
async def test_format_active_row_has_elapsed_annotation(repo):
    """Fix #4: active rows must include elapsed time annotation."""
    await repo.register("annotated task")
    out = await repo.format_for_prompt()
    assert "annotated task" in out
    assert "s ago)" in out


@pytest.mark.asyncio
async def test_get_recent_completed_returns_only_done_rows(repo):
    """get_recent_completed returns only completed/failed, newest first, respects limit."""
    id1 = await repo.register("goal A")
    await repo.update_status(id1, "completed", "A done")
    id2 = await repo.register("goal B")
    await repo.update_status(id2, "failed", "B failed")
    await repo.register("goal C")  # still working — must be excluded

    results = await repo.get_recent_completed(limit=5)
    statuses = {r["status"] for r in results}
    assert statuses <= {"completed", "failed"}
    assert len(results) == 2
    # newest completed/failed first (B registered after A)
    assert results[0]["goal"] == "goal B"


@pytest.mark.asyncio
async def test_get_recent_completed_respects_limit(repo):
    for i in range(5):
        rid = await repo.register(f"goal {i}")
        await repo.update_status(rid, "completed", "")
    results = await repo.get_recent_completed(limit=2)
    assert len(results) == 2
