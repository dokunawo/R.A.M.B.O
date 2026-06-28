"""Tests for moneyline line shopping (best price across books + no-vig value)."""
import math

from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev.line_shop import american_to_decimal, line_shop_game, line_shop_slate


def _row(book, side, price):
    return {"market": "moneyline", "book": book, "side": side, "price": price}


# ── american_to_decimal ───────────────────────────────────────────────────────
def test_american_to_decimal():
    assert math.isclose(american_to_decimal(150), 2.5)
    assert math.isclose(american_to_decimal(-100), 2.0)
    assert math.isclose(american_to_decimal(-120), 1 + 100 / 120)


# ── line_shop_game ────────────────────────────────────────────────────────────
def test_best_price_and_book_per_side():
    rows = [
        _row("BookA", "home", -120), _row("BookA", "away", +100),
        _row("BookB", "home", -110), _row("BookB", "away", -110),
    ]
    out = line_shop_game(rows)
    assert out["n_books"] == 2
    # best home payout is the least-negative (-110 @ BookB); best away is +100 @ BookA
    assert out["sides"]["home"]["best_book"] == "BookB"
    assert out["sides"]["home"]["best_price"] == -110
    assert out["sides"]["home"]["worst_price"] == -120
    assert out["sides"]["away"]["best_book"] == "BookA"
    assert out["sides"]["away"]["best_price"] == +100
    # consensus probs are two-way fair and sum to ~1
    assert math.isclose(out["sides"]["home"]["consensus_prob"]
                        + out["sides"]["away"]["consensus_prob"], 1.0, abs_tol=1e-3)


def test_generous_book_shows_positive_value():
    # BookC posts a fat +135 on away while the field sits near pick'em → +EV vs
    # the consensus fair line (line-shopping value).
    rows = [
        _row("BookA", "home", -115), _row("BookA", "away", -105),
        _row("BookB", "home", -110), _row("BookB", "away", -110),
        _row("BookC", "home", -115), _row("BookC", "away", +135),
    ]
    out = line_shop_game(rows)
    assert out["sides"]["away"]["best_book"] == "BookC"
    assert out["sides"]["away"]["best_price"] == +135
    assert out["sides"]["away"]["edge"] > 0          # beats the field's fair line


def test_none_when_no_two_sided_book():
    rows = [_row("BookA", "home", -120), _row("BookB", "home", -110)]   # no away
    assert line_shop_game(rows) is None


def test_drops_live_and_zero_price():
    rows = [
        _row("DraftKings", "home", -120), _row("DraftKings", "away", +100),
        _row("BetMGM Live", "home", -500), _row("BetMGM Live", "away", +350),  # live
        _row("Caesars", "home", 0), _row("Caesars", "away", 0),                # suspended
    ]
    out = line_shop_game(rows)
    assert out["n_books"] == 1          # only DraftKings counts
    assert out["sides"]["home"]["best_book"] == "DraftKings"


# ── line_shop_slate (DB-backed) ───────────────────────────────────────────────
def test_line_shop_slate(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    now = "2026-06-26T00:00:00Z"
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
                 "home_team_abbr, away_team_abbr, scraped_at) "
                 "VALUES (999,'2026-06-26',147,111,'NYY','BOS',?)", (now,))
    for book, hp, ap in [("DraftKings", -120, +100), ("FanDuel", -110, -110)]:
        for side, price in (("home", hp), ("away", ap)):
            conn.execute("INSERT INTO odds_lines (game_pk, book, market, side, line, price, "
                         "captured_at) VALUES (999,?,'moneyline',?,NULL,?,?)",
                         (book, side, price, now))
    conn.commit()

    games = line_shop_slate(MlbRepo(conn), "2026-06-26")
    assert len(games) == 1
    g = games[0]
    assert g["home"] == "NYY" and g["away"] == "BOS"
    assert g["sides"]["home"]["best_book"] == "FanDuel"   # -110 beats -120
    assert g["sides"]["away"]["best_book"] == "DraftKings"  # +100 beats -110
