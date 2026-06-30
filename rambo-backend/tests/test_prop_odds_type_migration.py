from db.migrate import get_connection, apply_migrations
from ingestion.normalize import _insert_prop


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def test_odds_type_column_exists_default_standard(tmp_path):
    conn = _conn(tmp_path)
    cols = {r["name"]: r for r in conn.execute("PRAGMA table_info(prop_lines)")}
    assert "odds_type" in cols
    assert cols["odds_type"]["dflt_value"].strip("'") == "standard"


def test_insert_prop_defaults_odds_type_standard(tmp_path):
    conn = _conn(tmp_path)
    _insert_prop(conn, {"game_pk": None, "mlb_id": None, "book": "prizepicks",
                        "market": "HR", "line": 0.5, "over_price": None,
                        "under_price": None, "multiplier": None,
                        "player_name_raw": "X", "captured_at": "2026-06-29T00:00Z"})
    assert conn.execute("SELECT odds_type FROM prop_lines").fetchone()["odds_type"] == "standard"


def test_insert_prop_writes_given_odds_type(tmp_path):
    conn = _conn(tmp_path)
    _insert_prop(conn, {"game_pk": None, "mlb_id": None, "book": "prizepicks",
                        "market": "HR", "line": 1.5, "over_price": None,
                        "under_price": None, "multiplier": None,
                        "player_name_raw": "Y", "captured_at": "2026-06-29T00:00Z",
                        "odds_type": "demon"})
    assert conn.execute("SELECT odds_type FROM prop_lines WHERE player_name_raw='Y'"
                        ).fetchone()["odds_type"] == "demon"


def test_migration_idempotent(tmp_path):
    conn = _conn(tmp_path)
    applied = apply_migrations(conn, "db/migrations")   # second run
    assert "009_prop_odds_type.sql" not in applied      # already applied first time
