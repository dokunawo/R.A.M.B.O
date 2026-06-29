import math
from brains.ev import alt_k


def test_leg_ev_positive_when_model_beats_price():
    # +120 -> decimal 2.2; model 0.50 -> 0.50*2.2 - 1 = 0.10
    assert alt_k.leg_ev(0.50, 120) == 0.10


def test_leg_ev_negative_when_model_trails_price():
    # +120 -> 2.2; model 0.40 -> 0.40*2.2 - 1 = -0.12
    assert alt_k.leg_ev(0.40, 120) == -0.12


def test_parlay_ev_two_legs():
    # legs: p=0.5@+120 (dec 2.2), p=0.4@+150 (dec 2.5)
    res = alt_k.parlay_ev([{"p": 0.5, "price": 120}, {"p": 0.4, "price": 150}])
    assert res["combined_p"] == 0.2
    assert res["payout"] == 5.5
    assert res["ev"] == 0.1   # 0.2*5.5 - 1


def test_parlay_ev_empty():
    res = alt_k.parlay_ev([])
    assert res == {"combined_p": 0.0, "payout": 0.0, "ev": -1.0}
