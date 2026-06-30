from db.migrate import get_connection, apply_migrations
from ingestion.normalize import map_prizepicks


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _item(stat="Home Runs", odds="standard", line=0.5, name="Aaron Judge"):
    return {"projection_id": "p1", "player_name": name, "team": "NYY",
            "position": "OF", "stat_type": stat, "line": line, "odds_type": odds,
            "start_time": "2026-06-29T19:00:00-04:00", "game_id": "g9"}


def test_mapped_standard_prop_lands(tmp_path):
    conn = _conn(tmp_path)
    assert map_prizepicks(conn, _item(), "2026-06-29T18:00:00Z") is True
    row = conn.execute("SELECT book, market, line, multiplier, player_name_raw "
                       "FROM prop_lines").fetchone()
    assert row["book"] == "prizepicks" and row["market"] == "HR"
    assert row["line"] == 0.5 and row["multiplier"] is None
    assert row["player_name_raw"] == "Aaron Judge"


def test_unmapped_stat_skipped_all_tiers(tmp_path):
    conn = _conn(tmp_path)
    map_prizepicks(conn, _item(stat="Pitches Thrown"), "2026-06-29T18:00:00Z")
    map_prizepicks(conn, _item(stat="Pitches Thrown", odds="demon"), "2026-06-29T18:00:00Z")
    assert conn.execute("SELECT COUNT(*) FROM prop_lines").fetchone()[0] == 0
