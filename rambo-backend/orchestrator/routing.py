"""Tier 1 — Smart routing (dispatch intelligence).

An LLM-backed router that reads an explicit routing policy plus the live
roster (core agents + skills + Factory-spawned manifests) and decides, on
purpose, either to:
  - ask ONE clarifying question (when genuinely ambiguous), or
  - dispatch an ORDERED list of steps (decomposing multi-step requests),

routing each step to a concrete target. Routing intelligence lives here in
the conductor; individual agents never see each other.

Falls back to the caller's keyword router when the LLM is unavailable or the
routing call fails — failure isolation (Tier 3) applies to the router too.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RouteStep(BaseModel):
    target: str
    task: str


class RoutingDecision(BaseModel):
    mode: Literal["clarify", "dispatch"]
    question: str = ""
    steps: list[RouteStep] = Field(default_factory=list)


_EMIT_TOOL = {
    "name": "emit_routing_decision",
    "description": (
        "Emit the routing decision. Call this exactly once. Either ask one "
        "clarifying question (mode=clarify) or dispatch an ordered list of "
        "steps (mode=dispatch)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["clarify", "dispatch"]},
            "question": {
                "type": "string",
                "description": "The single clarifying question (mode=clarify only).",
            },
            "steps": {
                "type": "array",
                "description": "Ordered dispatch steps (mode=dispatch only).",
                "items": {
                    "type": "object",
                    "properties": {
                        "target": {"type": "string", "description": "A target name from the roster."},
                        "task": {"type": "string", "description": "The task for that target, in natural language."},
                    },
                    "required": ["target", "task"],
                },
            },
        },
        "required": ["mode"],
    },
}

_POLICY = """\
You are the routing brain of R.A.M.B.O, a multi-agent operator. Your only \
job is to decide WHO handles a request and WHETHER to ask first. You do not \
do the work yourself.

Rules:
1. Pick targets ONLY from the roster below. Never invent a target name.
2. Ordering: a design/planning step must precede an implementation step. If a \
request needs planning then building, emit them as separate ordered steps \
(e.g. architect, then orchestrate/engineer).
3. Decomposition: a multi-step request becomes MULTIPLE ordered steps, not \
one blurred step. A single focused request is one step.
4. Clarify, don't guess: if the request is genuinely ambiguous between two \
targets (you cannot tell which the user means), set mode=clarify and ask ONE \
short question. Do not ask when one target is clearly best.
5. Prefer a specific skill or spawned agent when one squarely fits. Use \
"orchestrate" for open-ended, multi-agent build/research goals that need the \
full planning pipeline. Use a single core agent only for a focused task it \
owns.
6. Keep each step's task in natural language, phrased for that target.

ROSTER:
{roster}

Respond by calling emit_routing_decision exactly once."""


def build_policy(roster_lines: list[str]) -> str:
    return _POLICY.format(roster="\n".join(roster_lines))


class SmartRouter:
    def __init__(self, llm_client, model: str = "claude-sonnet-4-20250514"):
        self._llm = llm_client
        self._model = model

    async def route(
        self,
        goal: str,
        roster_lines: list[str],
        valid_targets: set[str],
    ) -> RoutingDecision | None:
        """Return a validated RoutingDecision, or None to signal fallback."""
        if not self._llm:
            return None
        try:
            response = await self._llm.messages.create(
                model=self._model,
                max_tokens=1024,
                system=[{
                    "type": "text",
                    "text": build_policy(roster_lines),
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": f"Route this request: {goal}"}],
                tools=[_EMIT_TOOL],
                tool_choice={"type": "tool", "name": "emit_routing_decision"},
            )
        except Exception:
            logger.exception("Smart router LLM call failed — falling back")
            return None

        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "emit_routing_decision":
                try:
                    decision = RoutingDecision(**block.input)
                except Exception:
                    logger.exception("Router emitted invalid decision — falling back")
                    return None
                return self._sanitize(decision, valid_targets)

        logger.warning("Router did not emit a decision — falling back")
        return None

    @staticmethod
    def _sanitize(decision: RoutingDecision, valid_targets: set[str]) -> RoutingDecision | None:
        if decision.mode == "clarify":
            if not decision.question.strip():
                return None
            return decision
        # dispatch: keep only steps with known targets; unknown → orchestrate
        cleaned: list[RouteStep] = []
        for step in decision.steps:
            target = step.target if step.target in valid_targets else "orchestrate"
            cleaned.append(RouteStep(target=target, task=step.task or ""))
        if not cleaned:
            return None
        decision.steps = cleaned
        return decision
