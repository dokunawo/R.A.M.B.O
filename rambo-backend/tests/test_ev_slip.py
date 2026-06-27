from brains.ev.types import Pick
from brains.ev.slip import build_slip, slip_label, SLIP_SIZE


def _prop(name, model_p, edge, *, market="hr", pick="1+ HOME RUN — OVER",
          team="NYY", opp="BOS"):
    return Pick(market=market, mlb_id=abs(hash(name)) % 100000, name=name, initials="XX",
                team=team, opponent=opp, hand="R", pick=pick, line=0.5, multiplier=2.0,
                breakeven=0.5, model_p=model_p, edge=edge, support="20 HR",
                tags=["EDGE"], glow="gold", headshot_url="u")


def _ml(team, model_p, edge, price):
    return Pick(market="ml", mlb_id=1, name=team, initials=team, team=team, opponent="BAL",
                hand="", pick=f"MONEYLINE LEAN ({price:+d})", line=0.0, multiplier=float(price),
                breakeven=0.31, model_p=model_p, edge=edge, support="vs 5.0 ERA SP",
                tags=["LEAN"], glow="gold", headshot_url="logo")


def test_caps_to_market_size():
    picks = [_prop(f"P{i}", 0.5 - i * 0.01, -0.2) for i in range(10)]
    slip = build_slip(picks, "hr")
    assert slip["count"] == SLIP_SIZE["hr"] == 6
    assert slip["requested"] == 6 and slip["shortfall"] == 0
    assert slip["title"] == "HOME RUNS"


def test_props_ranked_by_hit_probability_not_edge():
    a = _prop("Aaron", 0.30, -0.40)   # best prob, mediocre edge
    b = _prop("Bryce", 0.20, -0.10)   # best edge, worst prob
    c = _prop("Colt", 0.25, -0.50)
    names = [p["name"] for p in build_slip([b, c, a], "hr")["players"]]
    assert names == ["Aaron", "Colt", "Bryce"]            # by model_p desc


def test_moneyline_ranked_by_lean():
    picks = [_ml("WSH", 0.38, 0.02, 118), _ml("HOU", 0.32, 0.07, 440), _ml("PIT", 0.5, 0.05, -120)]
    teams = [p["team"] for p in build_slip(picks, "ml")["players"]]
    assert teams == ["HOU", "PIT", "WSH"]                 # by edge desc


def test_shortfall_reported_when_thin():
    slip = build_slip([_prop("Solo", 0.3, -0.2)], "hr")
    assert slip["count"] == 1 and slip["requested"] == 6 and slip["shortfall"] == 5


def test_count_override():
    picks = [_prop(f"P{i}", 0.4, -0.2) for i in range(8)]
    assert build_slip(picks, "hr", count=3)["count"] == 3


def test_slip_labels():
    assert slip_label(_prop("X", 0.3, -0.2)) == "1+ HOME RUN"
    assert slip_label(_ml("WSH", 0.38, 0.06, 118)) == "WSH ML +118"
    assert slip_label(_ml("CWS", 0.56, 0.01, -131)) == "CWS ML -131"


def test_prompt_contains_all_players_and_title():
    picks = [_prop("Aaron Judge", 0.3, -0.2), _prop("Mike Trout", 0.25, -0.3)]
    slip = build_slip(picks, "hr", count=2)
    assert "HOME RUNS" in slip["prompt"]
    assert "Aaron Judge" in slip["prompt"] and "Mike Trout" in slip["prompt"]
    assert "exactly as written" in slip["prompt"].lower() or "EXACTLY" in slip["prompt"]
