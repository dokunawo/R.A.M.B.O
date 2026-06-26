"""Tests for idle + deadline nudges and Seeker watch crawl logic."""

import time
from datetime import date, timedelta

import pytest

import proactive_nudges as pn
import seeker_watch


class _StubOrch:
    def __init__(self, keeper=None, factory=None, dev=None):
        self.keeper_repo = keeper
        self.factory_repo = factory
        self.dev_repo = dev
        self.said = []

    async def _response(self, agent, msg): self.said.append(msg)
    async def broadcast(self, msg): pass
    async def _voice_text(self, msg): self.said.append(("voice", msg))


# ── Idle nudges ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_idle_nudge_fires_once_when_work_waiting(monkeypatch):
    monkeypatch.setenv("PROACTIVE_IDLE", "on")
    monkeypatch.setenv("IDLE_MINUTES", "10")
    monkeypatch.setenv("PROACTIVE_WAKE", "0-24")   # always waking for the test
    monkeypatch.setenv("PROACTIVE_SPEAK", "off")
    # Force "idle for a long time".
    monkeypatch.setattr(pn, "_last_active", time.monotonic() - 9999)
    # One confirmation pending.
    monkeypatch.setattr("factory.confirmations.list_pending", lambda: [{"id": "x"}])

    orch = _StubOrch()
    state = {}
    msg = await pn.check_idle(orch, state)
    assert msg and "1 action to approve" in msg
    # Second tick: already fired this idle stretch → no repeat.
    assert await pn.check_idle(orch, state) is None


@pytest.mark.asyncio
async def test_idle_nudge_silent_when_nothing_waiting(monkeypatch):
    monkeypatch.setenv("PROACTIVE_IDLE", "on")
    monkeypatch.setenv("IDLE_MINUTES", "10")
    monkeypatch.setenv("PROACTIVE_WAKE", "0-24")
    monkeypatch.setattr(pn, "_last_active", time.monotonic() - 9999)
    monkeypatch.setattr("factory.confirmations.list_pending", lambda: [])
    monkeypatch.setattr("factory.handoff.list_pending", lambda: [])

    assert await pn.check_idle(_StubOrch(), {}) is None  # never nag with nothing waiting


# ── Deadlines ────────────────────────────────────────────────────
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


@pytest.mark.asyncio
async def test_add_and_list_deadline_iso():
    k = _FakeKeeper()
    due = (date.today() + timedelta(days=1)).isoformat()
    res = await pn.add_deadline(k, "Tax filing", due)
    assert res["due"] == due
    items = await pn.list_deadlines(k)
    assert items[0]["text"] == "Tax filing" and items[0]["due"] == due


@pytest.mark.asyncio
async def test_deadline_nudge_within_lead_only(monkeypatch):
    monkeypatch.setenv("PROACTIVE_DEADLINES", "on")
    monkeypatch.setenv("DEADLINE_LEAD_DAYS", "2")
    monkeypatch.setenv("PROACTIVE_SPEAK", "off")
    k = _FakeKeeper()
    await pn.add_deadline(k, "Soon thing", (date.today() + timedelta(days=1)).isoformat())
    await pn.add_deadline(k, "Far thing", (date.today() + timedelta(days=30)).isoformat())

    orch = _StubOrch(keeper=k)
    state = {}
    fired = await pn.check_deadlines(orch, state)
    assert [d["text"] for d in fired] == ["Soon thing"]
    # Same day → deduped.
    assert await pn.check_deadlines(orch, state) == []


# ── Seeker crawl ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_seeker_crawl_surfaces_new_then_dedupes(monkeypatch):
    k = _FakeKeeper()
    await seeker_watch.add_topic(k, "AI agents")

    calls = {"n": 0}
    async def _fake_search(goal, ctx):
        calls["n"] += 1
        return "Big new framework released this week." if calls["n"] == 1 else \
               "Big new framework released this week."   # unchanged on 2nd call
    monkeypatch.setattr("skills.web_search_skill", _fake_search)

    orch = _StubOrch(keeper=k)
    first = await seeker_watch.crawl_once(orch)
    assert [t["topic"] for t in first] == ["AI agents"]
    assert any("AI agents" in str(m) for m in orch.said)

    # Second crawl, same finding → nothing new surfaced.
    assert await seeker_watch.crawl_once(orch) == []


@pytest.mark.asyncio
async def test_seeker_no_topics_is_noop():
    assert await seeker_watch.crawl_once(_StubOrch(keeper=_FakeKeeper())) == []
