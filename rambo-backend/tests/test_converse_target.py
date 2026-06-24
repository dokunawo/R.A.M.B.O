import pytest
from orchestrator.orchestrator import Orchestrator


@pytest.mark.asyncio
async def test_converse_is_a_roster_target():
    o = Orchestrator()
    lines, targets = await o._build_roster()
    assert "converse" in targets
    assert any("converse" in line for line in lines)


@pytest.mark.asyncio
async def test_run_target_converse_does_not_invoke_agents():
    # Built via __new__ so __init__ never ran: there are no agents, no
    # factory, no orchestrate pipeline available. The converse branch must
    # still return a plain string without touching any of them.
    o = Orchestrator.__new__(Orchestrator)
    result = await o._run_target("converse", "say hello", {})
    assert isinstance(result, str)
    assert "error" not in result.lower()
