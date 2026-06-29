import math
from brains.ev.prizepicks_parlay import hit_distribution, entry_ev, suggest_entries


def test_hit_distribution_sums_to_one_and_known():
    d = hit_distribution([0.5, 0.5])
    assert math.isclose(sum(d), 1.0, rel_tol=1e-9)
    assert math.isclose(d[0], 0.25) and math.isclose(d[1], 0.5) and math.isclose(d[2], 0.25)


def test_power_ev_pays_only_on_all_hit():
    # 2-pick power pays 3x only if both hit (P=0.25): EV = 0.25*3 - 1 = -0.25
    res = entry_ev([0.5, 0.5], "power")
    assert math.isclose(res["combined_all"], 0.25, rel_tol=1e-9)
    assert math.isclose(res["ev"], 0.25 * 3.0 - 1.0, rel_tol=1e-9)


def test_flex_ev_uses_partial_table():
    # 3-pick flex, all p=0.8. P(3)=0.512, P(2)=3*0.8^2*0.2=0.384
    # EV = 0.512*2.25 + 0.384*1.25 - 1
    res = entry_ev([0.8, 0.8, 0.8], "flex")
    expected = 0.8**3 * 2.25 + (3 * 0.8**2 * 0.2) * 1.25 - 1.0
    assert math.isclose(res["ev"], expected, rel_tol=1e-9)


def test_suggest_returns_best_first():
    legs = [{"name": f"P{i}", "p": p} for i, p in enumerate([0.9, 0.85, 0.6, 0.55])]
    out = suggest_entries(legs, sizes=(2, 3))
    assert out and all("ev" in e for e in out)
    assert out[0]["ev"] >= out[-1]["ev"]            # sorted desc
    assert out[0]["size"] in (2, 3) and out[0]["play_type"] in ("power", "flex")
