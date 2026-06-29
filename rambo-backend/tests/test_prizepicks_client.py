from ingestion import prizepicks_client as pc


class _Resp:
    def __init__(self, payload): self._p = payload; self.status_code = 200
    def raise_for_status(self): pass
    def json(self): return self._p


class _Client:
    def __init__(self, payload): self._p = payload; self.calls = []
    def get(self, url, params=None, headers=None):
        self.calls.append((url, params)); return _Resp(self._p)
    def close(self): pass


def _payload():
    return {
        "data": [
            {"id": "p1", "type": "projection",
             "attributes": {"line_score": 0.5, "stat_type": "Home Runs",
                            "odds_type": "standard", "start_time": "2026-06-29T19:00:00-04:00",
                            "game_id": "g9"},
             "relationships": {"new_player": {"data": {"type": "new_player", "id": "np1"}}}},
        ],
        "included": [
            {"id": "np1", "type": "new_player",
             "attributes": {"name": "Aaron Judge", "team": "NYY", "position": "OF"}},
        ],
        "links": {},
    }


def test_fetch_joins_player_and_flattens():
    run = pc.fetch_mlb_props(client=_Client(_payload()))
    assert run.actor_id == "prizepicks" and run.estimated_cost_usd == 0.0
    assert run.item_count == 1
    it = run.items[0]
    assert it["player_name"] == "Aaron Judge" and it["team"] == "NYY"
    assert it["stat_type"] == "Home Runs" and it["line"] == 0.5
    assert it["odds_type"] == "standard" and it["projection_id"] == "p1"


def test_fetch_never_raises_on_bad_payload():
    run = pc.fetch_mlb_props(client=_Client({"nonsense": True}))
    assert run.item_count == 0 and run.actor_id == "prizepicks"
