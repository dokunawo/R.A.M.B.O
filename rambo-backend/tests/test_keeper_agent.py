import pytest
import pytest_asyncio
from orchestrator.orchestrator import Orchestrator
from keeper_repo import KeeperRepo


@pytest_asyncio.fixture
async def orch(tmp_path):
    o = Orchestrator.__new__(Orchestrator)   # bypass full __init__
    repo = KeeperRepo(db_path=tmp_path / "k.db")
    await repo.init_db()
    o.keeper_repo = repo
    return o, repo


@pytest.mark.asyncio
async def test_keeper_save(orch):
    o, repo = orch
    out = await o._run_keeper("remember my favorite color is blue")
    assert "Stored" in out
    assert (await repo.read("favorite_color"))["value"] == "blue"


@pytest.mark.asyncio
async def test_keeper_recall(orch):
    o, repo = orch
    await o._run_keeper("remember my favorite color is blue")
    out = await o._run_keeper("what is my favorite color")
    assert "blue" in out.lower()


@pytest.mark.asyncio
async def test_keeper_recall_plural_drift(orch):
    o, repo = orch
    await o._run_keeper("remember my dog's name is Rex")
    out = await o._run_keeper("what is my dogs name")
    assert "rex" in out.lower()


@pytest.mark.asyncio
async def test_keeper_recall_miss(orch):
    o, repo = orch
    out = await o._run_keeper("what is my spaceship")
    assert "nothing stored" in out.lower()


@pytest.mark.asyncio
async def test_keeper_no_repo_is_safe():
    o = Orchestrator.__new__(Orchestrator)   # no keeper_repo attribute
    out = await o._run_keeper("remember x is y")
    assert "no memory store" in out.lower()
