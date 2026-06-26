"""Tests for Finnhub finance + Guardian news modules and skill fallback wiring."""

import pytest

import skills
import finance_finnhub as fin
import news_guardian as gnews


# ── Finnhub: pure helpers + no-key degradation ───────────────────
def test_extract_ticker():
    assert fin._extract_ticker("how's NVDA doing") == "NVDA"
    assert fin._extract_ticker("what's AAPL at") == "AAPL"
    assert fin._extract_ticker("apple stock price") is None  # no uppercase ticker


@pytest.mark.asyncio
async def test_finance_lookup_no_key_returns_none(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    assert await fin.finance_lookup("NVDA") is None


# ── Guardian: topic cleaning + no-key degradation ────────────────
def test_topic_cleaning():
    assert gnews._topic("any headlines about AI regulation today").lower() == "ai regulation"
    assert gnews._topic("what's the news") == ""        # no topic → top stories


@pytest.mark.asyncio
async def test_news_lookup_no_key_returns_none(monkeypatch):
    monkeypatch.delenv("GUARDIAN_API_KEY", raising=False)
    assert await gnews.news_lookup("AI") is None


# ── Skill fallback wiring ────────────────────────────────────────
@pytest.mark.asyncio
async def test_news_skill_falls_back_to_web_search(monkeypatch):
    monkeypatch.delenv("GUARDIAN_API_KEY", raising=False)   # Guardian returns None
    async def _fake(goal, ctx): return "WEBSEARCH NEWS"
    monkeypatch.setattr(skills, "web_search_skill", _fake)
    assert await skills.news_skill("AI", {}) == "WEBSEARCH NEWS"


@pytest.mark.asyncio
async def test_news_skill_prefers_guardian(monkeypatch):
    async def _fake_lookup(query): return "GUARDIAN HEADLINES"
    monkeypatch.setattr("news_guardian.news_lookup", _fake_lookup)
    async def _fake_web(goal, ctx): return "should not be used"
    monkeypatch.setattr(skills, "web_search_skill", _fake_web)
    assert await skills.news_skill("AI", {}) == "GUARDIAN HEADLINES"


@pytest.mark.asyncio
async def test_finance_skill_falls_back_when_no_symbol(monkeypatch):
    async def _none(query): return None                     # e.g. market-wide
    monkeypatch.setattr("finance_finnhub.finance_lookup", _none)
    async def _fake_web(goal, ctx): return "WEBSEARCH FINANCE"
    monkeypatch.setattr(skills, "web_search_skill", _fake_web)
    assert await skills.finance_skill("how's the market", {}) == "WEBSEARCH FINANCE"


@pytest.mark.asyncio
async def test_finance_skill_prefers_finnhub(monkeypatch):
    async def _quote(query): return "NVDA: $123.45 ▲ +2.00 (+1.65%) today"
    monkeypatch.setattr("finance_finnhub.finance_lookup", _quote)
    out = await skills.finance_skill("NVDA", {})
    assert "NVDA: $123.45" in out
