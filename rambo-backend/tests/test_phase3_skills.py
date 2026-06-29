"""Tests for Phase 3 domain skills: news, finance, gmail, smart-home."""

import pytest

import skills
import homeassistant_skill as hass
import gmail_skill
from skills import match_skill


# ── Routing/matchers ─────────────────────────────────────────────
@pytest.mark.parametrize("goal,expected", [
    ("what's the news on AI regulation", "news"),
    ("any headlines today", "news"),
    ("how's NVDA doing", "finance"),
    ("what's the stock price of Apple", "finance"),
    ("turn off the lights", "smart-home"),
    ("lock the front door", "smart-home"),
    ("any unread emails", "gmail"),
    ("check my inbox", "gmail"),
])
def test_phase3_matchers(goal, expected):
    s = match_skill(goal)
    assert s is not None and s["name"] == expected


# ── News / finance reuse web_search (Option 1) ───────────────────
@pytest.mark.asyncio
async def test_news_skill_uses_web_search(monkeypatch):
    monkeypatch.delenv("GUARDIAN_API_KEY", raising=False)  # force the web-search fallback path
    captured = {}
    async def _fake(goal, ctx):
        captured["goal"] = goal
        return "Headline A — source X"
    monkeypatch.setattr(skills, "web_search_skill", _fake)
    out = await skills.news_skill("AI regulation", {})
    assert "Headline A" in out
    assert "AI regulation" in captured["goal"]          # tailored prompt carries the topic


@pytest.mark.asyncio
async def test_finance_skill_uses_web_search(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)  # force the web-search fallback path
    async def _fake(goal, ctx):
        assert "NVDA" in goal
        return "NVDA $X, +2%"
    monkeypatch.setattr(skills, "web_search_skill", _fake)
    assert "NVDA" in await skills.finance_skill("NVDA", {})


# ── Smart home: gating + intent parsing ──────────────────────────
@pytest.mark.asyncio
async def test_hass_unconfigured_message(monkeypatch):
    monkeypatch.delenv("HASS_URL", raising=False)
    monkeypatch.delenv("HASS_TOKEN", raising=False)
    assert not hass.is_configured()
    out = await hass.homeassistant_skill("turn off the lights", {})
    assert "isn't configured" in out and "HASS_URL" in out


def test_hass_parse_intent():
    assert hass._parse_intent("turn off the kitchen lights") == ("off", "kitchen lights")
    assert hass._parse_intent("switch on my desk lamp") == ("on", "desk lamp")
    action, name = hass._parse_intent("are the lights on?")
    assert action is None and "lights" in name


# ── Gmail: pure query mapping ────────────────────────────────────
def test_gmail_query_mapping():
    assert gmail_skill._query_for("any important emails")[0] == "is:important is:unread"
    assert gmail_skill._query_for("email from today")[1] == "from today"
    assert gmail_skill._query_for("check my inbox")[0] == "is:unread"
