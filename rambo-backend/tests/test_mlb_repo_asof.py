import json
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _game(conn, pk, date, home_id, away_id, hs, as_):
    conn.execute(
        "INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
        "home_team_abbr, away_team_abbr, home_score, away_score, scraped_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (pk, date, home_id, away_id, "AAA", "BBB", hs, as_, "2026-06-28T00:00:00Z"))


def test_team_runs_asof_excludes_target_date_and_after(tmp_path):
    conn = _conn(tmp_path)
    # team 147 home: scores 5 (allows 3) on 06-01, scores 2 (allows 4) on 06-02
    _game(conn, 1, "2026-06-01", 147, 200, 5, 3)
    _game(conn, 2, "2026-06-02", 147, 200, 2, 4)
    _game(conn, 3, "2026-06-03", 147, 200, 9, 9)  # must NOT count for before='2026-06-03'
    repo = MlbRepo(conn)
    r = repo.team_runs_asof(147, 2026, "2026-06-03")
    assert r == {"runs_scored": 7.0, "runs_allowed": 7.0, "games_played": 2}


def test_team_runs_asof_counts_away_games(tmp_path):
    conn = _conn(tmp_path)
    _game(conn, 1, "2026-06-01", 200, 147, 3, 8)  # 147 away: scored 8, allowed 3
    repo = MlbRepo(conn)
    r = repo.team_runs_asof(147, 2026, "2026-06-02")
    assert r == {"runs_scored": 8.0, "runs_allowed": 3.0, "games_played": 1}


def test_team_runs_asof_none_when_no_prior(tmp_path):
    conn = _conn(tmp_path)
    _game(conn, 1, "2026-06-05", 147, 200, 5, 3)
    assert MlbRepo(conn).team_runs_asof(147, 2026, "2026-06-05") is None


def _plog(conn, mlb_id, date, er, outs):
    # Ensure player exists to satisfy foreign key constraint
    conn.execute(
        "INSERT OR IGNORE INTO players (mlb_id, full_name, updated_at) VALUES (?,?,?)",
        (mlb_id, f"Player {mlb_id}", "2026-06-28T00:00:00Z"))
    stats = json.dumps({"stat": {"earnedRuns": er, "outs": outs, "inningsPitched": "x"}})
    conn.execute(
        "INSERT INTO player_game_logs (mlb_id, game_pk, game_date, stat_group, "
        "stats, source, scraped_at) VALUES (?,?,?,?,?,?,?)",
        (mlb_id, None, date, "pitching", stats, "mlb/statsapi:stats", "2026-06-28T00:00:00Z"))


def test_pitcher_era_asof_strict_before(tmp_path):
    conn = _conn(tmp_path)
    _plog(conn, 500, "2026-06-01", 2, 18)   # 6.0 IP, 2 ER
    _plog(conn, 500, "2026-06-02", 1, 9)    # 3.0 IP, 1 ER  -> total 3 ER / 9 IP
    _plog(conn, 500, "2026-06-03", 9, 3)    # must NOT count for before='2026-06-03'
    era = MlbRepo(conn).pitcher_era_asof(500, 2026, "2026-06-03")
    assert abs(era - (9 * 3 / 9.0)) < 1e-9  # 3.00


def test_pitcher_era_asof_none_paths(tmp_path):
    conn = _conn(tmp_path)
    assert MlbRepo(conn).pitcher_era_asof(None, 2026, "2026-06-03") is None
    assert MlbRepo(conn).pitcher_era_asof(500, 2026, "2026-06-03") is None


def test_pitcher_era_asof_excludes_prior_seasons(tmp_path):
    """Pitcher logs from prior seasons must NOT leak into the ERA calculation."""
    conn = _conn(tmp_path)
    # Prior season (2025-09-01) with 1 ER / 3 IP (ERA 3.00)
    _plog(conn, 500, "2025-09-01", 1, 9)
    # Current season (2026-06-01) with 2 ER / 6 IP (ERA 3.00)
    _plog(conn, 500, "2026-06-01", 2, 18)
    # If prior season leaks in: (1+2) ER / 9 IP = 3 ER / 9 IP = 3.00 ERA
    # If prior season excluded: 2 ER / 6 IP = 3 ER / 9 IP = 3.00 ERA (same by coincidence)
    # Use different values to expose leakage: prior season 0 ER / 9 IP
    conn.execute(
        "INSERT OR IGNORE INTO players (mlb_id, full_name, updated_at) VALUES (?,?,?)",
        (501, "Player 501", "2026-06-28T00:00:00Z"))
    stats_prior = json.dumps({"stat": {"earnedRuns": 0, "outs": 9, "inningsPitched": "3.0"}})
    conn.execute(
        "INSERT INTO player_game_logs (mlb_id, game_pk, game_date, stat_group, "
        "stats, source, scraped_at) VALUES (?,?,?,?,?,?,?)",
        (501, None, "2025-09-01", "pitching", stats_prior, "mlb/statsapi:stats", "2026-06-28T00:00:00Z"))
    stats_curr = json.dumps({"stat": {"earnedRuns": 3, "outs": 18, "inningsPitched": "6.0"}})
    conn.execute(
        "INSERT INTO player_game_logs (mlb_id, game_pk, game_date, stat_group, "
        "stats, source, scraped_at) VALUES (?,?,?,?,?,?,?)",
        (501, None, "2026-06-01", "pitching", stats_curr, "mlb/statsapi:stats", "2026-06-28T00:00:00Z"))
    repo = MlbRepo(conn)
    # Query for 2026 season before 2026-06-03
    # If bug present: (0+3) ER / 9 IP = 3.00 ERA (leaks prior season)
    # If bug fixed: 3 ER / 6 IP = 4.50 ERA (only current season)
    era = repo.pitcher_era_asof(501, 2026, "2026-06-03")
    assert abs(era - (9 * 3 / 6.0)) < 1e-9  # 4.50 (only 2026 counts)
