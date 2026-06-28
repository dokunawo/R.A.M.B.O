"""Tests for the voice-triggered code-review skill ("review the auth module")."""
import asyncio
import sys
import types

import pytest

import code_review_skill as crs


# ── matcher / routing ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("goal", [
    "review the auth module",
    "Operator, review the auth module",
    "review my changes",
    "review the open changes",
    "review orchestrator.py",
    "review my uncommitted code",
])
def test_match_accepts_code_review_phrases(goal):
    assert crs.match_code_review(goal) is True


@pytest.mark.parametrize("goal", [
    "review my calendar",        # no code cue → must not match
    "review my day",
    "what's the weather",
    "merge PR #5",
])
def test_match_rejects_non_code_phrases(goal):
    assert crs.match_code_review(goal) is False


def test_routes_through_match_skill_and_not_calendar():
    from skills import match_skill
    assert match_skill("review the auth module")["name"] == "code_review"
    assert match_skill("review orchestrator.py")["name"] == "code_review"
    # "review my calendar" must NOT be stolen by code_review
    m = match_skill("review my calendar")
    assert m is None or m["name"] != "code_review"


# ── scope-token parsing ───────────────────────────────────────────────────────
@pytest.mark.parametrize("goal,expected", [
    ("review the auth module", "auth"),
    ("Operator, review the billing module please", "billing"),
    ("review orchestrator.py", "orchestrator.py"),
    ("review my changes", None),
    ("review the open changes", None),
    ("review all my uncommitted code", None),
])
def test_scope_token(goal, expected):
    assert crs._scope_token(goal) == expected


# ── runner: graceful degradation ──────────────────────────────────────────────
def test_runner_degrades_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = asyncio.run(crs.code_review_skill("review the auth module", {}))
    assert "DEGRADED" in out and "ANTHROPIC_API_KEY" in out


def test_runner_reports_clean_tree(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr("os.path.exists", lambda p: True)

    async def _no_changes(*a):
        return (0, "")
    monkeypatch.setattr(crs, "_git", _no_changes)
    out = asyncio.run(crs.code_review_skill("review my changes", {}))
    assert "no open changes" in out.lower()


def test_runner_scope_with_no_matching_files(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr("os.path.exists", lambda p: True)

    async def _git(*args):
        if "--name-only" in args:
            return (0, "rambo-backend/orchestrator.py\n")
        return (0, "")
    monkeypatch.setattr(crs, "_git", _git)
    out = asyncio.run(crs.code_review_skill("review the auth module", {}))
    assert 'No open changes match "auth"' in out
    assert "rambo-backend" in out          # tells the operator what areas ARE changed


# ── runner: full path feeds the scoped diff to the LLM ────────────────────────
def _install_fake_anthropic(monkeypatch, capture: dict, reply: str):
    class _Block:
        type = "text"
        def __init__(self, t): self.text = t

    class _Resp:
        def __init__(self, t): self.content = [_Block(t)]

    class _Msgs:
        async def create(self, **kw):
            capture.update(kw)
            return _Resp(reply)

    class _Client:
        def __init__(self, *a, **k): self.messages = _Msgs()

    fake = types.ModuleType("anthropic")
    fake.AsyncAnthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", fake)


def test_runner_reviews_scoped_diff(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr("os.path.exists", lambda p: True)

    diff_text = ("diff --git a/rambo-backend/auth/login.py "
                 "b/rambo-backend/auth/login.py\n+    return token  # FIXME\n")

    async def _git(*args):
        if "--name-only" in args:
            return (0, "rambo-backend/auth/login.py\nrambo-backend/ui/page.js\n")
        return (0, diff_text)
    monkeypatch.setattr(crs, "_git", _git)

    cap: dict = {}
    _install_fake_anthropic(monkeypatch, cap, "Looks good to commit. Token flow is sound.")

    out = asyncio.run(crs.code_review_skill("review the auth module", {}))
    assert out == "Looks good to commit. Token flow is sound."
    # The scoped diff (auth only) was handed to the model, not the unrelated UI file.
    system = cap["system"]
    assert "auth/login.py" in system and "FIXME" in system
    assert "ui/page.js" not in system
