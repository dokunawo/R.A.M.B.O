from ingestion import prep


def test_no_fallback_when_free_has_props(monkeypatch):
    calls = []
    def fake_pull(conn, source, params=None):
        calls.append(source)
        return {"items": 12 if source == "prizepicks" else 0}
    monkeypatch.setattr(prep, "pull_source", fake_pull)
    summary = {}
    prep._pull_props_with_fallback(None, summary)
    assert summary["props"] == 12 and summary["props_source"] == "free"
    assert "prizepicks_paid" not in calls


def test_fallback_runs_when_free_zero_and_actor_configured(monkeypatch):
    calls = []
    def fake_pull(conn, source, params=None):
        calls.append(source)
        return {"items": 0 if source == "prizepicks" else 7}
    monkeypatch.setattr(prep, "pull_source", fake_pull)
    monkeypatch.setattr(prep, "paid_actor_config", lambda: object())  # configured
    summary = {}
    prep._pull_props_with_fallback(None, summary)
    assert "prizepicks_paid" in calls
    assert summary["props"] == 7 and summary["props_source"] == "paid"


def test_no_fallback_when_actor_unconfigured(monkeypatch):
    calls = []
    def fake_pull(conn, source, params=None):
        calls.append(source)
        return {"items": 0}
    monkeypatch.setattr(prep, "pull_source", fake_pull)
    monkeypatch.setattr(prep, "paid_actor_config", lambda: None)      # disabled
    summary = {}
    prep._pull_props_with_fallback(None, summary)
    assert "prizepicks_paid" not in calls
    assert summary["props"] == 0 and summary["props_source"] == "none"
