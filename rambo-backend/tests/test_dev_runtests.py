"""Tests for the CodingAgent run_tests tool — closed-loop TDD execution."""

import json

import pytest

from dev_agent.coding_agent import CodingAgent


def _agent(worktree, monkeypatch):
    # Run pytest from the worktree root (these fixtures put test files there).
    monkeypatch.setenv("RAMBO_TEST_CWD", "")
    return CodingAgent(llm_client=None, worktree_path=worktree, playbooks="")


@pytest.fixture
def worktree(tmp_path):
    (tmp_path / "test_pass.py").write_text("def test_ok():\n    assert 1 + 1 == 2\n", encoding="utf-8")
    (tmp_path / "test_fail.py").write_text("def test_bad():\n    assert 1 + 1 == 3\n", encoding="utf-8")
    return tmp_path


@pytest.mark.asyncio
async def test_passing_test_reports_passed(worktree, monkeypatch):
    agent = _agent(worktree, monkeypatch)
    res = json.loads(await agent._exec_tool("run_tests", {"path": "test_pass.py"}))
    assert res["passed"] is True
    assert res["returncode"] == 0


@pytest.mark.asyncio
async def test_failing_test_reports_failed(worktree, monkeypatch):
    agent = _agent(worktree, monkeypatch)
    res = json.loads(await agent._exec_tool("run_tests", {"path": "test_fail.py"}))
    assert res["passed"] is False
    assert res["returncode"] != 0
    assert "assert" in res["output"].lower() or "fail" in res["output"].lower()


@pytest.mark.asyncio
async def test_run_tests_confined_to_worktree(worktree, monkeypatch):
    agent = _agent(worktree, monkeypatch)
    res = json.loads(await agent._exec_tool("run_tests", {"path": "../escape.py"}))
    assert "error" in res and "escape" in res["error"].lower()


@pytest.mark.asyncio
async def test_run_tests_missing_path(worktree, monkeypatch):
    agent = _agent(worktree, monkeypatch)
    res = json.loads(await agent._exec_tool("run_tests", {"path": "nope.py"}))
    assert "error" in res and "not found" in res["error"].lower()


def test_run_tests_in_tool_list():
    agent = CodingAgent(llm_client=None, worktree_path=".", playbooks="")
    from dev_agent.coding_agent import _tool_defs
    assert any(t["name"] == "run_tests" for t in _tool_defs())
