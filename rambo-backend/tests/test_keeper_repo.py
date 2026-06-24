import pytest
import pytest_asyncio
import aiosqlite
from keeper_repo import KeeperRepo


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = KeeperRepo(db_path=tmp_path / "test_keeper.db")
    await r.init_db()
    return r


@pytest.mark.asyncio
async def test_table_and_columns(repo):
    async with aiosqlite.connect(repo._db_path) as db:
        rows = await db.execute_fetchall("PRAGMA table_info(memories)")
        cols = {r[1] for r in rows}
    assert cols == {"id", "key", "value", "tags", "created_at", "updated_at"}


@pytest.mark.asyncio
async def test_write_then_read(repo):
    rid = await repo.write("favorite_color", "blue", tags="preference")
    assert isinstance(rid, int)
    entry = await repo.read("favorite_color")
    assert entry["value"] == "blue"
    assert entry["tags"] == "preference"


@pytest.mark.asyncio
async def test_write_is_upsert_by_key(repo):
    await repo.write("city", "Detroit")
    await repo.write("city", "Austin")
    entry = await repo.read("city")
    assert entry["value"] == "Austin"
    # Still a single row for that key.
    rows = await repo.query("city")
    assert len([r for r in rows if r["key"] == "city"]) == 1


@pytest.mark.asyncio
async def test_read_missing_returns_none(repo):
    assert await repo.read("nope") is None


@pytest.mark.asyncio
async def test_query_search_across_fields(repo):
    await repo.write("project_deadline", "ship by Friday", tags="work")
    await repo.write("lunch", "tacos", tags="food")
    hits = await repo.query("friday")
    assert len(hits) == 1 and hits[0]["key"] == "project_deadline"
    by_tag = await repo.query("food")
    assert len(by_tag) == 1 and by_tag[0]["key"] == "lunch"


@pytest.mark.asyncio
async def test_query_empty_returns_all_newest_first(repo):
    await repo.write("a", "1")
    await repo.write("b", "2")
    rows = await repo.query()
    assert {r["key"] for r in rows} == {"a", "b"}


@pytest.mark.asyncio
async def test_confirm_reports_count_and_recent(repo):
    await repo.write("x", "1")
    await repo.write("y", "2")
    out = await repo.confirm()
    assert out["count"] == 2
    assert len(out["recent"]) == 2


@pytest.mark.asyncio
async def test_confirm_empty(repo):
    out = await repo.confirm()
    assert out["count"] == 0
    assert out["recent"] == []


@pytest.mark.asyncio
async def test_init_db_idempotent(tmp_path):
    r = KeeperRepo(db_path=tmp_path / "k.db")
    await r.init_db()
    await r.init_db()
    await r.write("k", "v")
    assert (await r.read("k"))["value"] == "v"
