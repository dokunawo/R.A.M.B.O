import pytest
import pytest_asyncio
import aiosqlite
from datetime import datetime, timezone, timedelta
from tts_usage_repo import TTSUsageRepo


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = TTSUsageRepo(db_path=tmp_path / "test_tts_usage.db")
    await r.init_db()
    return r


@pytest.mark.asyncio
async def test_table_and_columns(repo):
    async with aiosqlite.connect(repo._db_path) as db:
        rows = await db.execute_fetchall("PRAGMA table_info(tts_usage)")
        cols = {r[1] for r in rows}
    assert cols == {"id", "characters", "model", "created_at"}


@pytest.mark.asyncio
async def test_record_and_sum(repo):
    await repo.record(120, "eleven_turbo_v2_5")
    await repo.record(80)
    total = await repo.characters_since("2000-01-01")
    assert total == 200


@pytest.mark.asyncio
async def test_window_excludes_earlier_rows(repo):
    # Insert a row stamped well in the past, then a fresh one.
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    async with aiosqlite.connect(repo._db_path) as db:
        await db.execute(
            "INSERT INTO tts_usage (characters, model, created_at) VALUES (?, '', ?)",
            (500, old),
        )
        await db.commit()
    await repo.record(75)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert await repo.characters_since(cutoff) == 75


@pytest.mark.asyncio
async def test_empty_returns_zero(repo):
    assert await repo.characters_since("2000-01-01") == 0


@pytest.mark.asyncio
async def test_init_db_idempotent(tmp_path):
    r = TTSUsageRepo(db_path=tmp_path / "t.db")
    await r.init_db()
    await r.init_db()
    await r.record(10)
    assert await r.characters_since("2000-01-01") == 10
