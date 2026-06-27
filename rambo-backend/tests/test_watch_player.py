import json
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


def test_player_watch_omits_absent_weather_statcast_pitcher(tmp_path):
    """Honesty rule: no faked/None values when weather, statcast, and pitcher are absent."""
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    now = "2026-06-27T00:00:00Z"
    # Use distinct mlb_id / game_pk to avoid any cross-test collision
    conn.execute("INSERT INTO players (mlb_id, full_name, bats, throws, current_team_id, "
                 "updated_at) VALUES (2,'Jose Ramirez','S','R',114,?)", (now,))
    conn.execute("INSERT INTO player_season_stats (mlb_id, season, stat_group, stats, "
                 "source, as_of_date, scraped_at) VALUES (2,2026,'hitting',?,'mlb','2026-06-27',?)",
                 (json.dumps({"season": {"homeRuns": 18, "plateAppearances": 280}}), now))
    # Deliberately omit player_statcast row for mlb_id=2
    conn.execute("INSERT INTO games (game_pk, official_date, game_datetime, home_team_id, "
                 "away_team_id, home_team_abbr, away_team_abbr, "
                 "venue_name, scraped_at) VALUES (20,'2026-06-27','2026-06-27T19:00:00Z',"
                 "114,142,'CLE','KC','Progressive Field',?)", (now,))
    # Deliberately omit game_weather row for game_pk=20
    # away_probable_pitcher_id left NULL (not inserted)
    conn.execute("INSERT INTO prop_lines (game_pk, mlb_id, book, market, line, multiplier, "
                 "player_name_raw, captured_at) VALUES (20,2,'DK Pick6','HR',0.5,2.0,"
                 "'Jose Ramirez','2026-06-27T12:00:00Z')")
    from brains.ev.watch import player_watch, _pw_line
    out = player_watch("2026-06-27", repo=MlbRepo(conn))
    assert out["count"] == 1
    row = out["rows"][0]
    # Absent data must be None/empty — not faked values
    assert row["temp"] is None
    assert row["barrel"] is None
    assert row["hard_hit"] is None
    assert row["pitcher"] == ""
    # Prompt must not contain the string "None"
    assert "None" not in out["prompt"]
    # Prompt must contain the player name and the HR segment
    assert "JOSE RAMIREZ" in out["prompt"]
    assert "HR " in out["prompt"]
    # The formatted line must also be free of "None"
    line = _pw_line(row)
    assert "None" not in line


def test_player_watch_pins_leans_then_fills_pool(tmp_path):
    """Propped HR plays (our leans) are pinned first even if a pool hitter has a
    higher HR%; the rest of the board fills from confirmed-lineup hitters by HR%."""
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    now = "2026-06-27T00:00:00Z"
    conn.execute("INSERT INTO games (game_pk, official_date, game_datetime, home_team_id, "
                 "away_team_id, home_team_abbr, away_team_abbr, venue_name, scraped_at) "
                 "VALUES (20,'2026-06-27','2026-06-27T18:00:00Z',147,111,'MIN','DET','Target Field',?)",
                 (now,))

    def hitter(mid, name, team_id, hr, pa, prop=False):
        conn.execute("INSERT INTO players (mlb_id, full_name, bats, throws, current_team_id, "
                     "updated_at) VALUES (?,?,'R','R',?,?)", (mid, name, team_id, now))
        conn.execute("INSERT INTO player_season_stats (mlb_id, season, stat_group, stats, source, "
                     "as_of_date, scraped_at) VALUES (?,2026,'hitting',?,'mlb','2026-06-27',?)",
                     (mid, json.dumps({"season": {"homeRuns": hr, "plateAppearances": pa}}), now))
        conn.execute("INSERT INTO game_lineups (game_pk, team_id, mlb_id, batting_order, side, "
                     "scraped_at) VALUES (20,?,?,100,'home',?)", (team_id, mid, now))
        if prop:
            conn.execute("INSERT INTO prop_lines (game_pk, mlb_id, book, market, line, multiplier, "
                         "player_name_raw, captured_at) VALUES (20,?,'DK Pick6','HR',0.5,2.0,?,?)",
                         (mid, name, "2026-06-27T12:00:00Z"))

    hitter(1, "Lean Guy", 147, hr=20, pa=400, prop=True)     # our lean (modest rate)
    hitter(2, "Big Bopper", 147, hr=40, pa=300)              # pool, highest HR%
    hitter(3, "Small Bat", 111, hr=5, pa=400)                # pool, lowest HR%

    from brains.ev.watch import player_watch
    out = player_watch("2026-06-27", repo=MlbRepo(conn))
    names = [r["name"] for r in out["rows"]]
    assert names == ["LEAN GUY", "BIG BOPPER", "SMALL BAT"]   # lean pinned, pool by HR%
    assert out["rows"][0]["is_lean"] is True
    assert out["rows"][1]["is_lean"] is False and out["rows"][2]["is_lean"] is False
    assert "[CMC LEAN]" in out["prompt"]
