import pytest
import pytest_asyncio
import tts_dashboard
from tts_usage_repo import TTSUsageRepo


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = TTSUsageRepo(db_path=tmp_path / "t.db")
    await r.init_db()
    return r


@pytest.mark.asyncio
async def test_local_only_when_no_subscription(repo, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_MONTHLY_LIMIT", raising=False)
    await repo.record(2500)
    # No api_key → get_subscription returns None → source local.
    out = await tts_dashboard.get_tts_dashboard(repo, None)
    assert out["source"] == "local"
    assert out["real"] is None
    assert out["local"]["used"] == 2500
    assert out["local"]["limit"] == 10000
    assert out["local"]["remaining"] == 7500
    assert "reset_date" in out


@pytest.mark.asyncio
async def test_prefers_real_when_available(repo, monkeypatch):
    async def fake_sub(api_key):
        return {"used": 8420, "limit": 10000}
    monkeypatch.setattr(tts_dashboard, "get_subscription", fake_sub)
    out = await tts_dashboard.get_tts_dashboard(repo, "key")
    assert out["source"] == "real"
    assert out["real"] == {"used": 8420, "limit": 10000, "remaining": 1580}


@pytest.mark.asyncio
async def test_limit_env_override(repo, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_MONTHLY_LIMIT", "30000")
    out = await tts_dashboard.get_tts_dashboard(repo, None)
    assert out["local"]["limit"] == 30000
