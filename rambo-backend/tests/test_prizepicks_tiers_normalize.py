from db.migrate import get_connection, apply_migrations
from ingestion.normalize import map_prizepicks


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _item(odds, line, name="Aaron Judge", stat="Home Runs"):
    return {"projection_id": f"p-{odds}-{line}", "player_name": name, "team": "NYY",
            "position": "OF", "stat_type": stat, "line": line, "odds_type": odds,
            "start_time": "2026-06-29T19:00:00-04:00", "game_id": "g9"}


def test_all_three_tiers_land(tmp_path):
    conn = _conn(tmp_path)
    for odds, line in (("goblin", 0.5), ("standard", 0.5), ("demon", 1.5)):
        assert map_prizepicks(conn, _item(odds, line), "2026-06-29T18:00:00Z") is True
    rows = conn.execute("SELECT odds_type, line, market FROM prop_lines "
                        "ORDER BY odds_type").fetchall()
    tiers = {r["odds_type"] for r in rows}
    assert tiers == {"goblin", "standard", "demon"}
    assert all(r["market"] == "HR" for r in rows)


def test_unmapped_stat_still_skipped_all_tiers(tmp_path):
    conn = _conn(tmp_path)
    map_prizepicks(conn, _item("demon", 100.5, stat="Pitches Thrown"), "2026-06-29T18:00:00Z")
    assert conn.execute("SELECT COUNT(*) c FROM prop_lines").fetchone()["c"] == 0
