from config import prizepicks as pp


def test_stat_market_map_covers_six_markets():
    assert pp.STAT_MARKET_MAP == {
        "Home Runs": "HR", "Pitcher Strikeouts": "SO", "Total Bases": "TB",
        "Hits": "H", "Hits+Runs+RBIs": "H+R+RBI", "Stolen Bases": "SB",
    }
    assert pp.LEAGUE_ID == 2 and pp.SOURCE_ID == "prizepicks"


def test_payout_tables():
    assert pp.POWER[2] == 3.0 and pp.POWER[6] == 37.5
    # Flex partial tables are keyed by leg-count then by hits
    assert pp.FLEX[3][3] == 2.25 and pp.FLEX[3][2] == 1.25
    assert set(pp.FLEX.keys()) == {3, 4, 5, 6}
