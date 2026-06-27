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


def test_player_watch_endpoint(monkeypatch):
    monkeypatch.setattr(betting, "player_watch", lambda *a, **k: {
        "title": "PLAYER WATCH", "product": "DK Pick6", "count": 0, "rows": [],
        "prompt": "PLAYER WATCH ..."})
    monkeypatch.setattr(betting, "_provenance", lambda *a, **k: (
        {"generated_at": "x", "data_as_of": None, "book": "b", "product": "p", "stale": False},
        None, "DraftKings"))
    app = FastAPI(); app.include_router(betting.router)
    c = TestClient(app)
    r = c.get("/betting/player-watch")
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "PLAYER WATCH"
    assert "prompt" in body and "provenance" in body


def test_moneyline_board_endpoint(monkeypatch):
    monkeypatch.setattr(betting, "moneyline_board", lambda *a, **k: {
        "title": "MONEYLINE BOARD", "product": "Moneyline (de-vig book lean)", "count": 0,
        "rows": [], "prompt": "MONEYLINE BOARD ..."})
    monkeypatch.setattr(betting, "_provenance", lambda *a, **k: (
        {"generated_at": "x", "data_as_of": None, "book": "b", "product": "p", "stale": False},
        None, "DraftKings"))
    app = FastAPI(); app.include_router(betting.router)
    c = TestClient(app)
    r = c.get("/betting/moneyline-board")
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "MONEYLINE BOARD"
    assert "prompt" in body and "provenance" in body
