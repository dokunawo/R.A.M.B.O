from db.migrate import get_connection, apply_migrations
from ingestion.raw_store import land_raw
from ingestion.normalize import normalize_pending
from ingestion.apify_client_wrapper import RunResult
from repositories.mlb_repo import MlbRepo


def _schedule_item(game_pk, home_abbr, away_abbr, game_dt):
    return {
        "gamePk": game_pk, "officialDate": "2026-06-27", "gameDate": game_dt,
        "season": "2026", "gameType": "R",
        "status": {"detailedState": "Scheduled"},
        "teams": {
            "home": {"team": {"id": 147, "name": "h", "abbreviation": home_abbr}},
            "away": {"team": {"id": 111, "name": "a", "abbreviation": away_abbr}},
        },
        "venue": {"id": 1, "name": "Park"},
    }


def test_game_datetime_persisted_and_slate_ordered(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    # two games, later one landed first to prove ordering is by time, not insert order
    items = [_schedule_item(2, "AAA", "BBB", "2026-06-27T23:10:00Z"),
             _schedule_item(1, "CCC", "DDD", "2026-06-27T17:05:00Z")]
    land_raw(conn, RunResult("mlb/statsapi:schedule", "r", "d", items, 2, 0.0))
    normalize_pending(conn)
    now = "2026-06-27T12:00:00Z"
    for pk in (1, 2):
        conn.execute("INSERT INTO odds_lines (game_pk, book, market, side, price, captured_at) "
                     "VALUES (?,?,'moneyline','home',-110,?)", (pk, "DraftKings", now))
        conn.execute("INSERT INTO odds_lines (game_pk, book, market, side, price, captured_at) "
                     "VALUES (?,?,'moneyline','away',-110,?)", (pk, "DraftKings", now))
    slate = MlbRepo(conn).moneyline_slate("2026-06-27")
    assert [g["game_pk"] for g in slate] == [1, 2]                 # earliest first
    assert slate[0]["game_datetime"] == "2026-06-27T17:05:00Z"
