from config import the_odds_api as cfg


def test_alt_strikeout_market_is_pulled_and_mapped():
    assert "pitcher_strikeouts_alternate" in cfg.prop_markets()
    assert cfg.PROP_MARKET_MAP["pitcher_strikeouts_alternate"] == "SO_ALT"


def test_standard_strikeout_still_maps_to_so():
    assert cfg.PROP_MARKET_MAP["pitcher_strikeouts"] == "SO"
