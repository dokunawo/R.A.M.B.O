import math
from brains.ev.k_model import binom_prob_over, ladder, opponent_modifier, LG_K_PCT


def test_binom_prob_over_known_values():
    # X ~ Binomial(4, 0.25): P(X>=1) = 1 - 0.75^4
    assert math.isclose(binom_prob_over(4, 0.25, 1), 1 - 0.75 ** 4, rel_tol=1e-9)
    # P(X>=4) = 0.25^4
    assert math.isclose(binom_prob_over(4, 0.25, 4), 0.25 ** 4, rel_tol=1e-9)


def test_binom_prob_over_guards():
    assert binom_prob_over(0, 0.3, 1) == 0.0      # n<=0
    assert binom_prob_over(5, 0.3, 0) == 1.0      # j<=0 -> certain
    assert binom_prob_over(5, 0.3, 6) == 0.0      # j>n
    p = binom_prob_over(24, 0.25, 8)
    assert 0.0 <= p <= 1.0


def test_ladder_is_monotone_decreasing():
    lad = ladder(24, 0.25, max_j=10)
    assert set(lad.keys()) == set(range(1, 11))
    vals = [lad[j] for j in range(1, 11)]
    assert all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1))
    assert vals[0] <= 1.0


def test_opponent_modifier_clamp_and_none():
    assert opponent_modifier(None) == 1.0
    assert opponent_modifier(LG_K_PCT) == 1.0                 # league avg -> neutral
    assert opponent_modifier(0.40) == 1.20                    # high-K lineup -> capped boost
    assert opponent_modifier(0.05) == 0.85                    # contact lineup -> capped fade
