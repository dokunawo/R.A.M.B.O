"""Strikeout distribution model: Binomial(n = expected batters faced, p = expected
per-batter K rate). Gives the full P(1+ … max_j+ K) ladder. Pure Python."""
from __future__ import annotations

import math


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def binom_prob_over(n: int, p: float, j: int) -> float:
    """P(X >= j) for X ~ Binomial(n, p)."""
    if n <= 0:
        return 0.0
    if j <= 0:
        return 1.0
    if j > n:
        return 0.0
    p = _clamp(p, 0.0, 1.0)
    total = sum(math.comb(n, k) * p ** k * (1 - p) ** (n - k)
                for k in range(j, n + 1))
    return _clamp(total, 0.0, 1.0)


def ladder(n: int, p: float, max_j: int = 10) -> dict[int, float]:
    """{1: P(1+ K), …, max_j: P(max_j+ K)}."""
    return {j: binom_prob_over(n, p, j) for j in range(1, max_j + 1)}


LG_K_PCT = 0.22  # league-average batter strikeout rate (K / PA)


def opponent_modifier(opp_k_pct: float | None) -> float:
    """Opposing lineup's K% relative to league, clamped. Neutral (1.0) if unknown."""
    if opp_k_pct is None:
        return 1.0
    return _clamp(opp_k_pct / LG_K_PCT, 0.85, 1.20)
