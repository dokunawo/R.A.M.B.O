from ingestion import the_odds_api_client as toa


class _FakeResp:
    def __init__(self, payload):
        self._p = payload
        self.headers = {"x-requests-remaining": "19990"}
    def raise_for_status(self):
        pass
    def json(self):
        return self._p


class _FakeClient:
    def __init__(self, payload):
        self._p = payload
        self.last_url = None
        self.last_params = None
    def get(self, url, params=None):
        self.last_url = url
        self.last_params = params
        return _FakeResp(self._p)
    def close(self):
        pass


def test_fetch_historical_unwraps_data_and_stamps_timestamp(monkeypatch):
    monkeypatch.setenv("THE_ODDS_API_KEY", "k")
    payload = {
        "timestamp": "2026-05-01T16:00:00Z",
        "previous_timestamp": "2026-05-01T15:55:00Z",
        "next_timestamp": "2026-05-01T16:05:00Z",
        "data": [
            {"id": "abc", "home_team": "New York Yankees",
             "away_team": "Boston Red Sox", "commence_time": "2026-05-01T23:05:00Z",
             "bookmakers": []},
        ],
    }
    client = _FakeClient(payload)
    run = toa.fetch_moneyline_historical("2026-05-01T16:00:00Z", client=client)
    assert "/historical/sports/baseball_mlb/odds" in client.last_url
    assert client.last_params["date"] == "2026-05-01T16:00:00Z"
    assert run.item_count == 1
    assert run.actor_id == toa.cfg.SOURCE_ID          # routes through existing normalizer
    assert run.items[0]["_captured_at"] == "2026-05-01T16:00:00Z"


def test_fetch_historical_normalizes_plus_offset_to_z(monkeypatch):
    """Regression: The Odds API rejects +00:00 UTC offset form, requires Z."""
    monkeypatch.setenv("THE_ODDS_API_KEY", "k")
    payload = {
        "timestamp": "2026-05-01T19:05:00Z",
        "data": [
            {"id": "abc", "home_team": "New York Yankees",
             "away_team": "Boston Red Sox", "commence_time": "2026-05-01T23:05:00Z",
             "bookmakers": []},
        ],
    }
    client = _FakeClient(payload)
    run = toa.fetch_moneyline_historical("2026-05-01T19:05:00+00:00", client=client)
    assert client.last_params["date"] == "2026-05-01T19:05:00Z"
    assert run.item_count == 1


def test_fetch_historical_z_passthrough_unchanged(monkeypatch):
    """If input already uses Z, pass it through unchanged."""
    monkeypatch.setenv("THE_ODDS_API_KEY", "k")
    payload = {
        "timestamp": "2026-05-01T19:05:00Z",
        "data": [
            {"id": "abc", "home_team": "New York Yankees",
             "away_team": "Boston Red Sox", "commence_time": "2026-05-01T23:05:00Z",
             "bookmakers": []},
        ],
    }
    client = _FakeClient(payload)
    run = toa.fetch_moneyline_historical("2026-05-01T19:05:00Z", client=client)
    assert client.last_params["date"] == "2026-05-01T19:05:00Z"
    assert run.item_count == 1
