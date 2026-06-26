"""Tests for nightly reflection: gather, parse, synthesize, persist."""

import asyncio
from datetime import datetime, timezone

import pytest

import reflection
from keeper_repo import KeeperRepo
from dispatch_repo import DispatchRepo


def _run(coro):
    return asyncio.run(coro)


# Use the real current day so the test's just-written entries (stamped at the
# actual now) fall inside reflection's "today" window. A hardcoded date made the
# test break the moment the real clock crossed into a different UTC day.
NOW = datetime.now(timezone.utc)


@pytest.fixture
def keeper(tmp_path):
    r = KeeperRepo(db_path=tmp_path / "keeper.db")
    _run(r.init_db())
    return r


@pytest.fixture
def dispatch(tmp_path):
    r = DispatchRepo(db_path=tmp_path / "dispatch.db")
    _run(r.init_db())
    return r


def test_parse_insights_plain_json():
    out = reflection._parse_insights('[{"key": "Likes Jazz", "value": "User prefers jazz"}]')
    assert out == [{"key": "reflection_likes_jazz", "value": "User prefers jazz"}]


def test_parse_insights_with_code_fence():
    text = "Here you go:\n```json\n[{\"key\":\"a\",\"value\":\"b\"}]\n```"
    assert reflection._parse_insights(text) == [{"key": "reflection_a", "value": "b"}]


def test_parse_insights_bad_input():
    assert reflection._parse_insights("not json") == []
    assert reflection._parse_insights("") == []


def test_parse_insights_caps_count():
    items = "[" + ",".join('{"key":"k%d","value":"v%d"}' % (i, i) for i in range(10)) + "]"
    assert len(reflection._parse_insights(items)) == reflection._MAX_INSIGHTS


def test_gather_includes_today_excludes_reflections(keeper, dispatch):
    _run(keeper.write("dog", "Rex"))
    _run(keeper.write("old_insight", "stale", tags=reflection.REFLECTION_TAG))
    _run(dispatch.register("ship the feature"))
    raw = _run(reflection.gather_day_material(dispatch, keeper, NOW))
    assert "dog: Rex" in raw
    assert "ship the feature" in raw
    assert "old_insight" not in raw  # reflection-tagged excluded


def test_gather_empty_when_nothing_today(keeper, dispatch):
    assert _run(reflection.gather_day_material(dispatch, keeper, NOW)) == ""


class _FakeBlock:
    type = "text"
    def __init__(self, text): self.text = text


class _FakeResp:
    def __init__(self, text):
        self.content = [_FakeBlock(text)]
        self.usage = None


class _FakeMessages:
    def __init__(self, text): self._text = text
    async def create(self, **kw): return _FakeResp(self._text)


class _FakeLLM:
    def __init__(self, text): self.messages = _FakeMessages(text)


class _FakeOrch:
    def __init__(self, keeper, dispatch, llm):
        self.keeper_repo = keeper
        self.dispatch_repo = dispatch
        self.llm = llm
        self.broadcasts = []
    async def broadcast(self, msg): self.broadcasts.append(msg)


def test_run_reflection_persists_verified_insights(keeper, dispatch, monkeypatch):
    _run(keeper.write("dog", "Rex"))
    llm = _FakeLLM('[{"key":"pattern","value":"User works late on features"}]')
    orch = _FakeOrch(keeper, dispatch, llm)

    written = _run(reflection.run_reflection(orch, NOW))
    assert written and written[0]["key"] == "reflection_pattern"

    row = _run(keeper.read("reflection_pattern"))
    assert row is not None
    assert row["confidence"] == "verified"
    assert reflection.REFLECTION_TAG in row["tags"]
    assert orch.broadcasts  # announced


def test_run_reflection_noop_without_material(keeper, dispatch):
    llm = _FakeLLM("[]")
    orch = _FakeOrch(keeper, dispatch, llm)
    assert _run(reflection.run_reflection(orch, NOW)) == []
