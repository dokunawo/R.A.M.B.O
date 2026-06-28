import json
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev.moneyline_model import evaluate_game_asof


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _final(conn, pk, date, home_id, away_id, hs, as_):
    conn.execute(
        "INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
        "home_team_abbr, away_team_abbr, home_score, away_score, scraped_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (pk, date, home_id, away_id, "NYY", "BOS", hs, as_, "2026-06-28T00:00:00Z"))


def test_evaluate_game_asof_uses_prior_only(tmp_path):
    conn = _conn(tmp_path)
    # strong home team (147): wins big in May; weak away team (111)
    for d in ("2026-05-01", "2026-05-05", "2026-05-10"):
        _final(conn, hash(d) % 100000, d, 147, 111, 8, 2)
    repo = MlbRepo(conn)
    g = {"game_pk": 999, "home_team_id": 147, "away_team_id": 111,
         "home_probable_pitcher_id": None, "away_probable_pitcher_id": None,
         "home_team_abbr": "NYY", "away_team_abbr": "BOS",
         "home_price": -120, "away_price": 100}
    out = evaluate_game_asof(repo, 2026, g, "2026-06-01")
    assert out is not None
    assert out["model_home"] > 0.5            # model leans the strong home team
    assert abs(out["model_home"] + out["model_away"] - 1.0) < 1e-9
    assert out["diff"] == out["model_home"] - out["book_home"]


def test_evaluate_game_asof_none_without_prior(tmp_path):
    conn = _conn(tmp_path)
    repo = MlbRepo(conn)
    g = {"game_pk": 1, "home_team_id": 147, "away_team_id": 111,
         "home_probable_pitcher_id": None, "away_probable_pitcher_id": None,
         "home_team_abbr": "NYY", "away_team_abbr": "BOS",
         "home_price": -110, "away_price": -110}
    assert evaluate_game_asof(repo, 2026, g, "2026-04-01") is None
