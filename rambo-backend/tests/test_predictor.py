from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev.ml.predictor import AnchoredPredictor, LogRegPredictor


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _final(conn, pk, date, home_id, away_id, hs, as_):
    conn.execute(
        "INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
        "home_team_abbr, away_team_abbr, home_score, away_score, scraped_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (pk, date, home_id, away_id, "HHH", "AAA", hs, as_, "2026-06-28T00:00:00Z"))


def _history(conn):
    # alternating results so both classes appear; teams 1 (strong) vs 2 (weak)
    i = 0
    for d in ("2026-04-01", "2026-04-03", "2026-04-05", "2026-04-07", "2026-04-09"):
        _final(conn, 1000 + i, d, 1, 2, 7, 2); i += 1
        _final(conn, 1000 + i, d, 2, 1, 1, 6); i += 1


def test_logreg_predictor_refits_on_cadence(tmp_path):
    conn = _conn(tmp_path)
    _history(conn)
    repo = MlbRepo(conn)
    p = LogRegPredictor(refit_days=7)
    p.prepare(repo, 2026, "2026-04-15")
    first = p.model
    assert first is not None and p.last_fit_date == "2026-04-15"
    # within 7 days -> no refit (same model object)
    p.prepare(repo, 2026, "2026-04-18")
    assert p.model is first and p.last_fit_date == "2026-04-15"
    # >=7 days later -> refit (new model object)
    p.prepare(repo, 2026, "2026-04-25")
    assert p.model is not first and p.last_fit_date == "2026-04-25"


def test_logreg_predictor_predicts_probability(tmp_path):
    conn = _conn(tmp_path)
    _history(conn)
    repo = MlbRepo(conn)
    p = LogRegPredictor(refit_days=7)
    p.prepare(repo, 2026, "2026-04-15")
    game = {"home_team_id": 1, "away_team_id": 2,
            "home_probable_pitcher_id": None, "away_probable_pitcher_id": None}
    prob = p.predict_home(repo, 2026, game, "2026-04-15")
    assert prob is not None and 0.0 < prob < 1.0


def test_logreg_predictor_none_when_unfit(tmp_path):
    conn = _conn(tmp_path)
    repo = MlbRepo(conn)            # no history -> empty training set -> unfit
    p = LogRegPredictor()
    p.prepare(repo, 2026, "2026-04-01")
    assert p.last_fit_date is None
    game = {"home_team_id": 1, "away_team_id": 2,
            "home_probable_pitcher_id": None, "away_probable_pitcher_id": None}
    assert p.model is None
    assert p.predict_home(repo, 2026, game, "2026-04-01") is None


def test_anchored_predictor_matches_evaluate_game_asof(tmp_path):
    conn = _conn(tmp_path)
    for d in ("2026-04-01", "2026-04-05", "2026-04-10"):
        _final(conn, hash(d) % 90000, d, 1, 2, 8, 2)
    repo = MlbRepo(conn)
    from brains.ev.moneyline_model import evaluate_game_asof
    s = {"game_pk": 999, "home_team_id": 1, "away_team_id": 2,
         "home_probable_pitcher_id": None, "away_probable_pitcher_id": None,
         "home_team_abbr": "HHH", "away_team_abbr": "AAA",
         "home_price": -120, "away_price": 100}
    p = AnchoredPredictor()
    p.prepare(repo, 2026, "2026-05-01")
    got = p.predict_home(repo, 2026, s, "2026-05-01")
    ev = evaluate_game_asof(repo, 2026, s, "2026-05-01")
    assert got == ev["model_home"]
