# rambo-backend/tests/test_prizepicks_tiers_board.py
from brains.ev import prizepicks_tiers as pt


class FakeRepo:
    def __init__(self):
        self._props = [
            {"mlb_id": 1, "line": 0.5, "book": "prizepicks", "odds_type": "goblin",
             "player_name_raw": "Aaron Judge"},
            {"mlb_id": 1, "line": 0.5, "book": "prizepicks", "odds_type": "standard",
             "player_name_raw": "Aaron Judge"},
            {"mlb_id": 1, "line": 1.5, "book": "prizepicks", "odds_type": "demon",
             "player_name_raw": "Aaron Judge"},
        ]

    def latest_props(self, market=None, official_date=None, odds_type=None):
        assert odds_type is None        # board asks for all tiers
        return list(self._props)

    def player_game_context(self, mlb_id, date):
        return {"team_abbr": "NYY", "opponent_abbr": "BOS"}


def test_tiers_board_builds_ladder(monkeypatch):
    # P(over): goblin 0.5 -> .80, standard 0.5 -> .55, demon 1.5 -> .25
    probs = {("goblin", 0.5): 0.80, ("standard", 0.5): 0.55, ("demon", 1.5): 0.25}
    def fake_p_over(repo, date, market, prop):
        # identify tier by line+the seeded order; here line alone disambiguates demon
        for (tier, line), p in probs.items():
            if line == prop["line"] and tier in pt._TIER_ORDER:
                # pick the tier matching this row's odds_type if present
                if prop.get("odds_type") == tier:
                    return p, "form"
        return None
    monkeypatch.setattr(pt, "_p_over", fake_p_over)
    board = pt.prizepicks_tiers("2026-06-29", "HR", repo=FakeRepo())
    assert board["title"] == "PRIZEPICKS TIERS — HR"
    assert board["count"] == 1
    row = board["rows"][0]
    assert row["name"] == "AARON JUDGE"
    assert set(row["tiers"]) == {"goblin", "standard", "demon"}
    assert row["tiers"]["goblin"] == {"line": 0.5, "model_pct": 80}
    assert row["tiers"]["demon"] == {"line": 1.5, "model_pct": 25}
    assert "ALT" not in board["prompt"] and "TIERS" in board["prompt"].upper()


def test_tiers_board_empty(monkeypatch):
    class Empty(FakeRepo):
        def latest_props(self, market=None, official_date=None, odds_type=None):
            return []
    board = pt.prizepicks_tiers("2026-06-29", "HR", repo=Empty())
    assert board["count"] == 0 and board["rows"] == []
