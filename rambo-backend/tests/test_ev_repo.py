from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo

def _seed(conn):
    now = "2026-06-26T00:00:00Z"
    conn.execute("INSERT INTO players (mlb_id, full_name, throws, current_team_id, updated_at) "
                 "VALUES (592450,'Aaron Judge','R',147,?)", (now,))
    conn.execute("INSERT INTO players (mlb_id, full_name, throws, current_team_id, updated_at) "
                 "VALUES (222,'Lefty Pitcher','L',111,?)", (now,))
    conn.execute(
        "INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
        "home_team_abbr, away_team_abbr, home_probable_pitcher_id, away_probable_pitcher_id, "
        "scraped_at) VALUES (999,'2026-06-26',147,111,'NYY','BOS',111,222,?)", (now,))

def test_player_game_context_home_batter(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    _seed(conn)
    ctx = MlbRepo(conn).player_game_context(592450, "2026-06-26")
    assert ctx["game_pk"] == 999 and ctx["is_home"] is True
    assert ctx["team_abbr"] == "NYY" and ctx["opponent_abbr"] == "BOS"
    assert ctx["home_abbr"] == "NYY" and ctx["opp_pitcher_id"] == 222   # away pitcher

def test_pitcher_throws(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    _seed(conn)
    assert MlbRepo(conn).pitcher_throws(222) == "L"
    assert MlbRepo(conn).pitcher_throws(999999) is None
