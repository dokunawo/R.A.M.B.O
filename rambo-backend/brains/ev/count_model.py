from __future__ import annotations
import math

# Shared "count over a line" model for per-game counting props (H+R+RBI, SB, K).
# A player's per-game count is modeled as Poisson(mean); P(over a line L) is the
# probability of clearing it, i.e. P(X >= ceil(L)).  edge/breakeven are reused
# from hr_model (the Pick6 multiplier math is identical).


def poisson_prob_over(mean: float, line: float) -> float:
    """P(X >= ceil(line)) for X ~ Poisson(mean). 'over 1.5' -> P(X >= 2)."""
    if mean <= 0:
        return 0.0
    threshold = math.ceil(line)
    cdf_below = 0.0
    for k in range(threshold):
        cdf_below += math.exp(-mean) * mean ** k / math.factorial(k)
    return max(0.0, 1.0 - cdf_below)
