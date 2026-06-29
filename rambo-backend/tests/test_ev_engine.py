import json
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev.engine import daily_edge

def _seed(conn):
    now = "2026-06-26T00:00:00Z"
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_id, away_team_id,"
                 " home_team_abbr, away_team_abbr, scraped_at)"
                 " VALUES (999,'2026-06-26',147,111,'NYY','BOS',?)", (now,))
    for mlb_id, name, hr in [(1, "Big Bopper", 60), (2, "Weak Hitter", 5)]:
        conn.execute("INSERT INTO players (mlb_id, full_name, throws, current_team_id, updated_at)"
                     " VALUES (?,?,'R',147,?)", (mlb_id, name, now))
        stats = {"season": {"homeRuns": hr, "plateAppearances": 600}, "splits": {}}
        conn.execute("INSERT INTO player_season_stats (mlb_id, season, stat_group, stats, source,"
                     " as_of_date, scraped_at) VALUES (?,2026,'hitting',?,'mlb','2026-06-26',?)",
                     (mlb_id, json.dumps(stats), now))
        conn.execute("INSERT INTO prop_lines (game_pk, mlb_id, book, market, line, multiplier,"
                     " player_name_raw, captured_at) VALUES (999,?,'dk_pick6','HR',0.5,3.5,?,"
                     "'2026-06-26T18:00Z')", (mlb_id, name))

def test_daily_edge_ranks_and_filters(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    _seed(conn)
    picks = daily_edge("2026-06-26", "hr", repo=MlbRepo(conn),
                       complete=lambda prompt: "\n".join("reason" for _ in range(10)))
    assert [p.name for p in picks] == ["BIG BOPPER"]
    assert picks[0].edge > 0 and picks[0].rationale == "reason"

def test_unknown_market_raises(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    import pytest
    with pytest.raises(KeyError):
        daily_edge("2026-06-26", "nope", repo=MlbRepo(conn))
