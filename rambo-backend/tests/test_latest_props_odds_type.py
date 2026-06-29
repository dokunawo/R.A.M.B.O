from db.migrate import get_connection, apply_migrations
from ingestion.normalize import _insert_prop
from repositories.mlb_repo import MlbRepo


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _seed_game_and_player(conn):
    conn.execute("INSERT INTO games (game_pk, official_date, scraped_at) "
                 "VALUES (1, '2026-06-29', '2026-06-29T00:00:00Z')")
    conn.execute("INSERT INTO players (mlb_id, full_name, updated_at) "
                 "VALUES (100, 'Aaron Judge', '2026-06-29T00:00:00Z')")


def _seed_tier(conn, odds, line):
    _insert_prop(conn, {"game_pk": 1, "mlb_id": 100, "book": "prizepicks",
                        "market": "HR", "line": line, "over_price": None,
                        "under_price": None, "multiplier": None,
                        "player_name_raw": "Aaron Judge",
                        "captured_at": "2026-06-29T18:00:00Z", "odds_type": odds})


def test_default_returns_standard_only(tmp_path):
    conn = _conn(tmp_path); _seed_game_and_player(conn)
    for odds, line in (("goblin", 0.5), ("standard", 0.5), ("demon", 1.5)):
        _seed_tier(conn, odds, line)
    repo = MlbRepo(conn)
    rows = repo.latest_props(market="HR", official_date="2026-06-29")
    assert len(rows) == 1 and rows[0]["odds_type"] == "standard"


def test_none_returns_all_tiers(tmp_path):
    conn = _conn(tmp_path); _seed_game_and_player(conn)
    for odds, line in (("goblin", 0.5), ("standard", 0.5), ("demon", 1.5)):
        _seed_tier(conn, odds, line)
    repo = MlbRepo(conn)
    rows = repo.latest_props(market="HR", official_date="2026-06-29", odds_type=None)
    assert {r["odds_type"] for r in rows} == {"goblin", "standard", "demon"}
