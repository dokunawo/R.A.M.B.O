"""Tests for dev_agent.builds_repo."""

import pytest
import pytest_asyncio

from dev_agent.builds_repo import BuildsRepo


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = BuildsRepo(db_path=tmp_path / "builds.db")
    await r.init_db()
    return r


@pytest.mark.asyncio
async def test_create_and_ready(repo):
    await repo.create("b1", "hello-cli", "Hello CLI", "a tiny cli")
    assert await repo.slug_taken("hello-cli") is True
    row = await repo.get_by_slug("hello-cli")
    assert row["status"] == "building"

    await repo.set_ready("hello-cli", rel_path="builds/hello-cli",
                         host_path=r"C:\R.A.M.B.O\builds\hello-cli",
                         files=["main.py", "README.md"], summary="built a cli")
    row = await repo.get_by_slug("hello-cli")
    assert row["status"] == "ready"
    assert row["files"] == ["main.py", "README.md"]
    assert row["host_path"].endswith("hello-cli")

    listed = await repo.list_all()
    assert [b["slug"] for b in listed] == ["hello-cli"]


@pytest.mark.asyncio
async def test_error_path(repo):
    await repo.create("b2", "broken", "Broken", "fails")
    await repo.set_error("broken", "boom")
    row = await repo.get_by_slug("broken")
    assert row["status"] == "failed"
    assert row["error"] == "boom"


@pytest.mark.asyncio
async def test_missing_slug(repo):
    assert await repo.get_by_slug("nope") is None
    assert await repo.slug_taken("nope") is False
