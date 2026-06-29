"""Strikeout Watch — rank probable starters by P(8+/9+/10+ K)."""
import asyncio
import json
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo


def _seed_pitcher(conn, mid, name, team_id, k, gs, now):
    conn.execute("INSERT INTO players (mlb_id, full_name, throws, current_team_id, updated_at) "
                 "VALUES (?,?,'R',?,?)", (mid, name, team_id, now))
    conn.execute("INSERT INTO player_season_stats (mlb_id, season, stat_group, stats, source, "
                 "as_of_date, scraped_at) VALUES (?,2026,'pitching',?,'mlb','2026-06-28',?)",
                 (mid, json.dumps({"season": {"strikeOuts": k, "gamesStarted": gs}}), now))
    # Also seed game_logs for k_projection to work (batters_faced = k / (k/bf))
    # Use average BF across starts: for simplicity, assume ~25 BF per start
    bf_per_start = 25
    total_bf = bf_per_start * gs
    k_per_start = k / gs if gs > 0 else 0
    for g in range(gs):
        stat = json.dumps({"stat": {"strikeOuts": int(k_per_start), "battersFaced": bf_per_start}})
        game_date = f"2026-06-{(1 + g * 7):02d}"  # spread games out by week
        game_pk = 5000 + mid * 100 + g
        # Create dummy game for FK constraint
        conn.execute("INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, scraped_at) "
                     "VALUES (?,?,1,2,?)", (game_pk, game_date, now))
        conn.execute("INSERT INTO player_game_logs (mlb_id, game_pk, game_date, stat_group, stats, source, scraped_at) "
                     "VALUES (?,?,?,?,?,?,?)", (mid, game_pk, game_date, "pitching", stat, "mlb", now))


def test_strikeout_watch_ranks_by_k_rate(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    now = "2026-06-28T00:00:00Z"
    # game: SEA(147) vs CLE(111); ace (11 K/start) on away, mid arm (7 K/start) on home
    _seed_pitcher(conn, 10, "Mid Arm", 147, k=140, gs=20, now=now)     # 7.0 K/start
    _seed_pitcher(conn, 20, "Ace Pitcher", 111, k=220, gs=20, now=now)  # 11.0 K/start
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
                 "home_team_abbr, away_team_abbr, home_probable_pitcher_id, "
                 "away_probable_pitcher_id, scraped_at) "
                 "VALUES (1,'2026-06-28',147,111,'SEA','CLE',10,20,?)", (now,))

    from brains.ev.watch import strikeout_watch
    out = (strikeout_watch("2026-06-28", repo=MlbRepo(conn)))
    assert out["title"] == "STRIKEOUT WATCH" and out["count"] == 2
    rows = out["rows"]
    assert rows[0]["name"] == "ACE PITCHER"            # higher K rate ranks first
    assert rows[0]["k_mean"] == 11.0 and rows[1]["k_mean"] == 7.0
    # probabilities are monotonic: P(8+) >= P(9+) >= P(10+)
    r = rows[0]
    assert r["p8"] >= r["p9"] >= r["p10"]
    assert r["p9"] > rows[1]["p9"]                     # ace beats the mid arm at 9+
    assert "STRIKEOUT WATCH" in out["prompt"] and "ACE PITCHER" in out["prompt"]


def test_strikeout_watch_empty_when_no_starters(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    from brains.ev.watch import strikeout_watch
    out = (strikeout_watch("2026-06-28", repo=MlbRepo(conn)))
    assert out["count"] == 0 and "no probable starters" in out["prompt"]


def test_strikeout_watch_rows_carry_full_ladder(tmp_path):
    import json
    from db.migrate import get_connection, apply_migrations
    from repositories.mlb_repo import MlbRepo
    from brains.ev.watch import strikeout_watch
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    now = "2026-06-28T00:00:00Z"
    # a probable starter with enough starts + a K/BF history
    conn.execute("INSERT INTO players (mlb_id, full_name, current_team_id, updated_at) VALUES (50,'ACE',1,?)", (now,))
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
                 "home_team_abbr, away_team_abbr, home_probable_pitcher_id, scraped_at) "
                 "VALUES (900,'2026-06-29',1,2,'AAA','BBB',50,?)", (now,))
    season = json.dumps({"season": {"gamesStarted": 12}})
    conn.execute("INSERT INTO player_season_stats (mlb_id, season, stat_group, stats, "
                 "source, as_of_date, scraped_at) VALUES (50,2026,'pitching',?,?,?,?)",
                 (season, "mlb/statsapi:stats", "2026-06-28", now))
    for i, d in enumerate(("2026-06-01", "2026-06-08", "2026-06-15", "2026-06-22")):
        # Create a dummy game for each log entry (FK constraint)
        game_id = 901 + i
        conn.execute("INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
                     "home_team_abbr, away_team_abbr, scraped_at) "
                     "VALUES (?,?,1,2,'AAA','BBB',?)", (game_id, d, now))
        st = json.dumps({"stat": {"strikeOuts": 8, "battersFaced": 25}})
        conn.execute("INSERT INTO player_game_logs (mlb_id, game_pk, game_date, "
                     "stat_group, stats, source, scraped_at) VALUES (50,?,?,?,?,?,?)",
                     (game_id, d, "pitching", st, "mlb/statsapi:stats", now))
    board = strikeout_watch("2026-06-29", repo=MlbRepo(conn))
    assert board["count"] >= 1
    row = board["rows"][0]
    for j in range(1, 11):
        assert f"p{j}" in row and 0 <= row[f"p{j}"] <= 100
    assert "k_rate" in row and "batters_faced" in row
    # ladder is monotone non-increasing across thresholds
    probs = [row[f"p{j}"] for j in range(1, 11)]
    assert all(probs[i] >= probs[i + 1] for i in range(len(probs) - 1))
