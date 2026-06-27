from __future__ import annotations
import logging
from typing import Callable, Optional
from brains.ev.types import Pick

logger = logging.getLogger("rambo.ev.explainer")


def _fallback(pick: Pick) -> str:
    if pick.market == "ml":   # moneyline: an honest lean vs the market, never a lock
        return (f"Model {pick.model_p:.0%} vs market {pick.breakeven:.0%} — "
                f"a {pick.edge:+.0%} lean, not a lock.")
    if pick.edge > 0:
        return (f"Model {pick.model_p:.0%} vs break-even {pick.breakeven:.0%} "
                f"({pick.edge:+.0%} edge) on {pick.pick.lower()}.")
    return (f"Model {pick.model_p:.0%} vs break-even {pick.breakeven:.0%} "
            f"({pick.edge:+.0%}) — −EV, skip.")


def _prompt(picks: list[Pick], market_key: str) -> str:
    if market_key == "ml":
        head = ("You are a sharp, HONEST MLB analyst. For each moneyline play, write ONE "
                "sentence (max 18 words) on why the model LEANS this side vs the market. "
                "It's a small lean, NOT a +EV lock — don't overhype. "
                "Return exactly one line per play, in order, no numbering.\n")
    else:
        head = (f"You are a sharp MLB betting analyst. For each {market_key.upper()} play, "
                "write ONE punchy sentence (max 18 words) on why it's +EV. "
                "Return exactly one line per play, in order, no numbering.\n")
    lines = [head]
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
    # Honest template for everyone first; then upgrade only the genuine plays
    # (+edge / leans) via the LLM. −EV candidates never hit the LLM — the card
    # pulls them only for transparency, so they don't warrant a paid call.
    for pick in picks:
        pick.rationale = _fallback(pick)
    plays = [p for p in picks if p.edge > 0]
    if not plays:
        return picks
    complete = complete or _anthropic_complete
    try:
        text = complete(_prompt(plays, market_key))
        lines = [ln.strip("-• ").strip() for ln in text.splitlines() if ln.strip()]
        if len(lines) < len(plays):
            raise ValueError("fewer rationales than plays")
        for pick, line in zip(plays, lines):
            pick.rationale = line
    except Exception as exc:
        logger.warning("explainer fell back to templates: %s", exc)  # plays keep template
    return picks
