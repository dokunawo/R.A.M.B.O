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


def k_projection(repo, date: str, starter: dict, before_date: str | None = None,
                 max_j: int = 10) -> dict | None:
    """Opponent-adjusted strikeout distribution for one probable starter, as-of
    `before_date` (defaults to `date` — leak-free for both the live board and the
    backtest). Binomial(round(expected BF), expected K rate). None if no sample."""
    from brains.ev.features import _blend
    bd = before_date or date
    season = int(date[:4])
    mid = starter["mlb_id"]
    season_agg = repo.pitcher_k_aggregate(mid, season, bd)
    if not season_agg or season_agg["bf"] <= 0 or season_agg["starts"] <= 0:
        return None
    recent_agg = repo.pitcher_k_aggregate(mid, season, bd, limit=15)
    season_rate = season_agg["k"] / season_agg["bf"]
    recent_rate = (recent_agg["k"] / recent_agg["bf"]
                   if recent_agg and recent_agg["bf"] > 0 else None)
    base_rate = _blend(recent_rate, season_rate)

    season_bf = season_agg["bf"] / season_agg["starts"]
    recent_bf = (recent_agg["bf"] / recent_agg["starts"]
                 if recent_agg and recent_agg["starts"] > 0 else None)
    exp_bf = _blend(recent_bf, season_bf)
    if base_rate is None or exp_bf is None:
        return None
    exp_bf = _clamp(exp_bf, 15.0, 30.0)

    mod = opponent_modifier(repo.team_k_pct_asof(starter.get("opponent_team_id"),
                                                 season, bd)
                            if starter.get("opponent_team_id") else None)
    k_rate = _clamp(base_rate * mod, 0.05, 0.45)
    n = round(exp_bf)
    return {
        "mlb_id": mid, "name": starter.get("name") or "",
        "team_abbr": starter.get("team_abbr") or "",
        "opponent_abbr": starter.get("opponent_abbr") or "",
        "k_rate": k_rate, "batters_faced": exp_bf, "k_mean": n * k_rate,
        "ladder": ladder(n, k_rate, max_j),
    }
