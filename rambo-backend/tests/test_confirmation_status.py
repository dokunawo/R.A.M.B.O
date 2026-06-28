"""Tests for the confirmation-status contract that GET /confirmations/{id} relies
on: a resolved confirmation keeps its outcome so a dock can show 'Pushed ✓'."""
from factory import confirmations as c


def setup_function(_):
    c._reset()


def test_pending_then_approved_status_is_retained():
    rec = c.request_confirmation("git_push", {"branch": "main"}, agent_slug="operator")
    assert c.get(rec["id"])["status"] == "pending"

    c.resolve(rec["id"], "approved")
    # The endpoint reads exactly this — status survives resolution.
    got = c.get(rec["id"])
    assert got is not None
    assert got["status"] == "approved"
    assert got["tool_name"] == "git_push"


def test_rejected_status_is_retained():
    rec = c.request_confirmation("git_push", {"branch": "main"})
    c.resolve(rec["id"], "rejected")
    assert c.get(rec["id"])["status"] == "rejected"


def test_unknown_id_is_none():
    assert c.get("nope") is None


def test_resolve_is_idempotent_once_decided():
    rec = c.request_confirmation("git_push", {"branch": "main"})
    assert c.resolve(rec["id"], "approved") is not None
    # second resolve is a no-op (returns None); status stays approved
    assert c.resolve(rec["id"], "rejected") is None
    assert c.get(rec["id"])["status"] == "approved"
