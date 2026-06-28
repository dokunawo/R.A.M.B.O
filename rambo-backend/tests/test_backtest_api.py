import os
from fastapi.testclient import TestClient
from db.migrate import get_connection, apply_migrations


def _seed(path):
    conn = get_connection(path)
    apply_migrations(conn, "db/migrations")
    conn.commit()
    conn.close()


def test_backtest_endpoint_empty_range_ok(tmp_path, monkeypatch):
    db = str(tmp_path / "t.db")
    _seed(db)
    monkeypatch.setenv("RAMBO_DB_PATH", db)
    # import after env is set so the module reads the test DB path
    import importlib
    import api.betting as betting
    importlib.reload(betting)
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(betting.router)
    client = TestClient(app)
    r = client.get("/betting/backtest", params={"start": "2026-05-01", "end": "2026-05-02"})
    assert r.status_code == 200
    body = r.json()
    assert body["n"] == 0
    assert "early" in body and "close" in body
