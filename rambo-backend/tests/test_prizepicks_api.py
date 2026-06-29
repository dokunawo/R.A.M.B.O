import os
from fastapi import FastAPI
from fastapi.testclient import TestClient
from db.migrate import get_connection, apply_migrations


def _app(db):
    os.environ["RAMBO_DB_PATH"] = db
    import importlib, api.betting as betting
    importlib.reload(betting)
    app = FastAPI(); app.include_router(betting.router)
    return TestClient(app)


def test_prizepicks_board_empty_ok(tmp_path):
    db = str(tmp_path / "t.db")
    conn = get_connection(db); apply_migrations(conn, "db/migrations"); conn.commit(); conn.close()
    client = _app(db)
    r = client.get("/betting/prizepicks", params={"market": "HR", "date": "2026-06-29"})
    assert r.status_code == 200
    assert r.json()["product"] == "PrizePicks" and r.json()["count"] == 0
