"""Tests for PrizePicks prep: game_pk resolution."""
from db.migrate import get_connection, apply_migrations
from ingestion.prep import _resolve_prizepicks_game_pks


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def test_resolves_game_pk_for_slate_player(tmp_path):
    conn = _conn(tmp_path)
    now = "2026-06-29T00:00:00Z"
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_id, away_team_id,"
                 " home_team_abbr, away_team_abbr, scraped_at) "
                 "VALUES (900,'2026-06-29',147,111,'NYY','BOS',?)", (now,))
    conn.execute("INSERT INTO players (mlb_id, full_name, current_team_id, updated_at) "
                 "VALUES (592450,'Aaron Judge',147,?)", (now,))
    conn.execute("INSERT INTO prop_lines (game_pk, mlb_id, book, market, line, multiplier,"
                 " player_name_raw, captured_at) VALUES (NULL,592450,'prizepicks','HR',0.5,NULL,"
                 "'Aaron Judge','2026-06-29T18:00:00Z')")
    n = _resolve_prizepicks_game_pks(conn, "2026-06-29")
    assert n == 1
    assert conn.execute("SELECT game_pk FROM prop_lines").fetchone()[0] == 900
