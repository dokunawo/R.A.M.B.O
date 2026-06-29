"""Alt-strikeout board + parlay EV. Joins the k_model P(line+) ladder to real
book (FanDuel + best-of-book) pitcher_strikeouts_alternate odds. Pure-Python
math here; the board/repo glue is added in later tasks. Data-only."""
from __future__ import annotations

from brains.ev.line_shop import american_to_decimal


def leg_ev(model_p: float, american_price: int) -> float:
    """EV per 1u for a single over leg: model_p * decimal_payout - 1."""
    return round(model_p * american_to_decimal(american_price) - 1.0, 4)


def parlay_ev(legs: list[dict]) -> dict:
    """Independent-leg parlay. legs: [{"p": float, "price": int}, ...].
    combined_p = prod(p); payout = prod(decimal odds); ev = combined_p*payout - 1."""
    if not legs:
        return {"combined_p": 0.0, "payout": 0.0, "ev": -1.0}
    combined_p, payout = 1.0, 1.0
    for leg in legs:
        combined_p *= leg["p"]
        payout *= american_to_decimal(leg["price"])
    return {"combined_p": round(combined_p, 4), "payout": round(payout, 4),
            "ev": round(combined_p * payout - 1.0, 4)}
