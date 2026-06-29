# tests/test_prizepicks_board.py
import json
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev.prizepicks_board import prizepicks_board


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _seed_hr(conn, mlb_id=592450, team=147):
    now = "2026-06-29T00:00:00Z"
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_id, away_team_id,"
                 " home_team_abbr, away_team_abbr, scraped_at) "
                 "VALUES (900,'2026-06-29',?,111,'NYY','BOS',?)", (team, now))
    conn.execute("INSERT INTO players (mlb_id, full_name, bats, current_team_id, updated_at) "
                 "VALUES (?,?,'R',?,?)", (mlb_id, "Aaron Judge", team, now))
    stats = {"season": {"homeRuns": 50, "plateAppearances": 600}, "splits": {}}
    conn.execute("INSERT INTO player_season_stats (mlb_id, season, stat_group, stats, source,"
                 " as_of_date, scraped_at) VALUES (?,2026,'hitting',?,'mlb','2026-06-29',?)",
                 (mlb_id, json.dumps(stats), now))
    conn.execute("INSERT INTO prop_lines (game_pk, mlb_id, book, market, line, multiplier,"
                 " player_name_raw, captured_at) VALUES (900,?,'prizepicks','HR',0.5,NULL,"
                 "'Aaron Judge','2026-06-29T18:00:00Z')", (mlb_id,))


def test_hr_board_ranks_by_model_prob(tmp_path):
    conn = _conn(tmp_path)
    _seed_hr(conn)
    board = prizepicks_board("2026-06-29", "HR", repo=MlbRepo(conn))
    assert board["product"] == "PrizePicks"
    assert board["count"] == 1
    r = board["rows"][0]
    assert r["name"] == "AARON JUDGE" and r["stat"] == "HR" and r["line"] == 0.5
    assert r["side"] in ("over", "under")
    assert 0 <= r["model_pct"] <= 100


def test_board_skips_player_not_on_slate(tmp_path):
    conn = _conn(tmp_path)
    _seed_hr(conn)
    # ask for a different date with no game for this player
    assert prizepicks_board("2026-06-30", "HR", repo=MlbRepo(conn))["count"] == 0
