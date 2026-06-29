# rambo-backend/tests/test_alt_k_api.py
from fastapi.testclient import TestClient
from main import app
from brains.ev import alt_k

client = TestClient(app)


def _fake_board(date, **kw):
    return {"title": "ALT-K BOARD", "product": "Strikeout model (alt-K)",
            "count": 1, "rows": [
                {"rank": 1, "name": "ACE ONE", "team": "SEA", "opponent": "HOU",
                 "k_rate": 0.3, "batters_faced": 24.0, "k_mean": 7.2,
                 "thresholds": [{"threshold": 8, "model_p": 0.55,
                                 "fanduel": {"price": 120, "ev": 0.21},
                                 "best": {"book": "DK", "price": 150, "ev": 0.375}}]}],
            "prompt": "ALT-K BOARD ..."}


def test_alt_k_board_endpoint(monkeypatch):
    monkeypatch.setattr(alt_k, "alt_k_board", _fake_board)
    r = client.get("/betting/alt-k-board?date=2026-06-29")
    assert r.status_code == 200
    assert r.json()["title"] == "ALT-K BOARD"


def test_alt_k_parlay_auto(monkeypatch):
    monkeypatch.setattr(alt_k, "alt_k_board", _fake_board)
    monkeypatch.setattr(alt_k, "suggest_parlays",
                        lambda board, **kw: [{"size": 1, "legs": ["ACE ONE 8+"],
                                              "combined_p": 0.55, "payout": 2.5, "ev": 0.375}])
    r = client.post("/betting/alt-k/parlay?date=2026-06-29&book=best")
    assert r.status_code == 200
    body = r.json()
    assert body["book"] == "best"
    assert body["suggestions"][0]["ev"] == 0.375


def test_alt_k_parlay_empty_sizes(monkeypatch):
    """?sizes= (empty string) must not raise a 500 — falls back to default sizes."""
    monkeypatch.setattr(alt_k, "alt_k_board", _fake_board)
    monkeypatch.setattr(alt_k, "suggest_parlays", lambda board, **kw: [])
    r = client.post("/betting/alt-k/parlay?date=2026-06-29&sizes=")
    assert r.status_code == 200


def test_alt_k_parlay_manual(monkeypatch):
    monkeypatch.setattr(alt_k, "alt_k_board", _fake_board)
    monkeypatch.setattr(alt_k, "manual_parlay",
                        lambda board, picks, **kw: {"legs": [], "missing": [],
                                                    "combined_p": 0.55, "payout": 2.5, "ev": 0.375})
    r = client.post("/betting/alt-k/parlay?date=2026-06-29",
                    json={"legs": [{"name": "ACE ONE", "threshold": 8}]})
    assert r.status_code == 200
    assert r.json()["parlay"]["ev"] == 0.375
