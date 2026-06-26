import json, math
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev.features import build_hr_features

def _seed(conn):
    now = "2026-06-26T00:00:00Z"
    conn.execute("INSERT INTO players (mlb_id, full_name, throws, current_team_id, updated_at) "
                 "VALUES (592450,'Aaron Judge','R',147,?)", (now,))
    conn.execute("INSERT INTO players (mlb_id, full_name, throws, current_team_id, updated_at) "
                 "VALUES (222,'Lefty','L',111,?)", (now,))
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
                 "home_team_abbr, away_team_abbr, home_probable_pitcher_id, away_probable_pitcher_id, "
                 "scraped_at) VALUES (999,'2026-06-26',147,111,'NYY','BOS',111,222,?)", (now,))
    stats = {"season": {"homeRuns": 50, "plateAppearances": 600},
             "splits": {"vr": {"homeRuns": 30, "plateAppearances": 450},
                        "vl": {"homeRuns": 20, "plateAppearances": 150}}}
    conn.execute("INSERT INTO player_season_stats (mlb_id, season, stat_group, stats, source, "
                 "as_of_date, scraped_at) VALUES (592450,2026,'hitting',?,'mlb','2026-06-26',?)",
                 (json.dumps(stats), now))

def test_features_use_vs_lefty_split_and_park(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    _seed(conn)
    prop = {"mlb_id": 592450, "player_name_raw": "Aaron Judge", "line": 0.5, "multiplier": 2.5}
    f = build_hr_features(MlbRepo(conn), "2026-06-26", prop)
    assert f is not None
    assert f.pitcher_hand == "L"                       # away probable pitcher throws L
    assert math.isclose(f.hr_rate, 20/150, rel_tol=1e-9)   # vs-LHP split
    assert f.park_factor == 1.10                       # NYY home park
    assert f.opponent_abbr == "BOS" and f.season_hr == 50

def test_features_none_without_stats(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    prop = {"mlb_id": 1, "player_name_raw": "Nobody", "line": 0.5, "multiplier": 2.0}
    assert build_hr_features(MlbRepo(conn), "2026-06-26", prop) is None
