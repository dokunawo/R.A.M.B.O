"""Tests for dev_agent.builds — slug, path translation, safety, build_app plumbing."""

from pathlib import Path

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
async def test_run_tests_and_run_app(tmp_path, monkeypatch):
    monkeypatch.setenv("RAMBO_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("RAMBO_BUILDS_DIR", str(tmp_path / "builds"))
    proj = tmp_path / "builds" / "proj"
    proj.mkdir(parents=True)
    (proj / "main.py").write_text("print('hello from build')\n", encoding="utf-8")
    (proj / "test_main.py").write_text("def test_x():\n    assert 2 + 2 == 4\n", encoding="utf-8")

    tres = await builds.run_tests("proj")
    assert tres["ok"] is True

    rres = await builds.run_app("proj")
    assert rres["ok"] is True
    assert rres["entry"] == "main.py"
    assert "hello from build" in rres["output"]


@pytest.mark.asyncio
async def test_run_app_finds_nested_entry(tmp_path, monkeypatch):
    """Agent sometimes nests the project a folder deep; run_app should still find
    and run the entry point, reporting its relative path."""
    monkeypatch.setenv("RAMBO_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("RAMBO_BUILDS_DIR", str(tmp_path / "builds"))
    nested = tmp_path / "builds" / "calc" / "calculator"
    nested.mkdir(parents=True)
    (nested / "main.py").write_text("print('nested hello')\n", encoding="utf-8")

    rres = await builds.run_app("calc")
    assert rres["ok"] is True
    assert rres["entry"] == str(Path("calculator") / "main.py")
    assert "nested hello" in rres["output"]


@pytest.mark.asyncio
async def test_run_safety_and_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("RAMBO_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("RAMBO_BUILDS_DIR", str(tmp_path / "builds"))
    (tmp_path / "builds").mkdir(parents=True)
    # escaping slug refused
    assert builds._safe_build_dir("../../etc") is None
    # nonexistent build
    assert (await builds.run_tests("nope")).get("error") == "build not found"
    # build with no entry point
    empty = tmp_path / "builds" / "empty"
    empty.mkdir()
    assert (await builds.run_app("empty")).get("error") == "no runnable .py entry point found"


# Stub coding agent that actually writes a file (a successful build).
class _StubAgent:
    def __init__(self, llm, build_dir, **kw):
        self.build_dir = build_dir
        self.touched = []
    async def run(self, prompt):
        (self.build_dir / "main.py").write_text("print('hi')\n", encoding="utf-8")
        self.touched = ["main.py"]
        return "built a hello script"


@pytest.mark.asyncio
async def test_build_app_plumbing(tmp_path, monkeypatch, repo):
    monkeypatch.setenv("RAMBO_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("RAMBO_BUILDS_DIR", str(tmp_path / "builds"))
    monkeypatch.setenv("RAMBO_HOST_REPO_ROOT", r"C:\X\R.A.M.B.O")
    monkeypatch.setattr(builds, "CodingAgent", _StubAgent)

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


@pytest.mark.asyncio
async def test_build_app_no_files_marks_failed(tmp_path, monkeypatch, repo):
    """A build that writes no files must be marked FAILED, not READY, so the dock
    never shows a runnable card with nothing to run."""
    monkeypatch.setenv("RAMBO_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("RAMBO_BUILDS_DIR", str(tmp_path / "builds"))

    await repo.create("b2", "empty", "Empty", "produces nothing")
    res = await builds.build_app(llm=_FakeLLM(), repo=repo, slug="empty",
                                 name="Empty", goal="produces nothing")
    assert "error" in res
    row = await repo.get_by_slug("empty")
    assert row["status"] == "failed"
