import pytest
import pytest_asyncio
from orchestrator.orchestrator import Orchestrator
from dispatch_repo import DispatchRepo


@pytest_asyncio.fixture
async def orch(tmp_path):
    o = Orchestrator()
    repo = DispatchRepo(db_path=tmp_path / "d.db")
    await repo.init_db()
    o.set_dispatch_repo(repo)
    return o, repo


@pytest.mark.asyncio
async def test_dispatch_context_returns_block_when_present(orch):
    o, repo = orch
    did = await repo.register("earlier goal")
    await repo.update_status(did, "completed", "done earlier")
    ctx_block = await o._dispatch_context()
    assert "RECENTLY COMPLETED" in ctx_block


@pytest.mark.asyncio
async def test_dispatch_context_empty_without_repo():
    o = Orchestrator()
    assert await o._dispatch_context() == ""
