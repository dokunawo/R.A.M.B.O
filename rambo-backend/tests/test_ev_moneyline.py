import math
from db.migrate import get_connection, apply_migrations
from ingestion.raw_store import land_raw
from ingestion.normalize import normalize_pending
from ingestion.apify_client_wrapper import RunResult
from repositories.mlb_repo import MlbRepo
from brains.ev.moneyline_model import (pythag_winpct, matchup_winprob,
                                       american_to_implied, devig_two_way)
from brains.ev.market import MoneylineMarket, REGISTRY


def test_model_math():
    assert pythag_winpct(800, 600) > 0.5 and pythag_winpct(600, 800) < 0.5
    assert math.isclose(pythag_winpct(700, 700), 0.5, rel_tol=1e-9)
    # even teams -> 50/50 matchup
    assert math.isclose(matchup_winprob(0.5, 0.5), 0.5, rel_tol=1e-9)
    assert math.isclose(american_to_implied(-200), 200 / 300, rel_tol=1e-9)
    h, a = devig_two_way(-200, 170)
    assert math.isclose(h + a, 1.0, rel_tol=1e-9) and h > a


def test_team_stats_ingestion(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    item = {"team_id": 147, "season": 2026, "runs_scored": 800, "runs_allowed": 600,
            "games_played": 162}
    land_raw(conn, RunResult("mlb/statsapi:teams", "r", "d", [item], 1, 0.0))
    normalize_pending(conn)
    row = MlbRepo(conn).team_runs(147, 2026)
    assert row["runs_scored"] == 800 and row["runs_allowed"] == 600


def test_moneyline_market_picks_value_side(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    now = "2026-06-26T00:00:00Z"
    # strong home team, weak away team
    conn.execute("INSERT INTO team_season_stats VALUES (147,2026,800,600,162,'mlb',?)", (now,))
    conn.execute("INSERT INTO team_season_stats VALUES (111,2026,600,800,162,'mlb',?)", (now,))
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
                 "home_team_abbr, away_team_abbr, scraped_at) "
                 "VALUES (999,'2026-06-26',147,111,'NYY','BOS',?)", (now,))
    # book line near even (home -120) underrates the strong home team -> +EV home
    conn.execute("INSERT INTO odds_lines (game_pk, book, market, side, price, captured_at) "
                 "VALUES (999,'DK','moneyline','home',-120,'2026-06-26T18:00Z')")
    conn.execute("INSERT INTO odds_lines (game_pk, book, market, side, price, captured_at) "
                 "VALUES (999,'DK','moneyline','away',100,'2026-06-26T18:00Z')")
    picks = MoneylineMarket().raw_picks(MlbRepo(conn), "2026-06-26")
    assert len(picks) == 1
    pk = picks[0]
    assert pk.market == "ml" and pk.team == "NYY"          # value is on the strong home team
    assert pk.edge > 0 and pk.model_p > pk.breakeven
    assert "team-logos/147" in pk.headshot_url
    assert pk.pick.startswith("MONEYLINE")


def test_registry_has_moneyline():
    assert REGISTRY["ml"].market_key == "ml"
