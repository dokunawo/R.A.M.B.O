"""Transcript repo (clean Q&A) + orchestrator persistence wiring."""

import pytest
import pytest_asyncio

from transcript_repo import TranscriptRepo
from orchestrator.orchestrator import Orchestrator


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = TranscriptRepo(db_path=tmp_path / "transcript.db")
    await r.init_db()
    return r


@pytest.mark.asyncio
async def test_add_recent_clear(repo):
    await repo.add("what teams play today", "Nine games — Cubs at Brewers, ...")
    await repo.add("best HR bets", "Brooks Lee, Jackson Chourio")
    rows = await repo.recent(10)
    assert [r["question"] for r in rows] == ["what teams play today", "best HR bets"]  # chronological
    assert "Brooks Lee" in rows[1]["answer"]

    await repo.clear()
    assert await repo.recent(10) == []


@pytest.mark.asyncio
async def test_skips_fully_empty(repo):
    await repo.add("", "")
    assert await repo.recent(10) == []


@pytest.mark.asyncio
async def test_remember_turn_persists_to_transcript(tmp_path):
    """_remember_turn should schedule a durable transcript write."""
    repo = TranscriptRepo(db_path=tmp_path / "t.db")
    await repo.init_db()
    o = Orchestrator()
    o.set_transcript_repo(repo)

    o._remember_turn("what's the weather", "Sunny, 72 in Detroit, sir.")
    # fire-and-forget task needs a tick to flush
    import asyncio
    await asyncio.sleep(0.05)

    rows = await repo.recent(10)
    assert rows and rows[-1]["question"] == "what's the weather"
    assert "Detroit" in rows[-1]["answer"]
