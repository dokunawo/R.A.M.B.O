import json
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev.k_model import k_projection


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _pit_log(conn, mlb_id, date, k, bf):
    conn.execute("INSERT OR IGNORE INTO players (mlb_id, full_name, updated_at) "
                 "VALUES (?,?,?)", (mlb_id, f"P{mlb_id}", "2026-06-28T00:00:00Z"))
    conn.commit()
    stats = json.dumps({"stat": {"strikeOuts": k, "battersFaced": bf}})
    conn.execute(
        "INSERT INTO player_game_logs (mlb_id, game_pk, game_date, stat_group, "
        "stats, source, scraped_at) VALUES (?,?,?,?,?,?,?)",
        (mlb_id, None, date, "pitching", stats, "mlb/statsapi:stats", "2026-06-28T00:00:00Z"))
    conn.commit()


def _hit_log(conn, mlb_id, team_id, date, so, pa):
    conn.execute("INSERT OR IGNORE INTO players (mlb_id, full_name, current_team_id, updated_at) "
                 "VALUES (?,?,?,?)", (mlb_id, f"H{mlb_id}", team_id, "2026-06-28T00:00:00Z"))
    conn.commit()
    stats = json.dumps({"stat": {"strikeOuts": so, "plateAppearances": pa}})
    conn.execute(
        "INSERT INTO player_game_logs (mlb_id, game_pk, game_date, stat_group, "
        "stats, source, scraped_at) VALUES (?,?,?,?,?,?,?)",
        (mlb_id, None, date, "hitting", stats, "mlb/statsapi:stats", "2026-06-28T00:00:00Z"))
    conn.commit()


def _starter(opp_team=None):
    return {"mlb_id": 50, "name": "Ace", "team_abbr": "AAA",
            "opponent_abbr": "BBB", "opponent_team_id": opp_team}


def test_k_projection_basic(tmp_path):
    conn = _conn(tmp_path)
    for d in ("2026-04-01", "2026-04-08", "2026-04-15"):
        _pit_log(conn, 50, d, 7, 25)            # ~0.28 K rate, 25 BF
    repo = MlbRepo(conn)
    proj = k_projection(repo, "2026-05-01", _starter())
    assert proj is not None
    assert 0.20 < proj["k_rate"] < 0.35
    assert 20 <= proj["batters_faced"] <= 30
    assert set(proj["ladder"].keys()) == set(range(1, 11))
    assert proj["k_mean"] > 0


def test_k_projection_opponent_boost_raises_ladder(tmp_path):
    conn = _conn(tmp_path)
    for d in ("2026-04-01", "2026-04-08", "2026-04-15"):
        _pit_log(conn, 50, d, 7, 25)
    # opposing team 200 strikes out a lot (high K%)
    for mid in (201, 202):
        for d in ("2026-04-02", "2026-04-09"):
            _hit_log(conn, mid, 200, d, 3, 5)   # 0.6 K% -> capped boost
    repo = MlbRepo(conn)
    base = k_projection(repo, "2026-05-01", _starter(opp_team=None))
    boosted = k_projection(repo, "2026-05-01", _starter(opp_team=200))
    assert boosted["k_rate"] > base["k_rate"]
    assert boosted["ladder"][9] > base["ladder"][9]


def test_k_projection_none_without_sample(tmp_path):
    conn = _conn(tmp_path)
    assert k_projection(MlbRepo(conn), "2026-05-01", _starter()) is None


def test_k_projection_before_date_respects_season_boundary(tmp_path):
    """Test that k_projection uses before_date to derive season, not date.
    Seed logs in May 2026 and April 2026 with different K rates.
    Call with date="2026-06-01" but before_date="2026-05-01" to ensure
    only pre-May data is used. The projection should reflect pre-May K rate,
    not the blended post-May data."""
    conn = _conn(tmp_path)
    # Pre-cutoff (April): low K rate, 25 BF
    for d in ("2026-04-01", "2026-04-08", "2026-04-15"):
        _pit_log(conn, 50, d, 4, 25)  # ~0.16 K rate (low)
    # Post-cutoff (May): high K rate, 25 BF
    for d in ("2026-05-01", "2026-05-08", "2026-05-15"):
        _pit_log(conn, 50, d, 10, 25)  # ~0.40 K rate (high)
    repo = MlbRepo(conn)
    # Call with before_date="2026-05-01" should only see April data
    proj = k_projection(repo, date="2026-06-01", starter=_starter(),
                        before_date="2026-05-01")
    assert proj is not None
    # Pre-cutoff sample has ~0.16 K rate, post-cutoff has ~0.40 K rate.
    # With before_date in effect, should be closer to 0.16 (pre-May), not blended.
    assert proj["k_rate"] < 0.25, f"Expected low K rate but got {proj['k_rate']}"
