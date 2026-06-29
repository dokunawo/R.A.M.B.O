"""PrizePicks entry EV. Each leg has a model probability `p` (the favored side).
hit_distribution is the Poisson-binomial P(exactly k of N hit); entry_ev applies
the Power/Flex payout tables. Pure Python."""
from __future__ import annotations

from itertools import combinations

from config.prizepicks import POWER, FLEX


def hit_distribution(probs: list[float]) -> list[float]:
    """P(exactly k hits) for k=0..len(probs), independent legs (DP)."""
    dist = [1.0]
    for p in probs:
        p = min(1.0, max(0.0, p))
        nxt = [0.0] * (len(dist) + 1)
        for k, val in enumerate(dist):
            nxt[k] += val * (1.0 - p)      # leg misses
            nxt[k + 1] += val * p          # leg hits
        dist = nxt
    return dist


def entry_ev(probs: list[float], play_type: str) -> dict:
    """EV per 1 unit stake = sum_k P(k) * payout(k) - 1."""
    n = len(probs)
    dist = hit_distribution(probs)
    if play_type == "power":
        payout = {n: POWER.get(n, 0.0)}            # pays only when all hit
    elif play_type == "flex":
        payout = FLEX.get(n, {})
    else:
        raise ValueError(f"unknown play_type {play_type!r}")
    ev = sum(dist[k] * payout.get(k, 0.0) for k in range(n + 1)) - 1.0
    return {"combined_all": dist[n], "ev": round(ev, 4)}


def suggest_entries(legs: list[dict], sizes=(2, 3, 4, 5, 6)) -> list[dict]:
    """From the highest-p legs, evaluate Power and Flex at each size; return the
    best entry per (size, play_type), sorted by EV desc."""
    ranked = sorted(legs, key=lambda l: l.get("p", 0.0), reverse=True)
    out: list[dict] = []
    for size in sizes:
        if size > len(ranked):
            continue
        chosen = ranked[:size]
        probs = [l.get("p", 0.0) for l in chosen]
        for play_type in ("power", "flex"):
            if play_type == "flex" and size not in FLEX:
                continue
            res = entry_ev(probs, play_type)
            out.append({"size": size, "play_type": play_type,
                        "legs": [l.get("name") for l in chosen],
                        "combined_all": round(res["combined_all"], 4),
                        "ev": res["ev"]})
    out.sort(key=lambda e: e["ev"], reverse=True)
    return out
