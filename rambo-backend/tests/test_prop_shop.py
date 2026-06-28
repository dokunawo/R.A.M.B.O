"""Tests for prop line shopping: Pick6 vs sportsbook props (fetch, normalize, compare)."""
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev.prop_shop import compare_props, prop_shop_slate
from ingestion.normalize import map_props_book
from ingestion import the_odds_api_client as toa


# ── compare_props (pure) ──────────────────────────────────────────────────────
def _pick6(mult):
    return {"mlb_id": 1, "market": "HR", "line": 0.5, "multiplier": mult,
            "book": "dk_pick6", "player_name_raw": "Aaron Judge"}


def _book(name, over, under):
    return {"mlb_id": 1, "market": "HR", "line": 0.5, "book": name,
            "over_price": over, "under_price": under}


def test_compare_flags_plus_ev_when_multiplier_beats_book():
    # book fair P(over) ≈ 0.33; Pick6 4x → breakeven 0.25 → +EV
    pick6 = [_pick6(4.0)]
    books = [_book("BetRivers", +200, -260), _book("FanDuel", +180, -230)]
    out = compare_props(pick6, books)
    assert len(out) == 1
    r = out[0]
    assert r["pick6_breakeven"] == 0.25
    assert r["book_consensus_over"] > 0.30
    assert r["value"] > 0 and r["verdict"] == "+EV vs books"
    assert r["best_book"] == "BetRivers" and r["best_over_price"] == 200   # best payout


def test_compare_flags_minus_ev_on_thin_multiplier():
    pick6 = [_pick6(2.5)]   # breakeven 0.4 > book fair ~0.33
    books = [_book("BetRivers", +200, -260)]
    out = compare_props(pick6, books)
    assert out[0]["value"] < 0 and out[0]["verdict"] == "-EV vs books"


def test_compare_skips_unmatched_and_unresolved():
    assert compare_props([_pick6(3.0)], []) == []                 # no book match
    assert compare_props([{**_pick6(3.0), "mlb_id": None}],
                         [_book("X", 100, -120)]) == []            # unresolved pick6


# ── normalize: per-event props → prop_lines ───────────────────────────────────
def _event():
    return {
        "id": "evt1", "home_team": "Baltimore Orioles",
        "away_team": "Washington Nationals", "commence_time": "2026-06-28T17:36:00Z",
        "_captured_at": "2026-06-28T12:00:00Z",
        "bookmakers": [{"title": "BetRivers", "markets": [{
            "key": "batter_home_runs", "last_update": "2026-06-28T12:00:00Z",
            "outcomes": [
                {"name": "Over", "description": "James Wood", "price": 280, "point": 0.5},
                {"name": "Under", "description": "James Wood", "price": -360, "point": 0.5},
                {"name": "Over", "description": "Dylan Crews", "price": 450, "point": 0.5},
            ]}]},
        ],
    }


def test_map_props_book_groups_over_under_and_maps_market(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_name, away_team_name, "
                 "home_team_abbr, away_team_abbr, scraped_at) "
                 "VALUES (55,'2026-06-28','Baltimore Orioles','Washington Nationals','BAL','WSH','x')")
    conn.commit()
    assert map_props_book(conn, _event(), "2026-06-28T12:00:00Z") is True
    rows = conn.execute("SELECT market, line, over_price, under_price, multiplier, "
                        "player_name_raw, game_pk FROM prop_lines ORDER BY player_name_raw").fetchall()
    wood = [r for r in rows if r["player_name_raw"] == "James Wood"][0]
    assert wood["market"] == "HR" and wood["line"] == 0.5
    assert wood["over_price"] == 280 and wood["under_price"] == -360
    assert wood["multiplier"] is None and wood["game_pk"] == 55   # linked by team names
    crews = [r for r in rows if r["player_name_raw"] == "Dylan Crews"][0]
    assert crews["over_price"] == 450 and crews["under_price"] is None  # over-only is fine


# ── client fetch_props (mocked httpx) ─────────────────────────────────────────
class _Resp:
    def __init__(self, data, headers=None):
        self._d, self.headers = data, headers or {}
    def raise_for_status(self): pass
    def json(self): return self._d


class _FakeClient:
    def __init__(self):
        self.calls = []
    def get(self, url, params=None):
        self.calls.append(url)
        if url.endswith("/events"):
            return _Resp([{"id": "a", "commence_time": "2026-06-28T17:00:00Z"},
                          {"id": "b", "commence_time": "2026-06-28T20:00:00Z"}])
        return _Resp({"id": "a", "home_team": "H", "away_team": "A", "bookmakers": []},
                     {"x-requests-remaining": "383"})
    def close(self): pass


def test_fetch_props_caps_events_to_protect_credits(monkeypatch):
    monkeypatch.setenv("THE_ODDS_API_KEY", "test-key")   # mocked client, value unused
    fc = _FakeClient()
    run = toa.fetch_props(max_events=1, client=fc)
    assert run.item_count == 1                                   # only one event pulled
    odds_calls = [u for u in fc.calls if "/odds" in u]
    assert len(odds_calls) == 1                                  # one credit-spending call
    assert run.items[0].get("_captured_at")


# ── prop_shop_slate (DB-backed) ───────────────────────────────────────────────
def test_prop_shop_slate(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_abbr, away_team_abbr, "
                 "scraped_at) VALUES (77,'2026-06-28','NYY','BOS','x')")
    conn.execute("INSERT INTO players (mlb_id, full_name, current_team_id, updated_at) "
                 "VALUES (1,'Judge',147,'x')")
    ts = "2026-06-28T12:00:00Z"
    # resolved Pick6 leg (multiplier) + a resolved sportsbook prop, same player/market/line
    conn.execute("INSERT INTO prop_lines (game_pk, mlb_id, book, market, line, multiplier, "
                 "player_name_raw, captured_at) VALUES (77,1,'dk_pick6','HR',0.5,4.0,'Judge',?)", (ts,))
    conn.execute("INSERT INTO prop_lines (game_pk, mlb_id, book, market, line, over_price, "
                 "under_price, player_name_raw, captured_at) "
                 "VALUES (77,1,'BetRivers','HR',0.5,200,-260,'Judge',?)", (ts,))
    conn.commit()
    rows = prop_shop_slate(MlbRepo(conn), "2026-06-28")
    assert len(rows) == 1
    assert rows[0]["best_book"] == "BetRivers" and rows[0]["verdict"] == "+EV vs books"
