"""Alt-strikeout board + parlay EV. Joins the k_model P(line+) ladder to real
book (FanDuel + best-of-book) pitcher_strikeouts_alternate odds. Pure-Python
math here; the board/repo glue is added in later tasks. Data-only."""
from __future__ import annotations

import math

from brains.ev.k_model import binom_prob_over
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


def _threshold_for_line(line: float) -> int:
    """Alt over line L is cleared by ceil(L) Ks (7.5 -> 8+)."""
    return math.ceil(line + 1e-9)


def price_legs(proj: dict, odds_rows: list[dict], *,
               thresholds=(8, 9, 10)) -> list[dict]:
    n = round(proj["batters_faced"])
    rate = proj["k_rate"]
    # group priced rows by threshold
    by_t: dict[int, list[dict]] = {}
    for r in odds_rows:
        if r.get("over_price") is None or r.get("line") is None:
            continue
        by_t.setdefault(_threshold_for_line(r["line"]), []).append(r)
    legs = []
    for t in thresholds:
        model_p = round(binom_prob_over(n, rate, t), 4)
        rows = by_t.get(t, [])
        fanduel = None
        for r in rows:
            if (r.get("book") or "").lower() == "fanduel":
                fanduel = {"price": r["over_price"],
                           "ev": leg_ev(model_p, r["over_price"])}
                break
        best = None
        if rows:
            br = max(rows, key=lambda r: american_to_decimal(r["over_price"]))
            best = {"book": br.get("book") or "", "price": br["over_price"],
                    "ev": leg_ev(model_p, br["over_price"])}
        legs.append({"threshold": t, "model_p": model_p,
                     "fanduel": fanduel, "best": best})
    return legs
