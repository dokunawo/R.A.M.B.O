# rambo-backend/tests/test_alt_k_board.py
from brains.ev import alt_k


class FakeRepo:
    """Minimal repo: one starter with alt-K odds, one with none."""
    def __init__(self):
        self._starters = [
            {"mlb_id": 1, "name": "Ace One", "team_abbr": "SEA",
             "opponent_abbr": "HOU", "game_pk": 100},
            {"mlb_id": 2, "name": "Arm Two", "team_abbr": "LAD",
             "opponent_abbr": "SDP", "game_pk": 200},
        ]
        self._props = [
            {"mlb_id": 1, "line": 7.5, "over_price": 150, "book": "FanDuel"},
            {"mlb_id": 1, "line": 8.5, "over_price": 220, "book": "DraftKings"},
        ]

    def probable_starters(self, date):
        return list(self._starters)

    def latest_props(self, market=None, official_date=None):
        assert market == "SO_ALT"
        return list(self._props)

    def game(self, game_pk):
        return {"home_team_abbr": "SEA", "away_team_abbr": "HOU",
                "home_team_id": 11, "away_team_id": 22}


def _fake_projection(monkeypatch):
    def fake_proj(repo, date, starter, **kw):
        return {"mlb_id": starter["mlb_id"], "name": starter["name"],
                "team_abbr": starter["team_abbr"], "opponent_abbr": starter["opponent_abbr"],
                "k_rate": 0.30, "batters_faced": 24.0, "k_mean": 7.2,
                "ladder": {9: 0.25 if starter["mlb_id"] == 1 else 0.10}}
    monkeypatch.setattr(alt_k.k_model, "k_projection", fake_proj)


def test_alt_k_board_ranks_and_prices(monkeypatch):
    _fake_projection(monkeypatch)
    board = alt_k.alt_k_board("2026-06-29", repo=FakeRepo())
    assert board["title"] == "ALT-K BOARD"
    assert board["count"] == 2
    # pitcher 1 ranked first (higher P(9+))
    assert board["rows"][0]["name"] == "ACE ONE"
    assert board["rows"][0]["rank"] == 1
    # pitcher 1 has priced thresholds; threshold 8 from FanDuel
    t8 = next(t for t in board["rows"][0]["thresholds"] if t["threshold"] == 8)
    assert t8["fanduel"]["price"] == 150
    # pitcher 2 has no odds -> thresholds present but odds None
    t9_p2 = next(t for t in board["rows"][1]["thresholds"] if t["threshold"] == 9)
    assert t9_p2["best"] is None
    assert isinstance(board["prompt"], str) and "ALT-K" in board["prompt"].upper()
