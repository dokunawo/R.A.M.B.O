# tests/test_walkforward.py
from brains.ev.walkforward import pick_record


def _ev(model_home, book_home, gpk=1):
    return {"game_pk": gpk, "home_abbr": "NYY", "away_abbr": "BOS",
            "model_home": model_home, "model_away": 1 - model_home,
            "book_home": book_home, "book_away": 1 - book_home}


def test_pick_record_leans_home_maps_both_prices():
    ev = _ev(0.60, 0.52)                       # model > book on home -> bet home
    rec = pick_record(ev, win_home=True,
                      early={"home": -120, "away": 100},
                      close={"home": -140, "away": 120})
    assert rec["p"] == 0.60
    assert rec["win"] == 1
    assert rec["odds_early"] == -120
    assert rec["odds_close"] == -140


def test_pick_record_leans_away_uses_away_win_and_prices():
    ev = _ev(0.40, 0.50)                       # model < book on home -> value on away
    rec = pick_record(ev, win_home=False,      # away won
                      early={"home": -120, "away": 100},
                      close={"home": -130, "away": 110})
    assert rec["p"] == 0.60                     # model_away
    assert rec["win"] == 1                      # away won
    assert rec["odds_early"] == 100
    assert rec["odds_close"] == 110


def test_pick_record_none_when_no_lean():
    ev = _ev(0.52, 0.52)                        # no edge either way
    assert pick_record(ev, win_home=True,
                       early={"home": -110, "away": -110},
                       close={"home": -110, "away": -110}) is None


def test_pick_record_none_when_price_missing():
    ev = _ev(0.60, 0.52)
    assert pick_record(ev, win_home=True,
                       early={"home": None, "away": 100},
                       close={"home": -120, "away": 100}) is None
