import pytest
import pytest_asyncio
from datetime import datetime, timezone
from usage_repo import UsageRepo
from usage_dashboard import get_dashboard, _compute_cache_savings, clear_cache


@pytest_asyncio.fixture(autouse=True)
async def reset_cache():
    clear_cache()
    yield
    clear_cache()


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = UsageRepo(db_path=tmp_path / "test.db")
    await r.init_db()
    return r


@pytest.mark.asyncio
async def test_empty_table_returns_zeroes(repo):
    result = await get_dashboard(repo)
    assert result["month_to_date"]["cost_usd"] == 0.0
    assert result["month_to_date"]["call_count"] == 0
    assert result["today"]["cost_usd"] == 0.0
    assert result["by_model"] == []
    assert result["by_day"] == []
    assert result["cache_savings_usd"] == 0.0
    assert result["mom_delta_pct"] == 0.0


@pytest.mark.asyncio
async def test_totals_after_records(repo):
    await repo.record(
        model="claude-sonnet-4-6",
        input_tokens=1000, output_tokens=500,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        cost_usd=0.0105,
    )
    await repo.record(
        model="claude-sonnet-4-6",
        input_tokens=2000, output_tokens=1000,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        cost_usd=0.021,
    )
    result = await get_dashboard(repo)
    assert result["month_to_date"]["call_count"] == 2
    assert result["month_to_date"]["cost_usd"] == pytest.approx(0.0315)
    assert result["month_to_date"]["input_tokens"] == 3000
    assert result["month_to_date"]["output_tokens"] == 1500


@pytest.mark.asyncio
async def test_by_model_breakdown(repo):
    await repo.record(
        model="claude-sonnet-4", input_tokens=100, output_tokens=50,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        cost_usd=0.001,
    )
    await repo.record(
        model="claude-opus-4", input_tokens=100, output_tokens=50,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        cost_usd=0.005,
    )
    result = await get_dashboard(repo)
    models = {m["model"] for m in result["by_model"]}
    assert "claude-sonnet-4" in models
    assert "claude-opus-4" in models


@pytest.mark.asyncio
async def test_by_day_grouping(repo):
    await repo.record(
        model="claude-sonnet-4", input_tokens=100, output_tokens=50,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        cost_usd=0.001,
    )
    result = await get_dashboard(repo)
    assert len(result["by_day"]) >= 1
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert result["by_day"][0]["day"] == today_str


@pytest.mark.asyncio
async def test_today_matches_mtd_on_same_day(repo):
    await repo.record(
        model="claude-sonnet-4", input_tokens=100, output_tokens=50,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        cost_usd=0.001,
    )
    result = await get_dashboard(repo)
    assert result["today"]["cost_usd"] == result["month_to_date"]["cost_usd"]


def test_cache_savings_math():
    savings = _compute_cache_savings(
        cache_read_tokens=10000,
        by_model=[{"model": "claude-sonnet-4", "cost": 0.01, "calls": 5}],
    )
    # Full input rate: 3.00/M, cache read rate: 0.30/M
    # Savings = 10000 * (3.00 - 0.30) / 1_000_000 = 0.027
    assert savings == pytest.approx(0.027)


def test_cache_savings_zero_when_no_cache_reads():
    assert _compute_cache_savings(0, []) == 0.0


@pytest.mark.asyncio
async def test_cache_returns_same_object(repo):
    r1 = await get_dashboard(repo)
    r2 = await get_dashboard(repo)
    assert r1 is r2


@pytest.mark.asyncio
async def test_endpoint_returns_payload(tmp_path):
    from httpx import AsyncClient, ASGITransport
    import main
    from usage_capture import set_usage_repo as _set
    clear_cache()
    test_repo = UsageRepo(db_path=tmp_path / "endpoint_test.db")
    await test_repo.init_db()
    main._usage_repo = test_repo
    _set(test_repo)
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/usage")
    assert resp.status_code == 200
    data = resp.json()
    assert "month_to_date" in data
    assert "by_model" in data
    assert "cache_savings_usd" in data


@pytest.mark.asyncio
async def test_mom_delta_zero_with_no_previous(repo):
    await repo.record(
        model="claude-sonnet-4", input_tokens=100, output_tokens=50,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        cost_usd=0.001,
    )
    result = await get_dashboard(repo)
    assert result["mom_delta_pct"] == 0.0
