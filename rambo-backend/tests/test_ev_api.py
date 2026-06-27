from fastapi import FastAPI
from fastapi.testclient import TestClient
from brains.ev.types import Pick
import api.betting as betting

def _pick():
    return Pick(market="hr", mlb_id=1, name="BIG BOPPER", initials="BB", team="NYY",
                opponent="BOS", hand="R", pick="1+ HOME RUN — OVER", line=0.5,
                multiplier=2.5, breakeven=0.4, model_p=0.46, edge=0.15, support="60 HR",
                tags=["EDGE"], glow="gold", headshot_url="u", rationale="mash")

def _client(monkeypatch):
    monkeypatch.setattr(betting, "daily_edge", lambda date, market, threshold=0.0: [_pick()])
    app = FastAPI(); app.include_router(betting.router)
    return TestClient(app)

def test_daily_edge_endpoint(monkeypatch):
    c = _client(monkeypatch)
    r = c.get("/betting/daily-edge?market=hr&date=2026-06-26")
    assert r.status_code == 200
    body = r.json()
    assert body["market"] == "hr" and body["count"] == 1
    assert body["picks"][0]["name"] == "BIG BOPPER" and body["picks"][0]["edge"] == 0.15

def test_unknown_market_404(monkeypatch):
    c = _client(monkeypatch)
    assert c.get("/betting/daily-edge?market=nope").status_code == 404
