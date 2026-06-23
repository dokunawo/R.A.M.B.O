"""Tier 4 — Human-in-the-loop confirmation gate (store).

When a spawned agent calls a tool flagged `requires_confirmation`, the tool
router does NOT execute it. Instead it records a pending confirmation here and
returns a `confirmation_required` result. A human approves (or rejects) via the
/confirmations endpoints; only on approval is the action executed — exactly
once.

In-memory only, mirroring sentinel_queue. The gate lives in the router, not in
the tools themselves.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

_pending: list[dict] = []
_history: list[dict] = []


def request_confirmation(tool_name: str, tool_input: dict, agent_slug: str | None = None) -> dict:
    entry = {
        "id": uuid.uuid4().hex,
        "tool_name": tool_name,
        "tool_input": tool_input,
        "agent_slug": agent_slug,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _pending.append(entry)
    return entry


def list_pending() -> list[dict]:
    return [c for c in _pending if c["status"] == "pending"]


def get(confirmation_id: str) -> dict | None:
    for c in _pending:
        if c["id"] == confirmation_id:
            return c
    return None


def resolve(confirmation_id: str, decision: str) -> dict | None:
    """Mark a confirmation approved/rejected. Returns the record, or None if
    not found or already resolved."""
    for c in _pending:
        if c["id"] == confirmation_id and c["status"] == "pending":
            c["status"] = decision
            c["decided_at"] = datetime.now(timezone.utc).isoformat()
            _history.append(dict(c))
            return c
    return None


def get_history() -> list[dict]:
    return list(_history)


def _reset():  # test helper
    _pending.clear()
    _history.clear()
