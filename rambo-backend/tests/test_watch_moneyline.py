import json
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev.moneyline_model import evaluate_game


def _game(conn, pk, dt, home_abbr, away_abbr, h_pid=None, a_pid=None):
    conn.execute(
        "INSERT INTO games (game_pk, official_date, game_datetime, home_team_id, "
        "away_team_id, home_team_abbr, away_team_abbr, home_probable_pitcher_id, "
        "away_probable_pitcher_id, scraped_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (pk, "2026-06-27", dt, 147, 111, home_abbr, away_abbr, h_pid, a_pid,
         "2026-06-27T00:00:00Z"))
    for side, price in (("home", -120), ("away", 100)):
        conn.execute("INSERT INTO odds_lines (game_pk, book, market, side, price, "
                     "captured_at) VALUES (?, 'DraftKings','moneyline',?,?,?)",
                     (pk, side, price, "2026-06-27T12:00:00Z"))


def test_evaluate_game_returns_both_sides(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    now = "2026-06-27T00:00:00Z"
    conn.execute("INSERT INTO team_season_stats VALUES (147,2026,800,600,162,'mlb',?)", (now,))
    conn.execute("INSERT INTO team_season_stats VALUES (111,2026,600,800,162,'mlb',?)", (now,))
    _game(conn, 1, "2026-06-27T17:05:00Z", "NYY", "BOS")
    g = MlbRepo(conn).moneyline_slate("2026-06-27")[0]
    ev = evaluate_game(MlbRepo(conn), 2026, g)
    assert ev["home_abbr"] == "NYY" and ev["away_abbr"] == "BOS"
    assert abs((ev["model_home"] + ev["model_away"]) - 1.0) < 1e-9
    assert ev["diff"] > 0                      # strong home team underrated by even-ish line
    assert ev["game_datetime"] == "2026-06-27T17:05:00Z"
