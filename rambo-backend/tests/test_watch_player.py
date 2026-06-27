from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo


def test_player_bats_and_name(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    conn.execute("INSERT INTO players (mlb_id, full_name, bats, throws, updated_at) "
                 "VALUES (605141,'Mookie Betts','R','R','2026-06-27T00:00:00Z')")
    repo = MlbRepo(conn)
    assert repo.player_bats(605141) == "R"
    assert repo.player_name(605141) == "Mookie Betts"
    assert repo.player_bats(999) is None and repo.player_name(999) is None
