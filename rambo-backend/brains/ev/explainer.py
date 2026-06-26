from __future__ import annotations
import logging
from typing import Callable, Optional
from brains.ev.types import Pick

logger = logging.getLogger("rambo.ev.explainer")


def _fallback(pick: Pick) -> str:
    return (f"Model {pick.model_p:.0%} vs break-even {pick.breakeven:.0%} "
            f"({pick.edge:+.0%} edge) on {pick.pick.lower()}.")


def _prompt(picks: list[Pick], market_key: str) -> str:
    lines = [f"You are a sharp MLB betting analyst. For each {market_key.upper()} play, "
             "write ONE punchy sentence (max 18 words) on why it's +EV. "
             "Return exactly one line per play, in order, no numbering.\n"]
    for p in picks:
        lines.append(
            f"- {p.name} ({p.team} vs {p.opponent}, opp hand {p.hand or '?'}): "
            f"{p.pick} at {p.multiplier}x; model {p.model_p:.0%} vs break-even "
            f"{p.breakeven:.0%}; season {p.support}.")
    return "\n".join(lines)


def _anthropic_complete(prompt: str) -> str:
    import os
    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=400,
        messages=[{"role": "user", "content": prompt}])
    return resp.content[0].text


def explain(picks: list[Pick], market_key: str,
            complete: Optional[Callable[[str], str]] = None) -> list[Pick]:
    if not picks:
        return picks
    complete = complete or _anthropic_complete
    try:
        text = complete(_prompt(picks, market_key))
        lines = [ln.strip("-• ").strip() for ln in text.splitlines() if ln.strip()]
        if len(lines) < len(picks):
            raise ValueError("fewer rationales than picks")
        for pick, line in zip(picks, lines):
            pick.rationale = line
    except Exception as exc:
        logger.warning("explainer fell back to templates: %s", exc)
        for pick in picks:
            pick.rationale = _fallback(pick)
    return picks
