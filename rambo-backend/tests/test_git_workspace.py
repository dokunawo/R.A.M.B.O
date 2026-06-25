"""Tests for dev_agent.git_workspace — worktree isolation, diff, merge, discard."""

import subprocess
from pathlib import Path

import pytest
import pytest_asyncio

from dev_agent import git_workspace as gw


def _run(cwd, *args):
    out = subprocess.run(
        ["git", "-c", "safe.directory=*", *args],
        cwd=str(cwd), capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    return out.stdout


@pytest_asyncio.fixture
async def repo(tmp_path):
    """A temp git repo with one commit on the default branch."""
    root = tmp_path / "repo"
    root.mkdir()
    _run(root, "init")
    _run(root, "config", "user.name", "Test")
    _run(root, "config", "user.email", "test@local")
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    _run(root, "add", "-A")
    _run(root, "commit", "-m", "initial")
    return root


@pytest.mark.asyncio
async def test_create_edit_diff_merge_discard(repo):
    base = await gw.current_branch(repo)

    ws = await gw.create_workspace("abc123", repo_root=repo)
    assert ws.branch == "rambo/dev-abc123"
    assert ws.base_branch == base
    assert ws.worktree_path.exists()
    # The live working tree's README is untouched and base branch has no new commit yet.
    assert (repo / "README.md").read_text(encoding="utf-8") == "hello\n"

    # Agent edits a file INSIDE the worktree only.
    (ws.worktree_path / "README.md").write_text("hello\nworld\n", encoding="utf-8")
    (ws.worktree_path / "new.txt").write_text("brand new\n", encoding="utf-8")

    # Live tree still untouched before commit/merge.
    assert (repo / "README.md").read_text(encoding="utf-8") == "hello\n"
    assert not (repo / "new.txt").exists()

    committed = await gw.commit_paths(ws, "add world + new file", ["README.md", "new.txt"])
    assert committed is True

    d = await gw.diff(ws)
    assert "+world" in d
    assert "brand new" in d
    files = await gw.changed_files(ws)
    assert set(files) == {"README.md", "new.txt"}

    # Still not on the base branch until merge.
    assert (repo / "new.txt").exists() is False

    await gw.merge(ws)
    assert (repo / "README.md").read_text(encoding="utf-8") == "hello\nworld\n"
    assert (repo / "new.txt").read_text(encoding="utf-8") == "brand new\n"
    log = _run(repo, "log", "--oneline")
    assert "merge rambo/dev-abc123" in log

    await gw.discard(ws)
    assert not ws.worktree_path.exists()
    branches = _run(repo, "branch", "--list", ws.branch)
    assert ws.branch not in branches


@pytest.mark.asyncio
async def test_no_change_commit_returns_false(repo):
    ws = await gw.create_workspace("nochange", repo_root=repo)
    committed = await gw.commit_paths(ws, "noop", [])
    assert committed is False
    await gw.discard(ws)


@pytest.mark.asyncio
async def test_merge_refuses_dirty_working_tree(repo):
    ws = await gw.create_workspace("dirty", repo_root=repo)
    (ws.worktree_path / "README.md").write_text("hello\nchange\n", encoding="utf-8")
    await gw.commit_paths(ws, "change", ["README.md"])

    # Dirty the SAME file the merge will touch → real conflict, merge refused.
    (repo / "README.md").write_text("hello\nlocal edit\n", encoding="utf-8")

    with pytest.raises(gw.GitWorkspaceError, match="uncommitted changes"):
        await gw.merge(ws)

    await gw.discard(ws)


@pytest.mark.asyncio
async def test_merge_allows_unrelated_dirty_file(repo):
    # Merge touches README; an unrelated tracked file is dirty → merge still allowed.
    (repo / "other.txt").write_text("v1\n", encoding="utf-8")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-m", "add other")

    ws = await gw.create_workspace("unrel", repo_root=repo)
    (ws.worktree_path / "README.md").write_text("hello\nfrom branch\n", encoding="utf-8")
    await gw.commit_paths(ws, "branch edits readme", ["README.md"])

    # Dirty an UNRELATED file the merge won't touch.
    (repo / "other.txt").write_text("locally edited\n", encoding="utf-8")

    await gw.merge(ws)  # should NOT raise
    assert (repo / "README.md").read_text(encoding="utf-8") == "hello\nfrom branch\n"
    assert (repo / "other.txt").read_text(encoding="utf-8") == "locally edited\n"  # WIP preserved
    await gw.discard(ws)


@pytest.mark.asyncio
async def test_reject_discards_unmerged_branch(repo):
    ws = await gw.create_workspace("rej", repo_root=repo)
    (ws.worktree_path / "junk.txt").write_text("nope\n", encoding="utf-8")
    await gw.commit_paths(ws, "junk", ["junk.txt"])

    await gw.discard(ws)  # reject path: never merged
    assert not ws.worktree_path.exists()
    assert not (repo / "junk.txt").exists()
