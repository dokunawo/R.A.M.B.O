import math
from db.migrate import get_connection, apply_migrations
from ingestion.raw_store import land_raw
from ingestion.normalize import normalize_pending
from ingestion.apify_client_wrapper import RunResult
from repositories.mlb_repo import MlbRepo
import json
from brains.ev.moneyline_model import (pythag_winpct, matchup_winprob,
                                       american_to_implied, devig_two_way,
                                       expected_runs, winprob_from_runs,
                                       market_anchored_prob)
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


def test_expected_runs_and_winprob():
    assert math.isclose(expected_runs(4.5, 4.20), 4.5, rel_tol=1e-9)   # avg starter, no change
    assert expected_runs(4.5, 2.10) < 2.5                              # ace ~halves output
    assert math.isclose(winprob_from_runs(4.5, 4.5), 0.5, rel_tol=1e-9)
    assert winprob_from_runs(5.0, 3.0) > 0.5


def _seed_pitcher(conn, mlb_id, era, now):
    conn.execute("INSERT INTO players (mlb_id, full_name, throws, current_team_id, updated_at) "
                 "VALUES (?,?,'R',147,?)", (mlb_id, f"SP{mlb_id}", now))
    conn.execute("INSERT INTO player_season_stats (mlb_id, season, stat_group, stats, source, "
                 "as_of_date, scraped_at) VALUES (?,2026,'pitching',?,'mlb','2026-06-26',?)",
                 (mlb_id, json.dumps({"season": {"era": era}}), now))


def test_moneyline_pitcher_adjusted_flips_favorite(tmp_path):
    """A strong home team (Pythag favorite) facing an ace while starting a bad arm
    should be modeled an underdog — proof the starter dominates the season Pythag."""
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    now = "2026-06-26T00:00:00Z"
    conn.execute("INSERT INTO team_season_stats VALUES (147,2026,800,600,162,'mlb',?)", (now,))
    conn.execute("INSERT INTO team_season_stats VALUES (111,2026,600,800,162,'mlb',?)", (now,))
    _seed_pitcher(conn, 10, "5.50", now)   # home starts a bad arm
    _seed_pitcher(conn, 20, "2.00", now)   # away starts an ace
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
                 "home_team_abbr, away_team_abbr, home_probable_pitcher_id, "
                 "away_probable_pitcher_id, scraped_at) "
                 "VALUES (999,'2026-06-26',147,111,'NYY','BOS',10,20,?)", (now,))
    conn.execute("INSERT INTO odds_lines (game_pk, book, market, side, price, captured_at) "
                 "VALUES (999,'DK','moneyline','home',-110,'2026-06-26T18:00Z')")
    conn.execute("INSERT INTO odds_lines (game_pk, book, market, side, price, captured_at) "
                 "VALUES (999,'DK','moneyline','away',-110,'2026-06-26T18:00Z')")
    pk = MoneylineMarket().raw_picks(MlbRepo(conn), "2026-06-26")[0]
    assert pk.team == "BOS"                 # the ace flips the value to the away team
    assert "ERA SP" in pk.support           # pitcher-adjusted path used (not Pythag fallback)
    assert pk.tags == ["LEAN"] and abs(pk.edge) < 0.12   # market-anchored -> bounded lean


def test_moneyline_slate_excludes_live_odds(tmp_path):
    """In-game 'Live Odds' rows (extreme/suspended) must never override the pregame
    line, even though they're captured later."""
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
                 "home_team_abbr, away_team_abbr, scraped_at) "
                 "VALUES (999,'2026-06-26',111,147,'BOS','NYY','2026-06-26T00:00:00Z')")
    pre = "2026-06-26T18:00Z"
    live = "2026-06-26T21:00Z"   # later — would win a naive 'latest' pick
    for side, price, book, ts in [
        ("home", -120, "DraftKings", pre), ("away", 100, "DraftKings", pre),
        ("home", -730, "DraftKings - Live Odds", live), ("away", 440, "DraftKings - Live Odds", live),
    ]:
        conn.execute("INSERT INTO odds_lines (game_pk, book, market, side, price, captured_at) "
                     "VALUES (999,?,'moneyline',?,?,?)", (book, side, price, ts))
    slate = MlbRepo(conn).moneyline_slate("2026-06-26")
    assert len(slate) == 1
    assert slate[0]["home_price"] == -120 and slate[0]["away_price"] == 100   # pregame, not live


def test_market_anchored_prob_bounds():
    # an absurd model prob is clamped + pulled toward the book -> small, sane lean
    anchored = market_anchored_prob(0.91, 0.62)
    assert 0.62 < anchored < 0.70           # near the book, never near 0.91
    assert math.isclose(market_anchored_prob(0.50, 0.50), 0.50, rel_tol=1e-9)  # agree -> no lean


def test_registry_has_moneyline():
    assert REGISTRY["ml"].market_key == "ml"
