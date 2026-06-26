import json
from db.migrate import get_connection, apply_migrations
from ingestion.raw_store import land_raw
from ingestion.normalize import normalize_pending
from ingestion.apify_client_wrapper import RunResult
from repositories.mlb_repo import MlbRepo
from brains.ev.features import build_hr_features

def test_split_keys_flow_through_ingestion(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    now = "2026-06-26T00:00:00Z"
    conn.execute("INSERT INTO players (mlb_id, full_name, throws, current_team_id, updated_at) "
                 "VALUES (10,'Bat Man','R',147,?)", (now,))
    conn.execute("INSERT INTO players (mlb_id, full_name, throws, current_team_id, updated_at) "
                 "VALUES (22,'Lefty','L',111,?)", (now,))
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
                 "home_team_abbr, away_team_abbr, home_probable_pitcher_id, away_probable_pitcher_id, "
                 "scraped_at) VALUES (5,'2026-06-26',147,111,'NYY','BOS',111,22,?)", (now,))
    stats_raw = {"stats": [
        {"type": {"displayName": "season"},
         "splits": [{"stat": {"homeRuns": 50, "plateAppearances": 600}}]},
        {"type": {"displayName": "statSplits"},
         "splits": [{"split": {"code": "vl"}, "stat": {"homeRuns": 20, "plateAppearances": 150}},
                    {"split": {"code": "vr"}, "stat": {"homeRuns": 30, "plateAppearances": 450}}]}]}
    item = {"mlb_id": 10, "season": 2026, "group": "hitting", "stats_raw": stats_raw}
    land_raw(conn, RunResult("mlb/statsapi:stats", "r", "d", [item], 1, 0.0))
    normalize_pending(conn)
    prop = {"mlb_id": 10, "player_name_raw": "Bat Man", "line": 0.5, "multiplier": 2.5}
    f = build_hr_features(MlbRepo(conn), "2026-06-26", prop)
    assert f.pitcher_hand == "L"
    assert abs(f.hr_rate - 20 / 150) < 1e-9   # vs-LHP split selected -> keys flow as vl/vr
