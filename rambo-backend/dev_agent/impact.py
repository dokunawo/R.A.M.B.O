"""Impact analysis — turn a proposed diff into a reviewable judgment.

After the CodingAgent finishes, one LLM pass reads the diff and produces:
  - a plain-language summary of what changed,
  - what it affects in the system (files / modules / endpoints / behaviors),
  - a risk level,
  - a recommendation: "merge" (low-risk, self-contained), "escalate" (wants a
    senior/Claude review), or "hold" (incomplete or risky — don't merge yet).

This is the "what it affects + whether it's smart to merge" surface the operator
sees. Degrades cleanly: with no LLM or empty diff, returns a safe default.
"""
from __future__ import annotations

import logging

import cache_config
import model_config

logger = logging.getLogger(__name__)

RECOMMENDATIONS = ("merge", "escalate", "hold")

_EMIT_TOOL = {
    "name": "emit_impact",
    "description": "Emit the impact assessment for a proposed code change. Call exactly once.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "1-3 sentences: what the change does."},
            "affects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Concrete things this touches: files, modules, endpoints, behaviors.",
            },
            "risk": {"type": "string", "enum": ["low", "medium", "high"]},
            "recommendation": {
                "type": "string",
                "enum": list(RECOMMENDATIONS),
                "description": (
                    "merge = low-risk and self-contained, safe to merge; "
                    "escalate = correct-looking but worth a senior/Claude review before merge; "
                    "hold = incomplete, risky, or out of scope — do not merge."
                ),
            },
            "rationale": {"type": "string", "description": "One sentence on why this recommendation."},
        },
        "required": ["summary", "affects", "risk", "recommendation", "rationale"],
    },
}

_SYSTEM = (
    "You are RAMBO's change reviewer. Given the operator's goal and a unified git "
    "diff of a proposed self-change, assess impact and recommend whether to merge. "
    "Be conservative: prefer 'escalate' or 'hold' when the diff touches core "
    "routing, the agent loop, security, persistence, or anything you can't fully "
    "verify from the diff alone. Reserve 'merge' for small, self-contained, "
    "clearly-correct changes."
)

_MAX_DIFF_CHARS = 24_000


def _default(reason: str) -> dict:
    return {
        "summary": reason,
        "affects": [],
        "risk": "medium",
        "recommendation": "escalate",
        "rationale": "Could not analyze automatically; routing to human/Claude review.",
    }


async def analyze(llm_client, goal: str, diff: str, stat: str = "") -> dict:
    """Return an impact dict. Never raises — falls back to an 'escalate' default."""
    if not diff or not diff.strip():
        return {
            "summary": "The agent produced no changes.",
            "affects": [],
            "risk": "low",
            "recommendation": "hold",
            "rationale": "Empty diff — nothing to merge.",
        }
    if llm_client is None:
        return _default("No LLM available to analyze the change.")

    diff_text = diff[:_MAX_DIFF_CHARS]
    if len(diff) > _MAX_DIFF_CHARS:
        diff_text += "\n... [diff truncated for analysis] ..."

    user = (
        f"Operator goal:\n{goal}\n\n"
        f"Change summary (--stat):\n{stat or '(none)'}\n\n"
        f"Unified diff:\n```diff\n{diff_text}\n```"
    )
    try:
        resp = await llm_client.messages.create(
            model=model_config.default_model(),
            max_tokens=1024,
            system=[{"type": "text", "text": _SYSTEM, "cache_control": cache_config.cache_control()}],
            messages=[{"role": "user", "content": user}],
            tools=[_EMIT_TOOL],
            tool_choice={"type": "tool", "name": "emit_impact"},
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("Impact analysis failed")
        return _default(f"Impact analysis errored: {e}")

    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "emit_impact":
            data = dict(block.input)
            if data.get("recommendation") not in RECOMMENDATIONS:
                data["recommendation"] = "escalate"
            return data
    return _default("Analyzer returned no structured result.")
