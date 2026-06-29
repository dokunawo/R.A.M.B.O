import asyncio
import datetime as _dt

import pytest

from dev_agent.repo import DevRepo
from dev_agent import session as dev_session


def _repo(tmp_path):
    return DevRepo(str(tmp_path / "dev.db"))


def _no_prune(monkeypatch):
    """Stub the git prune so tests never touch a real repo."""
    async def _fake(*a, **k):
        return None
    monkeypatch.setattr(dev_session.gw, "prune_change", _fake)


def test_sweep_removes_stale_draft(tmp_path, monkeypatch):
    _no_prune(monkeypatch)

    async def go():
        repo = _repo(tmp_path)
        await repo.init_db()
        await repo.create("aaaa1111", "stuck calculator draft")
        # backdate updated_at so it counts as stale
        old = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=3)).isoformat()
        import aiosqlite
        async with aiosqlite.connect(repo.db_path) as db:
            await db.execute("UPDATE code_changes SET updated_at=? WHERE id=?",
                             (old, "aaaa1111"))
            await db.commit()
        swept = await dev_session.sweep_stale_drafts(repo, max_age_minutes=60)
        assert swept == 1
        assert await repo.get("aaaa1111") is None      # row deleted
    asyncio.run(go())


def test_sweep_keeps_fresh_draft(tmp_path, monkeypatch):
    _no_prune(monkeypatch)

    async def go():
        repo = _repo(tmp_path)
        await repo.init_db()
        await repo.create("bbbb2222", "in-flight draft")   # updated_at = now
        swept = await dev_session.sweep_stale_drafts(repo, max_age_minutes=60)
        assert swept == 0
        assert await repo.get("bbbb2222") is not None      # left alone
    asyncio.run(go())


def test_reject_accepts_drafting(tmp_path, monkeypatch):
    _no_prune(monkeypatch)

    async def go():
        repo = _repo(tmp_path)
        await repo.init_db()
        await repo.create("cccc3333", "drafting change to reject")
        res = await dev_session.reject_change(repo, "cccc3333")
        assert res == {"status": "rejected", "id": "cccc3333"}
        assert (await repo.get("cccc3333"))["status"] == "rejected"
    asyncio.run(go())


def test_reject_refuses_terminal_states(tmp_path, monkeypatch):
    _no_prune(monkeypatch)

    async def go():
        repo = _repo(tmp_path)
        await repo.init_db()
        await repo.create("dddd4444", "already merged")
        await repo.set_status("dddd4444", "merged")
        res = await dev_session.reject_change(repo, "dddd4444")
        assert "error" in res and "merged" in res["error"]
    asyncio.run(go())
