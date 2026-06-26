import json
import math
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev.count_model import poisson_prob_over
from brains.ev.market import HRRMarket, SBMarket, REGISTRY


def test_poisson_prob_over():
    # P(X>=2 | Poisson(2)) = 1 - e^-2 (1 + 2)
    assert math.isclose(poisson_prob_over(2.0, 1.5), 1 - math.exp(-2) * 3, rel_tol=1e-9)
    # P(X>=1 | Poisson(0.2)) = 1 - e^-0.2
    assert math.isclose(poisson_prob_over(0.2, 0.5), 1 - math.exp(-0.2), rel_tol=1e-9)
    assert poisson_prob_over(0.0, 0.5) == 0.0


def _seed_batter(conn, mlb_id, name, season_stat):
    now = "2026-06-26T00:00:00Z"
    conn.execute("INSERT INTO players (mlb_id, full_name, throws, current_team_id, updated_at) "
                 "VALUES (?,?,'R',147,?)", (mlb_id, name, now))
    stats = {"season": season_stat, "splits": {}}
    conn.execute("INSERT INTO player_season_stats (mlb_id, season, stat_group, stats, source, "
                 "as_of_date, scraped_at) VALUES (?,2026,'hitting',?,'mlb','2026-06-26',?)",
                 (mlb_id, json.dumps(stats), now))


def _prop(conn, mlb_id, name, market, line, mult):
    conn.execute("INSERT INTO prop_lines (game_pk, mlb_id, book, market, line, multiplier, "
                 "player_name_raw, captured_at) VALUES (NULL,?,'dk_pick6',?,?,?,?,"
                 "'2026-06-26T18:00Z')", (mlb_id, market, line, mult, name))


def test_hrr_market_builds_pick(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    _seed_batter(conn, 1, "Free Swinger",
                 {"hits": 150, "runs": 90, "rbi": 100, "gamesPlayed": 150})
    _prop(conn, 1, "Free Swinger", "H+R+RBI", 1.5, 1.7)
    picks = HRRMarket().raw_picks(MlbRepo(conn), "2026-06-26")
    assert len(picks) == 1
    pk = picks[0]
    assert pk.market == "hrr" and pk.pick == "2+ H+R+RBI — OVER"
    assert pk.support.endswith("H+R+RBI/gm")
    assert 0.5 < pk.model_p < 0.8                 # mean ~2.27 -> P(>=2) ~0.66
    assert pk.edge == round(pk.model_p * 1.7 - 1, 4)


def test_sb_market_builds_pick(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    _seed_batter(conn, 2, "Speed Demon", {"stolenBases": 30, "gamesPlayed": 150})
    _prop(conn, 2, "Speed Demon", "SB", 0.5, 3.0)
    picks = SBMarket().raw_picks(MlbRepo(conn), "2026-06-26")
    assert len(picks) == 1
    pk = picks[0]
    assert pk.market == "sb" and pk.pick == "1+ STOLEN BASE — OVER"
    assert 0.10 < pk.model_p < 0.25               # mean 0.2 -> P(>=1) ~0.18


def test_registry_has_new_markets():
    assert REGISTRY["hrr"].market_key == "hrr"
    assert REGISTRY["sb"].market_key == "sb"
