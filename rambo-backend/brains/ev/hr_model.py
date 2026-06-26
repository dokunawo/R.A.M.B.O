from __future__ import annotations

def hr_probability(hr_rate_per_pa: float, park_factor: float,
                   expected_pa: float = 4.2) -> float:
    rate = max(0.0, min(hr_rate_per_pa * park_factor, 0.99))
    return 1.0 - (1.0 - rate) ** expected_pa

def edge(p: float, multiplier: float) -> float:
    return p * multiplier - 1.0

def breakeven(multiplier: float) -> float:
    return 1.0 / multiplier if multiplier else 0.0
