import math
from brains.ev.hr_model import hr_probability, edge, breakeven

def test_probability_neutral_park():
    assert math.isclose(hr_probability(0.05, 1.0, 4.2), 1 - 0.95 ** 4.2, rel_tol=1e-9)

def test_park_boosts_rate():
    assert hr_probability(0.05, 1.2, 4.2) > hr_probability(0.05, 1.0, 4.2)

def test_rate_clamped():
    assert hr_probability(0.9, 2.0, 4.2) <= 1.0

def test_edge_and_breakeven():
    assert math.isclose(edge(0.40, 2.9), 0.40 * 2.9 - 1, rel_tol=1e-9)
    assert edge(0.30, 2.9) < 0
    assert math.isclose(breakeven(2.9), 1 / 2.9, rel_tol=1e-9)
