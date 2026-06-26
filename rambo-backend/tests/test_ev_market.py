import json
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev.market import HRMarket, REGISTRY

def _seed(conn):
    now = "2026-06-26T00:00:00Z"
    conn.execute("INSERT INTO players (mlb_id, full_name, throws, current_team_id, updated_at) "
                 "VALUES (592450,'Aaron Judge','R',147,?)", (now,))
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
                 "home_team_abbr, away_team_abbr, scraped_at) "
                 "VALUES (999,'2026-06-26',147,111,'NYY','BOS',?)", (now,))
    stats = {"season": {"homeRuns": 50, "plateAppearances": 600}, "splits": {}}
    conn.execute("INSERT INTO player_season_stats (mlb_id, season, stat_group, stats, source, "
                 "as_of_date, scraped_at) VALUES (592450,2026,'hitting',?,'mlb','2026-06-26',?)",
                 (json.dumps(stats), now))
    conn.execute("INSERT INTO prop_lines (game_pk, mlb_id, book, market, line, multiplier, "
                 "player_name_raw, captured_at) VALUES (NULL,592450,'dk_pick6','HR',0.5,2.5,"
                 "'Aaron Judge','2026-06-26T18:00Z')")

def test_hrmarket_builds_pick(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    _seed(conn)
    picks = HRMarket().raw_picks(MlbRepo(conn), "2026-06-26")
    assert len(picks) == 1
    pk = picks[0]
    assert pk.market == "hr" and pk.mlb_id == 592450
    assert pk.initials == "AJ" and pk.name == "AARON JUDGE"
    assert pk.pick == "1+ HOME RUN — OVER" and pk.multiplier == 2.5
    assert pk.support == "50 HR" and pk.tags == ["EDGE"]
    assert "/people/592450/headshot/" in pk.headshot_url
    assert 0.20 < pk.model_p < 0.40
    assert abs(pk.edge - (pk.model_p * 2.5 - 1)) < 1e-9

def test_registry_has_hr():
    assert "hr" in REGISTRY and REGISTRY["hr"].market_key == "hr"

def test_null_multiplier_prop_skipped(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    now = "2026-06-26T00:00:00Z"
    conn.execute("INSERT INTO players (mlb_id, full_name, throws, current_team_id, updated_at) "
                 "VALUES (592450,'Aaron Judge','R',147,?)", (now,))
    stats = {"season": {"homeRuns": 50, "plateAppearances": 600}, "splits": {}}
    conn.execute("INSERT INTO player_season_stats (mlb_id, season, stat_group, stats, source, "
                 "as_of_date, scraped_at) VALUES (592450,2026,'hitting',?,'mlb','2026-06-26',?)",
                 (json.dumps(stats), now))
    # HR prop with NULL multiplier (e.g. a non-Pick6 book) must be skipped, not crash
    conn.execute("INSERT INTO prop_lines (game_pk, mlb_id, book, market, line, multiplier, "
                 "player_name_raw, captured_at) VALUES (NULL,592450,'somebook','HR',0.5,NULL,"
                 "'Aaron Judge','2026-06-26T18:00Z')")
    assert HRMarket().raw_picks(MlbRepo(conn), "2026-06-26") == []
