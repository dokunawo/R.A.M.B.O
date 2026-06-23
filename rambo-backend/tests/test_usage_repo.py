import pytest
import pytest_asyncio
import aiosqlite
from pathlib import Path
from usage_repo import UsageRepo


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = UsageRepo(db_path=tmp_path / "test_usage.db")
    await r.init_db()
    return r


@pytest.mark.asyncio
async def test_table_exists(repo):
    async with aiosqlite.connect(repo._db_path) as db:
        rows = await db.execute_fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='usage'"
        )
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_expected_columns(repo):
    async with aiosqlite.connect(repo._db_path) as db:
        rows = await db.execute_fetchall("PRAGMA table_info(usage)")
        col_names = {r[1] for r in rows}
    expected = {
        "id", "model", "input_tokens", "output_tokens",
        "cache_creation_input_tokens", "cache_read_input_tokens",
        "cost_usd", "source", "created_at",
    }
    assert expected == col_names


@pytest.mark.asyncio
async def test_timestamp_index_exists(repo):
    async with aiosqlite.connect(repo._db_path) as db:
        rows = await db.execute_fetchall(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_usage_created_at'"
        )
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_record_and_read_back(repo):
    await repo.record(
        model="claude-sonnet-4-20250514",
        input_tokens=1000,
        output_tokens=500,
        cache_creation_input_tokens=200,
        cache_read_input_tokens=300,
        cost_usd=0.012,
        source="conversation",
    )
    result = await repo.usage_since("2000-01-01")
    assert result["total_input"] == 1000
    assert result["total_output"] == 500
    assert result["total_cache_write"] == 200
    assert result["total_cache_read"] == 300
    assert result["total_cost"] == pytest.approx(0.012)
    assert result["call_count"] == 1
    assert len(result["by_model"]) == 1
    assert result["by_model"][0]["model"] == "claude-sonnet-4-20250514"


@pytest.mark.asyncio
async def test_multiple_records_aggregate(repo):
    for _ in range(3):
        await repo.record(
            model="claude-sonnet-4",
            input_tokens=100, output_tokens=50,
            cache_creation_input_tokens=0, cache_read_input_tokens=0,
            cost_usd=0.001,
        )
    result = await repo.usage_since("2000-01-01")
    assert result["call_count"] == 3
    assert result["total_input"] == 300
    assert result["total_cost"] == pytest.approx(0.003)


@pytest.mark.asyncio
async def test_empty_table_returns_zeroes(repo):
    result = await repo.usage_since("2000-01-01")
    assert result["total_cost"] == 0.0
    assert result["call_count"] == 0
    assert result["by_model"] == []


@pytest.mark.asyncio
async def test_init_db_idempotent(tmp_path):
    r = UsageRepo(db_path=tmp_path / "test.db")
    await r.init_db()
    await r.init_db()
    await r.record(
        model="test", input_tokens=1, output_tokens=1,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        cost_usd=0.0,
    )
    result = await r.usage_since("2000-01-01")
    assert result["call_count"] == 1
