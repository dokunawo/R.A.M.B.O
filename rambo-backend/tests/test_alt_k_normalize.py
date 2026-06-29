from db.migrate import get_connection, apply_migrations
from ingestion.normalize import map_props_book


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _event():
    return {
        "home_team": "Seattle Mariners", "away_team": "Houston Astros",
        "commence_time": "2026-06-30T02:10:00Z", "_captured_at": "2026-06-29T18:00:00Z",
        "bookmakers": [{
            "title": "FanDuel", "key": "fanduel",
            "markets": [{
                "key": "pitcher_strikeouts_alternate", "last_update": "2026-06-29T18:00:00Z",
                "outcomes": [
                    {"description": "Logan Gilbert", "name": "Over", "point": 7.5, "price": 120},
                    {"description": "Logan Gilbert", "name": "Under", "point": 7.5, "price": -150},
                    {"description": "Logan Gilbert", "name": "Over", "point": 8.5, "price": 175},
                    {"description": "Logan Gilbert", "name": "Under", "point": 8.5, "price": -220},
                ],
            }],
        }],
    }


def test_alt_strikeout_event_lands_one_row_per_line(tmp_path):
    conn = _conn(tmp_path)
    assert map_props_book(conn, _event(), "2026-06-29T18:00:00Z") is True
    rows = conn.execute(
        "SELECT line, over_price, under_price, book, player_name_raw "
        "FROM prop_lines WHERE market='SO_ALT' ORDER BY line").fetchall()
    assert len(rows) == 2
    assert [r["line"] for r in rows] == [7.5, 8.5]
    assert rows[0]["over_price"] == 120 and rows[0]["under_price"] == -150
    assert rows[1]["over_price"] == 175 and rows[1]["under_price"] == -220
    assert rows[0]["book"] == "FanDuel"
    assert rows[0]["player_name_raw"] == "Logan Gilbert"
