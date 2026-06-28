# tests/test_walkforward.py
from brains.ev.walkforward import pick_record, _prices_at
from db.migrate import get_connection, apply_migrations


def _ev(model_home, book_home, gpk=1):
    return {"game_pk": gpk, "home_abbr": "NYY", "away_abbr": "BOS",
            "model_home": model_home, "model_away": 1 - model_home,
            "book_home": book_home, "book_away": 1 - book_home}


def test_pick_record_leans_home_maps_both_prices():
    ev = _ev(0.60, 0.52)                       # model > book on home -> bet home
    rec = pick_record(ev, win_home=True,
                      early={"home": -120, "away": 100},
                      close={"home": -140, "away": 120})
    assert rec["p"] == 0.60
    assert rec["win"] == 1
    assert rec["odds_early"] == -120
    assert rec["odds_close"] == -140


def test_pick_record_leans_away_uses_away_win_and_prices():
    ev = _ev(0.40, 0.50)                       # model < book on home -> value on away
    rec = pick_record(ev, win_home=False,      # away won
                      early={"home": -120, "away": 100},
                      close={"home": -130, "away": 110})
    assert rec["p"] == 0.60                     # model_away
    assert rec["win"] == 1                      # away won
    assert rec["odds_early"] == 100
    assert rec["odds_close"] == 110


def test_pick_record_none_when_no_lean():
    ev = _ev(0.52, 0.52)                        # no edge either way
    assert pick_record(ev, win_home=True,
                       early={"home": -110, "away": -110},
                       close={"home": -110, "away": -110}) is None


def test_pick_record_none_when_price_missing():
    ev = _ev(0.60, 0.52)
    assert pick_record(ev, win_home=True,
                       early={"home": None, "away": 100},
                       close={"home": -120, "away": 100}) is None


def test_prices_at_includes_boundary_z_form(tmp_path):
    """_prices_at should include prices captured exactly at the window boundary
    when the timestamp uses Z form (as stored in DB)."""
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")

    game_pk = 999
    boundary_ts = "2026-05-01T23:05:00Z"
    now = "2026-05-01T00:00:00Z"

    # Create game record (required for foreign key)
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
                 "home_team_abbr, away_team_abbr, scraped_at) "
                 "VALUES (?, '2026-05-01', 1, 2, 'A', 'B', ?)",
                 (game_pk, now))

    # Insert moneyline prices at the exact boundary timestamp (Z form)
    conn.execute("INSERT INTO odds_lines (game_pk, book, market, side, price, captured_at) "
                 "VALUES (?, 'DK', 'moneyline', 'home', -120, ?)",
                 (game_pk, boundary_ts))
    conn.execute("INSERT INTO odds_lines (game_pk, book, market, side, price, captured_at) "
                 "VALUES (?, 'DK', 'moneyline', 'away', 100, ?)",
                 (game_pk, boundary_ts))
    conn.commit()

    # Query with Z-form bounds that include the boundary
    result = _prices_at(conn, game_pk, "2026-05-01T22:35:00Z", "2026-05-01T23:05:00Z")

    # Both prices should be found at the boundary
    assert result is not None
    assert result["home"] == -120
    assert result["away"] == 100
