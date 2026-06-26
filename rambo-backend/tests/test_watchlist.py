"""Tests for natural-language watch-topic + deadline management (_run_watchlist)."""

from datetime import date, timedelta

import pytest

from orchestrator.orchestrator import Orchestrator


class _FakeKeeper:
    def __init__(self): self.rows = []
    async def write(self, key, value, tags="", confidence="verified"):
        self.rows = [r for r in self.rows if r["key"] != key]
        self.rows.append({"key": key, "value": value, "tags": tags})
    async def query(self, search="", limit=50):
        return [r for r in self.rows if search in r.get("tags", "") or search in r["key"]]
    async def read(self, key):
        return next((r for r in self.rows if r["key"] == key), None)
    async def delete(self, key):
        n = len(self.rows); self.rows = [r for r in self.rows if r["key"] != key]
        return len(self.rows) < n


def _orch():
    o = Orchestrator()
    o.keeper_repo = _FakeKeeper()
    return o


@pytest.mark.asyncio
async def test_add_and_list_and_remove_watch_topic():
    o = _orch()
    out = await o._run_watchlist("keep an eye on NVDA earnings")
    assert "NVDA earnings" in out
    listed = await o._run_watchlist("what am I watching")
    assert "NVDA earnings" in listed
    removed = await o._run_watchlist("stop watching NVDA earnings")
    assert "Stopped watching" in removed
    assert "not watching anything" in (await o._run_watchlist("what am I watching")).lower()


@pytest.mark.asyncio
async def test_add_watch_variants():
    for phrase in ["watch the housing market", "track OpenAI releases",
                   "monitor my server uptime", "keep tabs on Tigers scores"]:
        o = _orch()
        out = await o._run_watchlist(phrase)
        assert "keep an eye on" in out.lower()


@pytest.mark.asyncio
async def test_add_deadline_natural():
    o = _orch()
    out = await o._run_watchlist("remind me the quarterly report is due tomorrow")
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert "quarterly report" in out and tomorrow in out
    listed = await o._run_watchlist("what are my deadlines")
    assert "quarterly report" in listed


@pytest.mark.asyncio
async def test_add_deadline_relative_and_weekday():
    o = _orch()
    out = await o._run_watchlist("remind me the thing is due in 3 days")
    assert (date.today() + timedelta(days=3)).isoformat() in out
    out2 = await o._run_watchlist("the audit is due next Friday")
    assert "audit" in out2 and "due 2" in out2   # resolved to an actual date


@pytest.mark.asyncio
async def test_add_deadline_bad_date_is_graceful():
    o = _orch()
    out = await o._run_watchlist("remind me the thing is due whenever-ish")
    assert "couldn't pin a date" in out.lower()


def test_is_watchlist_command():
    o = Orchestrator()
    assert o._is_watchlist_command("keep an eye on the AI chip market")
    assert o._is_watchlist_command("remind me the report is due Friday")
    assert o._is_watchlist_command("what am I watching")
    assert not o._is_watchlist_command("what's the news on AI")


@pytest.mark.asyncio
async def test_unparseable_gives_help():
    o = _orch()
    out = await o._run_watchlist("uhh do something")
    assert "keep an eye on" in out.lower()


@pytest.mark.asyncio
async def test_no_keeper_degrades():
    o = Orchestrator()
    o.keeper_repo = None
    assert "isn't available" in await o._run_watchlist("watch NVDA")
