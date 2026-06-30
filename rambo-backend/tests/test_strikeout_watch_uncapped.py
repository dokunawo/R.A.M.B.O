"""The strikeout-watch endpoint must translate limit/min_starts into the board's
count/min_starts kwargs: default caps at 11; limit<=0 means all (count=None)."""
from fastapi.testclient import TestClient
from main import app
import api.betting as betting

client = TestClient(app)


def _capture(monkeypatch):
    seen = {}
    def fake_watch(d, *, count=11, min_starts=None, as_of=None, book=None):
        seen["count"] = count
        seen["min_starts"] = min_starts
        return {"title": "STRIKEOUT WATCH", "product": "Strikeout model (alt-K)",
                "count": 0, "rows": [], "prompt": "x"}
    monkeypatch.setattr(betting, "strikeout_watch", fake_watch)
    return seen


def test_default_caps_at_11(monkeypatch):
    seen = _capture(monkeypatch)
    r = client.get("/betting/strikeout-watch?date=2026-06-30")
    assert r.status_code == 200
    assert seen["count"] == 11 and seen["min_starts"] is None


def test_limit_zero_means_all(monkeypatch):
    seen = _capture(monkeypatch)
    r = client.get("/betting/strikeout-watch?date=2026-06-30&limit=0&min_starts=0")
    assert r.status_code == 200
    assert seen["count"] is None        # uncapped
    assert seen["min_starts"] == 0      # low-sample starters included


def test_explicit_limit_passes_through(monkeypatch):
    seen = _capture(monkeypatch)
    r = client.get("/betting/strikeout-watch?date=2026-06-30&limit=20")
    assert r.status_code == 200
    assert seen["count"] == 20
