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


def _proj(bf=24, rate=0.30):
    return {"batters_faced": bf, "k_rate": rate}


def test_price_legs_matches_thresholds_and_picks_best_book():
    proj = _proj()
    # line 7.5 -> threshold 8; two books, DraftKings has the better over price
    odds_rows = [
        {"line": 7.5, "over_price": 120, "book": "FanDuel"},
        {"line": 7.5, "over_price": 150, "book": "DraftKings"},
        {"line": 8.5, "over_price": 200, "book": "FanDuel"},   # threshold 9
    ]
    legs = alt_k.price_legs(proj, odds_rows, thresholds=(8, 9, 10))
    by_t = {l["threshold"]: l for l in legs}

    # threshold 8 present, FanDuel + best (DK +150) priced
    assert by_t[8]["fanduel"]["price"] == 120
    assert by_t[8]["best"]["book"] == "DraftKings"
    assert by_t[8]["best"]["price"] == 150
    # model_p == binom_prob_over(24, 0.30, 8)
    from brains.ev.k_model import binom_prob_over
    assert by_t[8]["model_p"] == round(binom_prob_over(24, 0.30, 8), 4)

    # threshold 9 present from FanDuel only -> best is FanDuel
    assert by_t[9]["fanduel"]["price"] == 200
    assert by_t[9]["best"]["price"] == 200

    # threshold 10 has no odds row -> leg still emitted, odds None
    assert by_t[10]["fanduel"] is None
    assert by_t[10]["best"] is None
    assert by_t[10]["model_p"] == round(binom_prob_over(24, 0.30, 10), 4)


def _board():
    return {"rows": [
        {"rank": 1, "name": "ACE ONE", "thresholds": [
            {"threshold": 8, "model_p": 0.55,
             "fanduel": {"price": 120, "ev": 0.21},
             "best": {"book": "DK", "price": 150, "ev": 0.375}},
            {"threshold": 9, "model_p": 0.30,
             "fanduel": {"price": 200, "ev": -0.10},
             "best": {"book": "DK", "price": 210, "ev": -0.07}},
        ]},
        {"rank": 2, "name": "ARM TWO", "thresholds": [
            {"threshold": 8, "model_p": 0.45,
             "fanduel": {"price": 130, "ev": 0.035},
             "best": {"book": "FD", "price": 130, "ev": 0.035}},
        ]},
    ]}


def test_board_to_best_legs_picks_highest_ev_threshold():
    best = alt_k.board_to_best_legs(_board(), book="best")
    assert best[1]["threshold"] == 8       # ev 0.375 beats 9+ (-0.07)
    assert best[1]["price"] == 150
    assert best[2]["threshold"] == 8


def test_suggest_parlays_builds_sizes_and_sorts():
    out = alt_k.suggest_parlays(_board(), sizes=(2,), book="best")
    assert len(out) == 1
    assert out[0]["size"] == 2
    # combined_p = 0.55*0.45 = 0.2475; payout = 2.5*2.3 = 5.75
    assert out[0]["combined_p"] == 0.2475
    assert out[0]["payout"] == 5.75


def test_manual_parlay_resolves_and_flags_missing():
    res = alt_k.manual_parlay(
        _board(),
        [{"name": "ACE ONE", "threshold": 8}, {"name": "GHOST", "threshold": 9}],
        book="best")
    assert res["missing"] == [{"name": "GHOST", "threshold": 9}]
    assert res["ev"] is None     # not all legs priced
