"""Tests for the full-suite test gate before a dev-lane merge."""
import asyncio
from pathlib import Path

import pytest

from dev_agent import session as dev_session
from dev_agent import test_gate


# ── run_full_suite: real pytest in a worktree ─────────────────────────────────
def _worktree_with(tmp_path: Path, body: str) -> Path:
    (tmp_path / "test_sample.py").write_text(body, encoding="utf-8")
    return tmp_path


def test_full_suite_passes_on_green(tmp_path, monkeypatch):
    monkeypatch.setenv("RAMBO_TEST_CWD", "")          # run at the worktree root
    _worktree_with(tmp_path, "def test_ok():\n    assert 1 + 1 == 2\n")
    res = asyncio.run(test_gate.run_full_suite(tmp_path))
    assert res["passed"] is True and res["returncode"] == 0


def test_full_suite_fails_on_red(tmp_path, monkeypatch):
    monkeypatch.setenv("RAMBO_TEST_CWD", "")
    _worktree_with(tmp_path, "def test_bad():\n    assert 1 + 1 == 3\n")
    res = asyncio.run(test_gate.run_full_suite(tmp_path))
    assert res["passed"] is False and res["returncode"] != 0
    assert "output" in res


def test_full_suite_handles_missing_runner(tmp_path, monkeypatch):
    monkeypatch.setenv("RAMBO_TEST_CWD", "")
    monkeypatch.setenv("RAMBO_TEST_CMD", "definitely-not-a-real-binary-xyz")
    _worktree_with(tmp_path, "def test_ok():\n    assert True\n")
    res = asyncio.run(test_gate.run_full_suite(tmp_path))
    assert res["passed"] is False and "not found" in res["error"]


# ── merge_change gating ───────────────────────────────────────────────────────
class _FakeRepo:
    def __init__(self, row):
        self._row = row
        self.status = None

    async def get(self, _cid):
        return self._row

    async def set_status(self, _cid, st):
        self.status = st


def _wire_merge(monkeypatch, tmp_path):
    """Stub git ops so merge_change can run without a real worktree; return a
    dict that records whether the actual merge happened."""
    calls = {"merged": False}

    async def _merge(_ws):
        calls["merged"] = True

    async def _discard(_ws):
        pass

    monkeypatch.setattr(dev_session.gw, "resolve_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(dev_session.gw, "merge", _merge)
    monkeypatch.setattr(dev_session.gw, "discard", _discard)
    return calls


def _row(tmp_path):
    return {"id": "c1", "status": "pending_review", "branch": "dev/c1",
            "worktree_path": str(tmp_path), "base_branch": "main"}


def test_red_suite_blocks_merge(tmp_path, monkeypatch):
    repo = _FakeRepo(_row(tmp_path))
    calls = _wire_merge(monkeypatch, tmp_path)

    async def _red(_wt):
        return {"passed": False, "returncode": 1, "output": "1 failed"}
    monkeypatch.setattr(test_gate, "run_full_suite", _red)

    result = asyncio.run(dev_session.merge_change(repo, "c1", run_full_tests=True))
    assert "test gate failed" in result["error"]
    assert result["tests"]["passed"] is False
    assert calls["merged"] is False          # never merged
    assert repo.status is None               # left reviewable, not marked merged


def test_green_suite_allows_merge_and_reports(tmp_path, monkeypatch):
    repo = _FakeRepo(_row(tmp_path))
    calls = _wire_merge(monkeypatch, tmp_path)

    async def _green(_wt):
        return {"passed": True, "returncode": 0, "output": "42 passed"}
    monkeypatch.setattr(test_gate, "run_full_suite", _green)

    result = asyncio.run(dev_session.merge_change(repo, "c1", run_full_tests=True))
    assert result["status"] == "merged"
    assert result["tests"]["passed"] is True
    assert calls["merged"] is True
    assert repo.status == "merged"


def test_gate_skipped_by_default(tmp_path, monkeypatch):
    repo = _FakeRepo(_row(tmp_path))
    calls = _wire_merge(monkeypatch, tmp_path)

    async def _boom(_wt):
        raise AssertionError("gate must not run when run_full_tests is False")
    monkeypatch.setattr(test_gate, "run_full_suite", _boom)

    result = asyncio.run(dev_session.merge_change(repo, "c1"))   # default: no gate
    assert result["status"] == "merged"
    assert "tests" not in result
    assert calls["merged"] is True
