"""Git remote ops — commit + push to GitHub, behind the operator's confirmation.

Strictly guarded, because pushing is outward-facing and hard to undo:
  - NEVER force-push.
  - Commit only TRACKED modifications (`git add -u`) — never blindly add untracked
    files (avoids sweeping in junk or secrets).
  - SECRET-SCAN the diff before committing; refuse if anything looks like a key.
  - Push only over `https://github.com/...` origins, using a fine-grained PAT from
    `RAMBO_GITHUB_TOKEN`; the token is injected into an ephemeral URL (never written
    to git config) and SCRUBBED from any returned output.
  - The push itself is gated by the human confirmation queue (see main.py); this
    module only does the mechanics.
"""
from __future__ import annotations

import os
import re

from dev_agent.git_workspace import (
    _git, _git_ok, _IDENT, resolve_repo_root, current_branch, is_dirty, GitWorkspaceError,
)

# Obvious credential shapes — refuse to commit a diff that contains any of these.
_SECRET_PATTERNS = [
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "GitHub token"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "GitHub fine-grained token"),
    (re.compile(r"sk-ant-[A-Za-z0-9\-]{20,}"), "Anthropic API key"),
    (re.compile(r"\bsk-[A-Za-z0-9]{32,}"), "OpenAI-style key"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
    (re.compile(r"(?:ANTHROPIC_API_KEY|ELEVENLABS_API_KEY|VOYAGE_API_KEY|"
                r"APIFY_TOKEN|THE_ODDS_API_KEY|RAMBO_GITHUB_TOKEN)\s*=\s*\S"), "env secret assignment"),
]


def scan_secrets(text: str) -> list[str]:
    """Labels of any secret-looking content found in `text` (empty = clean)."""
    return sorted({label for rx, label in _SECRET_PATTERNS if rx.search(text or "")})


def _token() -> str:
    return os.environ.get("RAMBO_GITHUB_TOKEN", "").strip()


def _scrub(text: str, *secrets: str) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text


async def push_preview(repo_root=None) -> dict:
    """What a push would send: branch, commits-ahead-of-upstream, tracked changes
    that would be committed, and untracked files (which are NOT committed)."""
    root = resolve_repo_root(repo_root)
    branch = await current_branch(root)
    _, porcelain = await _git(root, "status", "--porcelain")
    tracked, untracked = [], []
    for line in porcelain.splitlines():
        if not line.strip():
            continue
        (untracked if line.startswith("??") else tracked).append(line[3:])
    ahead = None
    rc, cnt = await _git(root, "rev-list", "--count", f"origin/{branch}..HEAD")
    if rc == 0 and cnt.strip().isdigit():
        ahead = int(cnt.strip())
    return {"branch": branch, "ahead": ahead,
            "tracked_changes": tracked, "untracked": untracked,
            "token_configured": bool(_token())}


async def commit_tracked(repo_root=None, message: str = "Update via R.A.M.B.O") -> dict:
    """Stage tracked modifications only, secret-scan, then commit. No-op (committed
    False) when there's nothing tracked to commit. Untracked files are ignored."""
    root = resolve_repo_root(repo_root)
    _, diff = await _git(root, "diff", "HEAD")          # working tree vs HEAD (tracked)
    secrets = scan_secrets(diff)
    if secrets:
        raise GitWorkspaceError(
            "refusing to commit — the diff looks like it contains secrets: "
            + ", ".join(secrets) + ". Remove them (or gitignore the file) first.")
    await _git_ok(root, "add", "-u")
    _, staged = await _git(root, "diff", "--cached", "--name-only")
    files = [f for f in staged.splitlines() if f.strip()]
    if not files:
        return {"committed": False, "reason": "no tracked changes to commit", "files": []}
    await _git_ok(root, *_IDENT, "commit", "--no-verify", "-m", message)
    return {"committed": True, "files": files}


async def push(repo_root=None, branch: str | None = None, *, force: bool = False) -> dict:
    """Push the current branch to origin over an authenticated https URL. Never
    force-pushes; refuses detached HEAD, a missing token, or a non-github origin."""
    if force:
        raise GitWorkspaceError("force-push is not allowed")
    root = resolve_repo_root(repo_root)
    branch = branch or await current_branch(root)
    if branch in ("", "HEAD"):
        raise GitWorkspaceError("detached HEAD — check out a branch before pushing")
    token = _token()
    if not token:
        raise GitWorkspaceError(
            "no RAMBO_GITHUB_TOKEN configured — add a fine-grained GitHub PAT "
            "(scoped to this repo, Contents: read/write) to rambo-backend/.env to push")
    _, origin = await _git(root, "remote", "get-url", "origin")
    origin = origin.strip()
    if not origin.startswith("https://github.com/"):
        raise GitWorkspaceError(f"unsupported origin (https github only): {origin or '(none)'}")
    authed = origin.replace("https://", f"https://x-access-token:{token}@", 1)
    rc, out = await _git(root, "push", authed, f"HEAD:{branch}")
    out = _scrub(out, token, authed)
    if rc != 0:
        raise GitWorkspaceError("push failed: " + out.strip()[-500:])
    return {"pushed": True, "branch": branch, "output": out.strip()[-500:]}


async def commit_and_push(repo_root=None, message: str = "Update via R.A.M.B.O",
                          branch: str | None = None) -> dict:
    """The approved action: commit tracked changes (if any) then push. Used after
    the operator confirms."""
    root = resolve_repo_root(repo_root)
    committed = await commit_tracked(root, message)
    pushed = await push(root, branch)
    return {**pushed, "commit": committed}


# ── local branch merge (operator-confirmed) ─────────────────────────────────
async def merge_preview(source: str, target: str | None = None, repo_root=None) -> dict:
    root = resolve_repo_root(repo_root)
    target = target or await current_branch(root)
    rc, _ = await _git(root, "rev-parse", "--verify", source)
    exists = rc == 0
    dirty = await is_dirty(root)
    commits = None
    if exists:
        rc, cnt = await _git(root, "rev-list", "--count", f"{target}..{source}")
        if rc == 0 and cnt.strip().isdigit():
            commits = int(cnt.strip())
    return {"source": source, "target": target, "source_exists": exists,
            "dirty": dirty, "commits": commits}


async def local_merge(source: str, target: str | None = None,
                      message: str | None = None, repo_root=None) -> dict:
    """Merge `source` into `target` (default current branch), --no-ff. Refuses on a
    dirty tree or a missing branch; aborts cleanly on conflict."""
    root = resolve_repo_root(repo_root)
    if await is_dirty(root):
        raise GitWorkspaceError("working tree has uncommitted changes — commit or stash first")
    rc, _ = await _git(root, "rev-parse", "--verify", source)
    if rc != 0:
        raise GitWorkspaceError(f"branch not found: {source}")
    target = target or await current_branch(root)
    rc, out = await _git(root, "checkout", target)
    if rc != 0:
        raise GitWorkspaceError(f"couldn't switch to {target}: {out.strip()[-200:]}")
    msg = message or f"Merge {source} into {target}"
    rc, out = await _git(root, *_IDENT, "merge", "--no-ff", "--no-verify", "-m", msg, source)
    if rc != 0:
        await _git(root, "merge", "--abort")
        raise GitWorkspaceError(
            f"merge had conflicts and was aborted — {target} is unchanged. "
            f"Resolve {source} vs {target} by hand. ({out.strip()[-200:]})")
    return {"merged": True, "source": source, "target": target}


# ── GitHub PR merge (operator-confirmed; needs Pull requests: write) ─────────
def _owner_repo(origin: str) -> tuple[str | None, str | None]:
    m = re.search(r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?/?$", origin or "")
    return (m.group(1), m.group(2)) if m else (None, None)


async def merge_pr(number: int, method: str = "merge", repo_root=None) -> dict:
    token = _token()
    if not token:
        raise GitWorkspaceError("no RAMBO_GITHUB_TOKEN configured — can't merge a PR")
    root = resolve_repo_root(repo_root)
    _, origin = await _git(root, "remote", "get-url", "origin")
    owner, repo = _owner_repo(origin.strip())
    if not owner:
        raise GitWorkspaceError(f"can't parse a GitHub owner/repo from origin: {origin.strip()}")
    import httpx
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}/merge"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.put(url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }, json={"merge_method": method})
    if r.status_code == 200:
        return {"merged": True, "pr": number, "repo": f"{owner}/{repo}",
                "message": (r.json() or {}).get("message", "merged")}
    if r.status_code == 403:
        raise GitWorkspaceError("GitHub refused (403) — your token likely lacks the "
                                "'Pull requests: write' permission. Add it to the PAT.")
    if r.status_code == 404:
        raise GitWorkspaceError(f"PR #{number} not found (or the token can't see it).")
    if r.status_code in (405, 409):
        raise GitWorkspaceError(f"PR #{number} isn't mergeable right now "
                                "(conflicts, failing checks, or branch protection).")
    raise GitWorkspaceError(f"GitHub merge failed ({r.status_code}): {r.text[:200]}")


async def execute_git_confirmation(rec: dict) -> dict:
    """Run an approved git action recorded in the confirmation queue. Shared by the
    HTTP approve endpoint and the voice resolver so the dispatch lives in one place."""
    inp = rec.get("tool_input") or {}
    name = rec.get("tool_name")
    if name == "git_push":
        return await commit_and_push(message=inp.get("message"), branch=inp.get("branch"))
    if name == "git_merge_local":
        return await local_merge(inp["source"], inp.get("target"), inp.get("message"))
    if name == "git_merge_pr":
        return await merge_pr(int(inp["number"]), inp.get("method", "merge"))
    raise GitWorkspaceError(f"unknown git action: {name}")
