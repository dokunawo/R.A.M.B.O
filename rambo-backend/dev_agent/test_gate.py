"""Full-suite test gate for the dev lane.

Before a drafted self-change is merged into the base branch, optionally run the
WHOLE test suite in the change's isolated worktree — not just the files the
coding agent happened to touch during TDD. A red suite blocks the merge.

Reuses the coding agent's pytest command/cwd config (RAMBO_TEST_CMD /
RAMBO_TEST_CWD) so the gate runs tests exactly the way the lane already does,
just without a path argument (= the entire suite).
"""
from __future__ import annotations

import asyncio
import os
import shlex
from pathlib import Path

from dev_agent.coding_agent import (
    _DEFAULT_TEST_CMD,
    _DEFAULT_TEST_CWD,
    _MAX_TEST_OUTPUT,
)

# The full suite is slower than a single file, so give it more head-room than the
# per-path runner's 180s. Overridable for large suites / slow machines.
_FULL_SUITE_TIMEOUT = int(os.environ.get("RAMBO_FULL_TEST_TIMEOUT", "600"))


async def run_full_suite(worktree_path: str | Path) -> dict:
    """Run the entire pytest suite in the worktree. Returns
    {passed, returncode, output}; on a missing runner or timeout returns
    {passed: False, error}. Never raises — a gate failure must not crash merge."""
    worktree = Path(worktree_path)
    cmd = shlex.split(os.environ.get("RAMBO_TEST_CMD", _DEFAULT_TEST_CMD))
    test_cwd = os.environ.get("RAMBO_TEST_CWD", _DEFAULT_TEST_CWD)
    cwd = (worktree / test_cwd) if test_cwd else worktree
    if not cwd.is_dir():
        cwd = worktree

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,                         # no path argument → whole suite
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            out, _ = await asyncio.wait_for(
                proc.communicate(), timeout=_FULL_SUITE_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return {"passed": False,
                    "error": f"suite timed out after {_FULL_SUITE_TIMEOUT}s"}
    except FileNotFoundError:
        return {"passed": False, "error": f"test runner not found: {cmd[0]}"}

    text = out.decode("utf-8", errors="replace")
    return {
        "passed": proc.returncode == 0,
        "returncode": proc.returncode,
        "output": text[-_MAX_TEST_OUTPUT:],
    }
