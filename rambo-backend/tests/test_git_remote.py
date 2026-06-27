"""Guardrails for git_remote: secret scan, no force-push, token never leaks."""
import asyncio
import pytest

from dev_agent import git_remote as gr
from dev_agent.git_workspace import GitWorkspaceError


def test_scan_secrets_flags_and_clears():
    assert gr.scan_secrets("token ghp_ABCDEFGHIJKLMNOPQRSTUVWX") == ["GitHub token"]
    assert "Anthropic API key" in gr.scan_secrets("k = sk-ant-ABCDEFGHIJKLMNOPQRSTUV")
    assert "AWS access key id" in gr.scan_secrets("AKIA1234567890ABCDEF")
    assert gr.scan_secrets("just a normal line of code") == []


def test_push_refuses_force():
    with pytest.raises(GitWorkspaceError, match="force"):
        asyncio.run(gr.push(force=True))


def test_push_refuses_without_token(monkeypatch):
    monkeypatch.delenv("RAMBO_GITHUB_TOKEN", raising=False)
    async def cb(root): return "main"
    monkeypatch.setattr(gr, "current_branch", cb)
    with pytest.raises(GitWorkspaceError, match="RAMBO_GITHUB_TOKEN"):
        asyncio.run(gr.push())


def test_push_refuses_non_github_origin(monkeypatch):
    monkeypatch.setenv("RAMBO_GITHUB_TOKEN", "ghp_token1234567890ABCDEFGH")
    async def cb(root): return "main"
    async def fake_git(root, *args):
        if args[:2] == ("remote", "get-url"):
            return (0, "git@github.com:dokunawo/R.A.M.B.O.git\n")   # ssh, not https
        return (0, "")
    monkeypatch.setattr(gr, "current_branch", cb)
    monkeypatch.setattr(gr, "_git", fake_git)
    with pytest.raises(GitWorkspaceError, match="origin"):
        asyncio.run(gr.push())


def test_push_scrubs_token_from_output(monkeypatch):
    tok = "ghp_SECRETTOKEN1234567890abcdef"
    monkeypatch.setenv("RAMBO_GITHUB_TOKEN", tok)
    async def cb(root): return "main"
    async def fake_git(root, *args):
        if args[:2] == ("remote", "get-url"):
            return (0, "https://github.com/dokunawo/R.A.M.B.O.git\n")
        if args[0] == "push":
            return (0, f"To https://x-access-token:{tok}@github.com/dokunawo/R.A.M.B.O.git\n"
                       " main -> main")
        return (0, "")
    monkeypatch.setattr(gr, "current_branch", cb)
    monkeypatch.setattr(gr, "_git", fake_git)
    res = asyncio.run(gr.push())
    assert res["pushed"] and res["branch"] == "main"
    assert tok not in res["output"] and "***" in res["output"]


def test_owner_repo_parsing():
    assert gr._owner_repo("https://github.com/dokunawo/R.A.M.B.O.git") == ("dokunawo", "R.A.M.B.O")
    assert gr._owner_repo("https://github.com/dokunawo/R.A.M.B.O") == ("dokunawo", "R.A.M.B.O")
    assert gr._owner_repo("git@github.com:foo/bar.git") == ("foo", "bar")


def test_local_merge_refuses_dirty(monkeypatch):
    async def dirty(root): return True
    monkeypatch.setattr(gr, "is_dirty", dirty)
    with pytest.raises(GitWorkspaceError, match="uncommitted"):
        asyncio.run(gr.local_merge("feature", "main"))


def test_local_merge_aborts_on_conflict(monkeypatch):
    async def clean(root): return False
    async def cb(root): return "main"
    monkeypatch.setattr(gr, "is_dirty", clean)
    monkeypatch.setattr(gr, "current_branch", cb)
    seen = []
    async def fake_git(root, *args):
        seen.append(args[:2])
        if args[:2] == ("rev-parse", "--verify"):
            return (0, "")
        if args[0] == "checkout":
            return (0, "")
        if args[:2] == ("merge", "--abort"):
            return (0, "")
        if "merge" in args:                      # the --no-ff merge attempt
            return (1, "CONFLICT (content): Merge conflict in foo.py")
        return (0, "")
    monkeypatch.setattr(gr, "_git", fake_git)
    with pytest.raises(GitWorkspaceError, match="conflict"):
        asyncio.run(gr.local_merge("feature", "main"))
    assert ("merge", "--abort") in seen          # cleaned up after the conflict


class _Resp:
    def __init__(self, code, payload=None, text=""):
        self.status_code, self._p, self.text = code, payload or {}, text
    def json(self): return self._p


class _Client:
    def __init__(self, resp): self._r = resp
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def put(self, *a, **k): return self._r


def _patch_httpx(monkeypatch, resp):
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _Client(resp))


def _patch_origin_token(monkeypatch):
    monkeypatch.setenv("RAMBO_GITHUB_TOKEN", "ghp_token1234567890ABCDEFGH")
    async def fake_git(root, *args):
        if args[:2] == ("remote", "get-url"):
            return (0, "https://github.com/dokunawo/R.A.M.B.O.git\n")
        return (0, "")
    monkeypatch.setattr(gr, "_git", fake_git)


def test_merge_pr_success(monkeypatch):
    _patch_origin_token(monkeypatch)
    _patch_httpx(monkeypatch, _Resp(200, {"merged": True, "message": "Pull Request successfully merged"}))
    res = asyncio.run(gr.merge_pr(12))
    assert res["merged"] and res["pr"] == 12 and res["repo"] == "dokunawo/R.A.M.B.O"


def test_merge_pr_403_explains_scope(monkeypatch):
    _patch_origin_token(monkeypatch)
    _patch_httpx(monkeypatch, _Resp(403, text="Forbidden"))
    with pytest.raises(GitWorkspaceError, match="Pull requests"):
        asyncio.run(gr.merge_pr(12))


def test_merge_pr_405_not_mergeable(monkeypatch):
    _patch_origin_token(monkeypatch)
    _patch_httpx(monkeypatch, _Resp(405, text="Method Not Allowed"))
    with pytest.raises(GitWorkspaceError, match="mergeable"):
        asyncio.run(gr.merge_pr(12))


def test_commit_tracked_refuses_secret_diff(monkeypatch):
    async def fake_git(root, *args):
        if args[0] == "diff" and "--cached" not in args:
            return (0, "+ANTHROPIC_API_KEY=sk-ant-AAAAAAAAAAAAAAAAAAAAAA\n")
        return (0, "")
    monkeypatch.setattr(gr, "_git", fake_git)
    with pytest.raises(GitWorkspaceError, match="secret"):
        asyncio.run(gr.commit_tracked(message="oops"))
