"""Backtest / evaluation harness — data-agnostic metrics for graded predictions.

A *record* is {p, win, odds}: the model probability for the side bet, whether it
won (bool / 1-0), and the American price taken. Optional `close` = closing
American price for the same side, enabling CLV.

These are pure scoring functions. The predictive model itself and point-in-time
(leak-free) features are a separate research track; this just scores whatever
predictions you feed it, so the model work can iterate against fixed metrics.

Self-contained on purpose (no EV-brain imports) so it can be developed and merged
independently of the line-shop / CLV modules.
"""
from __future__ import annotations

import math

_EPS = 1e-12


def american_to_decimal(odds: int) -> float:
    """Decimal payout incl. stake. +150 -> 2.5, -120 -> 1.8333…"""
    return 1 + (odds / 100 if odds > 0 else 100 / -odds)


def _won(r) -> float:
    return 1.0 if (r["win"] is True or r["win"] == 1) else 0.0


def flat_roi(records) -> float:
    """Profit per 1u flat stake: win → decimal−1, loss → −1."""
    if not records:
        return 0.0
    profit = sum((american_to_decimal(r["odds"]) - 1) if _won(r) else -1.0
                 for r in records)
    return profit / len(records)


def brier(records) -> float:
    if not records:
        return 0.0
    return sum((r["p"] - _won(r)) ** 2 for r in records) / len(records)


def log_loss(records) -> float:
    if not records:
        return 0.0
    tot = 0.0
    for r in records:
        p = min(1 - _EPS, max(_EPS, r["p"]))
        y = _won(r)
        tot += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return tot / len(records)


def calibration(records, bins: int = 10) -> list[dict]:
    """Reliability buckets: predicted vs actual win rate per probability band."""
    out = []
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        grp = [r for r in records
               if (lo <= r["p"] < hi) or (i == bins - 1 and r["p"] >= hi)]
        if grp:
            out.append({
                "bin": [round(lo, 2), round(hi, 2)],
                "n": len(grp),
                "pred": round(sum(g["p"] for g in grp) / len(grp), 4),
                "actual": round(sum(_won(g) for g in grp) / len(grp), 4),
            })
    return out


def avg_clv(records) -> float | None:
    """Mean beat-the-close: taken decimal / closing decimal − 1, over records that
    carry a `close` price (>0 = beat the closing line on average)."""
    vals = [american_to_decimal(r["odds"]) / american_to_decimal(r["close"]) - 1
            for r in records if r.get("close") is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def evaluate(records) -> dict:
    """All metrics in one shot for a set of graded predictions."""
    n = len(records)
    return {
        "n": n,
        "win_rate": round(sum(_won(r) for r in records) / n, 4) if n else None,
        "roi": round(flat_roi(records), 4),
        "brier": round(brier(records), 4),
        "log_loss": round(log_loss(records), 4),
        "avg_clv": avg_clv(records),
        "calibration": calibration(records),
    }
