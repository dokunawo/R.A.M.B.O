"""Git workspace — the isolation core of RAMBO's self-coding lane.

Every proposed self-change happens inside a dedicated git **worktree** on a
throwaway branch (`rambo/dev-<id>`), branched off the repo's current HEAD. The
coding agent edits files *only* inside that worktree path — never the live
working tree the running process uses, and never `main` directly. The change
reaches the base branch only via `merge()`, which the operator triggers after
review.

Guarded subprocess pattern extends `codebase_skill._git` (which is read-only)
to the write operations needed here, scoped to a resolvable repo root.

Repo root resolution order:
  1. explicit `repo_root` argument
  2. `RAMBO_REPO_ROOT` env var
  3. `git rev-parse --show-toplevel` from this file's location

Worktrees live under `<repo_root>/.rambo-worktrees/<change_id>` (gitignored by
convention; the dir is created on demand and removed on discard/merge-cleanup).
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

# Branches we will never edit or delete directly.
_PROTECTED = {"main", "master"}
# Identity used for RAMBO's own commits/merges (avoids depending on global git config).
_IDENT = ("-c", "user.name=R.A.M.B.O", "-c", "user.email=rambo@local")
_WORKTREE_DIRNAME = ".rambo-worktrees"


class GitWorkspaceError(RuntimeError):
    """Raised when a git operation fails or a safety guard trips."""


@dataclass
class GitWorkspace:
    change_id: str
    repo_root: Path
    base_branch: str
    branch: str
    worktree_path: Path


async def _git(repo_root: Path, *args: str) -> tuple[int, str]:
    """Run a git command at repo_root. Returns (returncode, combined output).

    `-c safe.directory=*` avoids git's dubious-ownership refusal when the repo is
    owned by the host user but the container runs as root (same rationale as
    codebase_skill._git)."""
    proc = await asyncio.create_subprocess_exec(
        "git", "-c", "safe.directory=*", "-C", str(repo_root), *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    return proc.returncode, out.decode("utf-8", errors="replace")


async def _git_ok(repo_root: Path, *args: str) -> str:
    rc, out = await _git(repo_root, *args)
    if rc != 0:
        raise GitWorkspaceError(f"git {' '.join(args)} failed (rc={rc}): {out.strip()}")
    return out


def resolve_repo_root(repo_root: str | Path | None = None) -> Path:
    if repo_root:
        return Path(repo_root).resolve()
    env = os.environ.get("RAMBO_REPO_ROOT")
    if env:
        return Path(env).resolve()
    # Discover the git toplevel from this file's location.
    here = Path(__file__).resolve().parent
    try:
        import subprocess
        out = subprocess.run(
            ["git", "-c", "safe.directory=*", "-C", str(here),
             "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip()).resolve()
    except Exception:
        pass
    # Last resort: assume two levels up (rambo-backend/dev_agent/ -> repo root).
    return here.parent.parent


async def current_branch(repo_root: Path) -> str:
    return (await _git_ok(repo_root, "rev-parse", "--abbrev-ref", "HEAD")).strip()


async def is_dirty(repo_root: Path) -> bool:
    """True if the repo's main working tree has uncommitted changes (any kind)."""
    out = await _git_ok(repo_root, "status", "--porcelain")
    return bool(out.strip())


async def locally_modified(repo_root: Path) -> set[str]:
    """Tracked files with uncommitted modifications (untracked files excluded).

    These are the only files a merge could unsafely clobber — untracked files are
    protected by git itself, so they don't block a merge that doesn't touch them.
    """
    out = await _git_ok(repo_root, "status", "--porcelain", "--untracked-files=no")
    files: set[str] = set()
    for line in out.splitlines():
        path = line[3:].strip()
        if " -> " in path:  # rename: "old -> new"
            path = path.split(" -> ", 1)[1].strip()
        if path:
            files.add(path)
    return files


async def create_workspace(change_id: str,
                           repo_root: str | Path | None = None) -> GitWorkspace:
    """Create an isolated worktree on a fresh `rambo/dev-<id>` branch off HEAD."""
    root = resolve_repo_root(repo_root)
    base = await current_branch(root)
    branch = f"rambo/dev-{change_id}"
    if branch in _PROTECTED:
        raise GitWorkspaceError(f"refusing to use protected branch name {branch!r}")

    # Worktrees live OUTSIDE the main working tree so they never show up as
    # untracked content in `git status` (which would trip the dirty-tree guard).
    wt_root = root.parent / _WORKTREE_DIRNAME
    wt_root.mkdir(parents=True, exist_ok=True)
    worktree_path = wt_root / change_id
    if worktree_path.exists():
        raise GitWorkspaceError(f"worktree path already exists: {worktree_path}")

    await _git_ok(root, "worktree", "add", "-b", branch, str(worktree_path), base)
    return GitWorkspace(
        change_id=change_id, repo_root=root,
        base_branch=base, branch=branch, worktree_path=worktree_path,
    )


async def commit_paths(ws: GitWorkspace, message: str, paths: list[str]) -> bool:
    """Stage ONLY the given worktree-relative paths and commit. Returns False if
    nothing was staged (agent touched nothing, or its edits were no-ops).

    Staging an explicit path set — never `git add -A` — guarantees the committed
    diff reflects exactly what the agent changed, with no unrelated files (e.g.
    runtime-generated artifacts already in the tree) leaking into the review."""
    if not paths:
        return False
    await _git_ok(ws.worktree_path, "add", "--", *paths)
    staged = await _git_ok(ws.worktree_path, "diff", "--cached", "--name-only")
    if not staged.strip():
        return False  # nothing actually changed
    await _git_ok(ws.worktree_path, *_IDENT, "commit", "-m", message)
    return True


async def diff(ws: GitWorkspace, stat: bool = False) -> str:
    """Unified diff (base..branch). With stat=True, return the --stat summary."""
    args = ["diff", f"{ws.base_branch}...{ws.branch}"]
    if stat:
        args.append("--stat")
    return await _git_ok(ws.repo_root, *args)


async def changed_files(ws: GitWorkspace) -> list[str]:
    out = await _git_ok(
        ws.repo_root, "diff", "--name-only", f"{ws.base_branch}...{ws.branch}",
    )
    return [line for line in out.splitlines() if line.strip()]


async def merge(ws: GitWorkspace) -> str:
    """Merge the change branch into the base branch (no-fast-forward).

    Guards: refuses if the main working tree is dirty (would risk clobbering
    operator changes) or if the base branch is somehow protected-but-missing.
    The caller should `discard()` afterward to clean up the worktree.
    """
    if ws.branch in _PROTECTED:
        raise GitWorkspaceError(f"refusing to merge protected branch {ws.branch!r}")
    # Precise guard: block only if the merge would touch a locally-modified file
    # (untracked files and unrelated WIP don't block a clean merge — git itself
    # protects against the collision cases).
    conflicts = (await locally_modified(ws.repo_root)) & set(await changed_files(ws))
    if conflicts:
        raise GitWorkspaceError(
            "merge would touch files with uncommitted changes: "
            f"{sorted(conflicts)} — commit or stash them first"
        )
    on = await current_branch(ws.repo_root)
    if on != ws.base_branch:
        await _git_ok(ws.repo_root, "checkout", ws.base_branch)
    out = await _git_ok(
        ws.repo_root, *_IDENT, "merge", "--no-ff", ws.branch,
        "-m", f"RAMBO self-change {ws.change_id}: merge {ws.branch}",
    )
    return out


async def discard(ws: GitWorkspace) -> None:
    """Remove the worktree and delete the change branch. Idempotent-ish."""
    # Remove worktree first (force, since it may contain uncommitted/extra files).
    await _git(ws.repo_root, "worktree", "remove", "--force", str(ws.worktree_path))
    # Delete the branch (force; it may be unmerged on reject).
    await _git(ws.repo_root, "branch", "-D", ws.branch)
