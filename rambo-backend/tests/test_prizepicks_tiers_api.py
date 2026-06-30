from fastapi.testclient import TestClient
from main import app
import brains.ev.prizepicks_tiers as pt

client = TestClient(app)


def test_prizepicks_tiers_endpoint(monkeypatch):
    monkeypatch.setattr(pt, "prizepicks_tiers",
                        lambda d, m, **k: {"title": f"PRIZEPICKS TIERS — {m}",
                                           "product": "PrizePicks", "market": m,
                                           "count": 0, "rows": [], "prompt": "x"})
    r = client.get("/betting/prizepicks-tiers?market=hr&date=2026-06-29")
    assert r.status_code == 200
    assert r.json()["market"] == "HR"
