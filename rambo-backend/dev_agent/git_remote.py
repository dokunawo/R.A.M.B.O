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
    _git, _git_ok, _IDENT, resolve_repo_root, current_branch, GitWorkspaceError,
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
