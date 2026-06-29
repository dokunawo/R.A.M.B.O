import json
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _player(conn, mlb_id, team_id):
    conn.execute("INSERT INTO players (mlb_id, full_name, current_team_id, updated_at) "
                 "VALUES (?,?,?,?)", (mlb_id, f"P{mlb_id}", team_id, "2026-06-28T00:00:00Z"))


def _game(conn, game_pk, official_date):
    conn.execute(
        "INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, scraped_at) "
        "VALUES (?,?,?,?,?)",
        (game_pk, official_date, 100, 200, "2026-06-28T00:00:00Z"))


def _hit_log(conn, mlb_id, date, so, pa):
    stats = json.dumps({"stat": {"strikeOuts": so, "plateAppearances": pa}})
    conn.execute(
        "INSERT INTO player_game_logs (mlb_id, game_pk, game_date, stat_group, "
        "stats, source, scraped_at) VALUES (?,?,?,?,?,?,?)",
        (mlb_id, None, date, "hitting", stats, "mlb/statsapi:stats", "2026-06-28T00:00:00Z"))


def _pit_log(conn, mlb_id, date, k, bf):
    stats = json.dumps({"stat": {"strikeOuts": k, "battersFaced": bf}})
    conn.execute(
        "INSERT INTO player_game_logs (mlb_id, game_pk, game_date, stat_group, "
        "stats, source, scraped_at) VALUES (?,?,?,?,?,?,?)",
        (mlb_id, None, date, "pitching", stats, "mlb/statsapi:stats", "2026-06-28T00:00:00Z"))


def test_team_k_pct_asof_strict_before_and_team(tmp_path):
    conn = _conn(tmp_path)
    _game(conn, 1, "2026-05-01"); _game(conn, 2, "2026-05-02"); _game(conn, 3, "2026-05-10")
    _player(conn, 1, 100); _player(conn, 2, 100); _player(conn, 9, 999)  # 9 on other team
    _hit_log(conn, 1, "2026-05-01", 2, 5)
    _hit_log(conn, 2, "2026-05-02", 1, 5)
    _hit_log(conn, 9, "2026-05-02", 5, 5)            # different team — excluded
    _hit_log(conn, 1, "2026-05-10", 9, 9)            # on/after before_date — excluded
    conn.commit()
    repo = MlbRepo(conn)
    # before 05-10: team 100 has (2+1) K over (5+5) PA = 0.3
    assert abs(repo.team_k_pct_asof(100, 2026, "2026-05-10") - 0.3) < 1e-9


def test_team_k_pct_asof_none_without_pa(tmp_path):
    conn = _conn(tmp_path)
    assert MlbRepo(_conn(tmp_path)).team_k_pct_asof(100, 2026, "2026-05-01") is None


def test_pitcher_k_aggregate_all_and_limited(tmp_path):
    conn = _conn(tmp_path)
    _game(conn, 1, "2026-04-01"); _game(conn, 2, "2026-04-08"); _game(conn, 3, "2026-04-15"); _game(conn, 4, "2026-05-01")
    _player(conn, 50, 100)  # pitcher belongs to a team
    _pit_log(conn, 50, "2026-04-01", 6, 24)
    _pit_log(conn, 50, "2026-04-08", 8, 25)
    _pit_log(conn, 50, "2026-04-15", 10, 26)
    _pit_log(conn, 50, "2026-05-01", 99, 99)         # on/after before_date — excluded
    conn.commit()
    repo = MlbRepo(conn)
    allagg = repo.pitcher_k_aggregate(50, 2026, "2026-05-01")
    assert allagg == {"k": 24.0, "bf": 75.0, "starts": 3}
    last2 = repo.pitcher_k_aggregate(50, 2026, "2026-05-01", limit=2)
    assert last2 == {"k": 18.0, "bf": 51.0, "starts": 2}   # the two most recent
    assert repo.pitcher_k_aggregate(50, 2026, "2026-03-01") is None
