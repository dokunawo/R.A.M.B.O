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


def test_commit_tracked_refuses_secret_diff(monkeypatch):
    async def fake_git(root, *args):
        if args[0] == "diff" and "--cached" not in args:
            return (0, "+ANTHROPIC_API_KEY=sk-ant-AAAAAAAAAAAAAAAAAAAAAA\n")
        return (0, "")
    monkeypatch.setattr(gr, "_git", fake_git)
    with pytest.raises(GitWorkspaceError, match="secret"):
        asyncio.run(gr.commit_tracked(message="oops"))
