"""Tests for the operator greeting (template fallback + fact assembly)."""

import pytest

import greeting


class _StubKeeper:
    async def read(self, key): return None
    async def query(self, search="", limit=50): return []


class _StubOrch:
    llm = None           # force the template path (no LLM)
    keeper_repo = _StubKeeper()
    factory_repo = None
    dev_repo = None


def test_part_of_day():
    assert greeting._part_of_day(9) == "Good morning"
    assert greeting._part_of_day(14) == "Good afternoon"
    assert greeting._part_of_day(21) == "Good evening"


def test_fact_bits_formats():
    facts = {
        "next_event": {"summary": "Standup", "minutes_until": 12},
        "pending": ["2 actions to approve"],
        "deadlines": [{"text": "Taxes", "due": "2026-07-01"}],
    }
    bits = greeting._fact_bits(facts)
    assert any("Standup" in b and "12 minutes" in b for b in bits)
    assert any("2 actions to approve" in b for b in bits)
    assert any("Taxes" in b for b in bits)


@pytest.mark.asyncio
async def test_greeting_template_fallback_quiet(monkeypatch):
    monkeypatch.setenv("RAMBO_OPERATOR_NAME", "Daniel")
    # No calendar/pending/deadlines → "all quiet" template.
    monkeypatch.setattr(greeting, "_gather", lambda o: _aval({"pending": [], "next_event": None, "deadlines": []}))
    out = await greeting.generate_greeting(_StubOrch())
    assert out.startswith("Good ") and "Daniel" in out and "standing by" in out.lower()


@pytest.mark.asyncio
async def test_greeting_template_with_facts(monkeypatch):
    monkeypatch.setenv("RAMBO_OPERATOR_NAME", "Daniel")
    facts = {"pending": ["1 code change to review"], "next_event": None, "deadlines": []}
    monkeypatch.setattr(greeting, "_gather", lambda o: _aval(facts))
    out = await greeting.generate_greeting(_StubOrch())
    assert "Daniel" in out and "code change to review" in out.lower()


def _aval(value):
    async def _coro(*a, **k):
        return value
    return _coro()
