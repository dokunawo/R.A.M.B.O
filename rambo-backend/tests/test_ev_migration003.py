import json
from db.migrate import get_connection, apply_migrations
from ingestion.raw_store import land_raw
from ingestion.normalize import normalize_pending
from ingestion.apify_client_wrapper import RunResult

def _schedule_item():
    return {"gamePk": 999, "officialDate": "2026-06-26", "season": 2026,
            "teams": {
              "home": {"team": {"id": 147, "name": "New York Yankees", "abbreviation": "NYY"},
                       "probablePitcher": {"id": 111}},
              "away": {"team": {"id": 111, "name": "Boston Red Sox", "abbreviation": "BOS"},
                       "probablePitcher": {"id": 222}}}}

def test_games_gets_pitchers_and_abbrs(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    run = RunResult("mlb/statsapi:schedule", "r", "d", [_schedule_item()], 1, 0.0)
    land_raw(conn, run)
    normalize_pending(conn)
    g = conn.execute(
        "SELECT home_team_abbr, away_team_abbr, home_probable_pitcher_id, "
        "away_probable_pitcher_id FROM games WHERE game_pk=999").fetchone()
    assert g["home_team_abbr"] == "NYY"
    assert g["away_team_abbr"] == "BOS"
    assert g["home_probable_pitcher_id"] == 111
    assert g["away_probable_pitcher_id"] == 222
