"""Tests for dev_agent.builds — slug, path translation, safety, build_app plumbing."""

import pytest
import pytest_asyncio

from dev_agent import builds
from dev_agent.builds_repo import BuildsRepo


def test_slugify():
    assert builds.slugify("Hello World!") == "hello-world"
    assert builds.slugify("  My App 2  ") == "my-app-2"
    assert builds.slugify("***") == "build"


def test_path_translation_and_safety(tmp_path, monkeypatch):
    monkeypatch.setenv("RAMBO_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("RAMBO_BUILDS_DIR", raising=False)
    monkeypatch.setenv("RAMBO_HOST_REPO_ROOT", r"C:\Users\dokun\PycharmProjects\R.A.M.B.O")

    host = builds.to_host_path(tmp_path / "builds" / "hello")
    assert host == r"C:\Users\dokun\PycharmProjects\R.A.M.B.O\builds\hello"

    assert builds.is_safe_host_path(host) is True
    assert builds.is_safe_host_path(r"C:\Users\dokun\PycharmProjects\R.A.M.B.O") is True
    assert builds.is_safe_host_path(r"C:\Windows\System32") is False
    assert builds.is_safe_host_path(r"C:\Users\dokun\Secrets") is False


# ── Minimal fake LLM that returns immediately (no tool use) ──────────
class _Block:
    type = "text"
    def __init__(self, t): self.text = t


class _Resp:
    def __init__(self, t): self.content = [_Block(t)]; self.stop_reason = "end_turn"


class _Messages:
    async def create(self, **kw): return _Resp("Nothing further.")


class _FakeLLM:
    messages = _Messages()


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = BuildsRepo(db_path=tmp_path / "builds.db")
    await r.init_db()
    return r


@pytest.mark.asyncio
async def test_build_app_plumbing(tmp_path, monkeypatch, repo):
    monkeypatch.setenv("RAMBO_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("RAMBO_BUILDS_DIR", str(tmp_path / "builds"))
    monkeypatch.setenv("RAMBO_HOST_REPO_ROOT", r"C:\X\R.A.M.B.O")

    await repo.create("b1", "hello", "Hello", "a hello script")
    res = await builds.build_app(llm=_FakeLLM(), repo=repo, slug="hello",
                                 name="Hello", goal="a hello script")
    # build dir was created
    assert (tmp_path / "builds" / "hello").is_dir()
    # record marked ready with a translated host path
    row = await repo.get_by_slug("hello")
    assert row["status"] == "ready"
    assert row["host_path"] == r"C:\X\R.A.M.B.O\builds\hello"
    assert res["host_path"] == r"C:\X\R.A.M.B.O\builds\hello"
