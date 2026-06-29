from ingestion import prizepicks_apify_client as ppa


def test_adapt_canonical_item():
    raw = {"id": "p1", "player_name": "Aaron Judge", "team": "NYY",
           "position": "OF", "stat_type": "Home Runs", "line": 0.5,
           "odds_type": "standard", "start_time": "2026-06-29T19:00:00-04:00",
           "game_id": "g9"}
    out = ppa._adapt_item(raw)
    assert out == {"projection_id": "p1", "player_name": "Aaron Judge",
                   "team": "NYY", "position": "OF", "stat_type": "Home Runs",
                   "line": 0.5, "odds_type": "standard",
                   "start_time": "2026-06-29T19:00:00-04:00", "game_id": "g9"}


def test_adapt_key_aliases():
    raw = {"projectionId": "p2", "playerName": "Mookie Betts",
           "statType": "Hits", "lineScore": 1.5, "oddsType": "goblin",
           "startTime": "t", "gameId": "g"}
    out = ppa._adapt_item(raw)
    assert out["projection_id"] == "p2"
    assert out["player_name"] == "Mookie Betts"
    assert out["stat_type"] == "Hits"
    assert out["line"] == 1.5
    assert out["odds_type"] == "goblin"


def test_adapt_defaults_odds_type_standard():
    raw = {"player_name": "X", "stat_type": "Hits", "line": 1.5}
    assert ppa._adapt_item(raw)["odds_type"] == "standard"


def test_adapt_drops_missing_required():
    assert ppa._adapt_item({"player_name": "X", "stat_type": "Hits"}) is None   # no line
    assert ppa._adapt_item({"line": 1.5, "stat_type": "Hits"}) is None          # no player
    assert ppa._adapt_item({"player_name": "X", "line": 1.5}) is None           # no stat


def test_adapt_drops_non_mlb_when_league_present():
    raw = {"player_name": "X", "stat_type": "Points", "line": 20.5, "league": "NBA"}
    assert ppa._adapt_item(raw) is None


def test_adapt_keeps_when_no_league_field():
    raw = {"player_name": "X", "stat_type": "Hits", "line": 1.5}
    assert ppa._adapt_item(raw) is not None
