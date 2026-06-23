"""Tier 5 — Handoff system (propose, don't chain).

An agent can RECOMMEND a next step and which agent should take it, but the
human is always the one who pulls the trigger. No agent dispatches another
directly — that's how errors compound invisibly. Agents propose the graph of
work; the human approves each edge.

A spawned agent proposes a handoff by calling the `propose_handoff` tool, which
records a HandoffRecommendation here. The orchestrator surfaces it as an offer;
on human acceptance it dispatches the target with the proposed task.

In-memory store, mirroring sentinel_queue / confirmations.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class HandoffRecommendation(BaseModel):
    target_agent: str                              # which agent takes the next step
    reason: str                                    # one human-readable sentence on why
    task: str                                      # task to pass the next agent verbatim
    artifacts: dict[str, str] = Field(default_factory=dict)  # refs (paths/IDs/URLs), NOT blobs
    preconditions: list[str] = Field(default_factory=list)   # things the human should verify
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


_pending: list[dict] = []
_history: list[dict] = []


def propose(rec: HandoffRecommendation, from_agent: str | None = None) -> dict:
    entry = {
        "id": uuid.uuid4().hex,
        "from_agent": from_agent,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        **rec.model_dump(),
    }
    _pending.append(entry)
    return entry


def list_pending() -> list[dict]:
    return [h for h in _pending if h["status"] == "pending"]


def get(handoff_id: str) -> dict | None:
    for h in _pending:
        if h["id"] == handoff_id:
            return h
    return None


def resolve(handoff_id: str, decision: str) -> dict | None:
    for h in _pending:
        if h["id"] == handoff_id and h["status"] == "pending":
            h["status"] = decision
            h["decided_at"] = datetime.now(timezone.utc).isoformat()
            _history.append(dict(h))
            return h
    return None


def get_history() -> list[dict]:
    return list(_history)


def _reset():  # test helper
    _pending.clear()
    _history.clear()
