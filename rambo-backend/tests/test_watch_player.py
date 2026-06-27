from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo


def test_player_bats_and_name(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    conn.execute("INSERT INTO players (mlb_id, full_name, bats, throws, updated_at) "
                 "VALUES (605141,'Mookie Betts','R','R','2026-06-27T00:00:00Z')")
    repo = MlbRepo(conn)
    assert repo.player_bats(605141) == "R"
    assert repo.player_name(605141) == "Mookie Betts"
    assert repo.player_bats(999) is None and repo.player_name(999) is None


import json


def _seed_hr_player(conn, now):
    conn.execute("INSERT INTO players (mlb_id, full_name, bats, throws, current_team_id, "
                 "updated_at) VALUES (1,'Byron Buxton','R','R',147,?)", (now,))
    conn.execute("INSERT INTO players (mlb_id, full_name, bats, throws, current_team_id, "
                 "updated_at) VALUES (50,'Michael Lorenzen','R','R',111,?)", (now,))
    conn.execute("INSERT INTO player_season_stats (mlb_id, season, stat_group, stats, "
                 "source, as_of_date, scraped_at) VALUES (1,2026,'hitting',?,'mlb','2026-06-27',?)",
                 (json.dumps({"season": {"homeRuns": 22, "plateAppearances": 300}}), now))
    conn.execute("INSERT INTO player_statcast VALUES (1,2026,14.0,48.0,'savant',?)", (now,))
    conn.execute("INSERT INTO games (game_pk, official_date, game_datetime, home_team_id, "
                 "away_team_id, home_team_abbr, away_team_abbr, away_probable_pitcher_id, "
                 "venue_name, scraped_at) VALUES (10,'2026-06-27','2026-06-27T18:00:00Z',"
                 "147,111,'MIN','DET',50,'Target Field',?)", (now,))
    conn.execute("INSERT INTO game_weather VALUES (10,81,'Clear','12 mph, In From RCF',?)", (now,))
    conn.execute("INSERT INTO prop_lines (game_pk, mlb_id, book, market, line, multiplier, "
                 "player_name_raw, captured_at) VALUES (10,1,'DK Pick6','HR',0.5,2.0,"
                 "'Byron Buxton','2026-06-27T12:00:00Z')")


def test_player_watch_builds_real_rows(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    now = "2026-06-27T00:00:00Z"
    _seed_hr_player(conn, now)
    from brains.ev.watch import player_watch
    out = player_watch("2026-06-27", repo=MlbRepo(conn))
    assert out["title"] == "PLAYER WATCH"
    assert out["count"] == 1
    row = out["rows"][0]
    assert row["name"] == "BYRON BUXTON" and row["bats"] == "R"
    assert row["pitcher"] == "Michael Lorenzen"
    assert row["venue"] == "Target Field" and row["temp"] == 81
    assert "Michael Lorenzen" in out["prompt"] and "PLAYER WATCH" in out["prompt"]
    assert "barrel 14" in out["prompt"]
