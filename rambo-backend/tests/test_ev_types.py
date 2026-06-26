from dataclasses import asdict
from brains.ev.types import Pick, HRFeatures

def test_pick_constructible_and_serializable():
    p = Pick(market="hr", mlb_id=592450, name="AARON JUDGE", initials="AJ",
             team="NYY", opponent="BOS", hand="R", pick="1+ HOME RUN — OVER",
             line=0.5, multiplier=2.5, breakeven=0.4, model_p=0.46, edge=0.15,
             support="58 HR", tags=["EDGE"], glow="gold",
             headshot_url="https://img.mlbstatic.com/...", rationale="")
    d = asdict(p)
    assert d["edge"] == 0.15 and d["tags"] == ["EDGE"] and d["mlb_id"] == 592450

def test_features_constructible():
    f = HRFeatures(mlb_id=592450, name="Aaron Judge", team_abbr="NYY",
                   opponent_abbr="BOS", pitcher_hand="L", hr_rate=0.06,
                   park_factor=1.1, line=0.5, multiplier=2.5, season_hr=58)
    assert f.hr_rate == 0.06
