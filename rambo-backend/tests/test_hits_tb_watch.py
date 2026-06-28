"""Hits & Total Bases Watch — rank hitters by P(2+ TB) (+ P(1+ hit))."""
import json
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo


def _seed_hitter(conn, mid, name, team_id, hits, tb, games, now):
    conn.execute("INSERT INTO players (mlb_id, full_name, bats, throws, current_team_id, "
                 "updated_at) VALUES (?,?,'R','R',?,?)", (mid, name, team_id, now))
    conn.execute("INSERT INTO player_season_stats (mlb_id, season, stat_group, stats, source, "
                 "as_of_date, scraped_at) VALUES (?,2026,'hitting',?,'mlb','2026-06-28',?)",
                 (mid, json.dumps({"season": {"hits": hits, "totalBases": tb,
                                              "gamesPlayed": games}}), now))
    conn.execute("INSERT INTO game_lineups (game_pk, team_id, mlb_id, batting_order, side, "
                 "scraped_at) VALUES (1,?,?,100,'home',?)", (team_id, mid, now))


def test_hits_tb_watch_ranks_by_total_bases(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    now = "2026-06-28T00:00:00Z"
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
                 "home_team_abbr, away_team_abbr, scraped_at) "
                 "VALUES (1,'2026-06-28',147,111,'SEA','CLE',?)", (now,))
    # slugger: lots of total bases; contact guy: hits but fewer TB
    _seed_hitter(conn, 1, "Slugger", 147, hits=90, tb=200, games=80, now=now)   # 2.5 TB/gm
    _seed_hitter(conn, 2, "Contact Guy", 147, hits=110, tb=140, games=80, now=now)  # 1.75 TB/gm

    from brains.ev.watch import hits_tb_watch
    out = hits_tb_watch("2026-06-28", repo=MlbRepo(conn))
    assert out["title"] == "HITS & TOTAL BASES" and out["count"] == 2
    rows = out["rows"]
    assert rows[0]["name"] == "SLUGGER"                 # higher TB rate ranks first
    assert rows[0]["p_tb2"] > rows[1]["p_tb2"]
    assert 0 < rows[0]["p_hit"] <= 100
    assert "HITS & TOTAL BASES" in out["prompt"] and "SLUGGER" in out["prompt"]


def test_hits_tb_watch_empty_without_lineups(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    from brains.ev.watch import hits_tb_watch
    out = hits_tb_watch("2026-06-28", repo=MlbRepo(conn))
    assert out["count"] == 0 and "no lineups" in out["prompt"]
