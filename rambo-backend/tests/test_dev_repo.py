"""Tests for dev_agent.repo — code_changes CRUD + status lifecycle."""

import pytest
import pytest_asyncio

from dev_agent.repo import DevRepo


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = DevRepo(db_path=tmp_path / "dev_changes.db")
    await r.init_db()
    return r


@pytest.mark.asyncio
async def test_create_and_get(repo):
    await repo.create("c1", "add a docstring")
    row = await repo.get("c1")
    assert row["goal"] == "add a docstring"
    assert row["status"] == "drafting"
    assert row["impact"] is None


@pytest.mark.asyncio
async def test_set_proposal_moves_to_pending(repo):
    await repo.create("c2", "tweak readme")
    await repo.set_proposal(
        "c2", branch="rambo/dev-c2", worktree_path="/tmp/wt/c2",
        base_branch="main", diff="--- a\n+++ b\n", stat=" 1 file changed",
        impact={"recommendation": "merge", "summary": "small readme tweak",
                "affects": ["README.md"], "risk": "low", "rationale": "trivial"},
    )
    row = await repo.get("c2")
    assert row["status"] == "pending_review"
    assert row["recommendation"] == "merge"
    assert row["impact"]["affects"] == ["README.md"]

    pending = await repo.list_pending()
    assert [p["id"] for p in pending] == ["c2"]


@pytest.mark.asyncio
async def test_status_transitions_and_error(repo):
    await repo.create("c3", "risky change")
    await repo.set_status("c3", "merged")
    assert (await repo.get("c3"))["status"] == "merged"

    await repo.create("c4", "broken change")
    await repo.set_error("c4", "boom")
    row = await repo.get("c4")
    assert row["status"] == "failed"
    assert row["error"] == "boom"

    # merged/failed are not pending
    assert await repo.list_pending() == []
