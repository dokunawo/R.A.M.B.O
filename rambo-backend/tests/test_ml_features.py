from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev.ml import features


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _final(conn, pk, date, home_id, away_id, hs, as_, hp=None, ap=None):
    conn.execute(
        "INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
        "home_team_abbr, away_team_abbr, home_probable_pitcher_id, "
        "away_probable_pitcher_id, home_score, away_score, scraped_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (pk, date, home_id, away_id, "HHH", "AAA", hp, ap, hs, as_,
         "2026-06-28T00:00:00Z"))


def test_feature_vector_signs(tmp_path):
    conn = _conn(tmp_path)
    # team 1 strong (scores 8 allows 2), team 2 weak (scores 2 allows 8), in April
    for d in ("2026-04-01", "2026-04-05", "2026-04-10"):
        _final(conn, hash(d) % 90000, d, 1, 2, 8, 2)
    repo = MlbRepo(conn)
    game = {"home_team_id": 1, "away_team_id": 2,
            "home_probable_pitcher_id": None, "away_probable_pitcher_id": None}
    vec = features.game_feature_vector(repo, 2026, game, "2026-05-01")
    assert vec is not None
    run_diff, era_diff, pythag_diff = vec
    assert run_diff > 0           # home outscores opponents by far more
    assert era_diff == 0.0        # both pitchers unknown -> 4.20 fallback both sides
    assert pythag_diff > 0        # home has better pythag


def test_feature_vector_none_without_prior(tmp_path):
    conn = _conn(tmp_path)
    repo = MlbRepo(conn)
    game = {"home_team_id": 1, "away_team_id": 2,
            "home_probable_pitcher_id": None, "away_probable_pitcher_id": None}
    assert features.game_feature_vector(repo, 2026, game, "2026-04-01") is None


def test_training_set_leak_guard_and_labels(tmp_path):
    conn = _conn(tmp_path)
    # history so feature vectors are buildable
    for d in ("2026-04-01", "2026-04-03", "2026-04-05"):
        _final(conn, hash("h" + d) % 90000, d, 1, 2, 6, 3)
        _final(conn, hash("k" + d) % 90000 + 1, d, 2, 1, 3, 6)
    # a labeled game on 04-20 (home team 1 wins) and one on the cutoff 05-01 (excluded)
    _final(conn, 70001, "2026-04-20", 1, 2, 7, 1)
    _final(conn, 70002, "2026-05-01", 1, 2, 0, 9)
    repo = MlbRepo(conn)
    X, y = features.training_set(repo, 2026, "2026-05-01")
    # the 05-01 game is excluded (official_date < before_date is strict)
    pks = repo.training_games(2026, "2026-05-01")
    assert all(g["official_date"] < "2026-05-01" for g in pks)
    # every label is 1/0 and matches a home win/loss; the 04-20 blowout is a home win
    assert set(y) <= {0, 1}
    assert len(X) == len(y) and len(y) >= 1
