"""Tests for Closing Line Value (opening vs closing line, lean grading)."""
import math

from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev import clv

BOOK = "DraftKings"


def _r(side, price, ts, book=BOOK):
    return {"market": "moneyline", "book": book, "side": side, "price": price, "captured_at": ts}


def _history():
    # DraftKings line moves toward HOME over time: home shortens -120 -> -150,
    # away lengthens +100 -> +130.
    return [
        _r("home", -120, "2026-06-26T12:00Z"), _r("away", +100, "2026-06-26T12:00Z"),
        _r("home", -135, "2026-06-26T15:00Z"), _r("away", +115, "2026-06-26T15:00Z"),
        _r("home", -150, "2026-06-26T18:00Z"), _r("away", +130, "2026-06-26T18:00Z"),
    ]


def test_opening_and_closing_pick_edges():
    rows = _history()
    op, cl = clv.opening_line(rows, BOOK), clv.closing_line(rows, BOOK)
    assert op["home"] == -120 and op["away"] == +100
    assert cl["home"] == -150 and cl["away"] == +130


def test_closing_respects_game_time_cutoff():
    rows = _history()
    # cutoff before the 18:00 snapshot → close is the 15:00 line
    cl = clv.closing_line(rows, BOOK, game_datetime="2026-06-26T16:00Z")
    assert cl["home"] == -135 and cl["away"] == +115


def test_beat_close_pct_sign():
    # took +130, closed +100 → got a better payout → positive
    assert clv.beat_close_pct(+130, +100) > 0
    # took -150, closed -120 → worse payout → negative
    assert clv.beat_close_pct(-150, -120) < 0


def test_lean_on_home_gets_positive_clv_when_line_moves_home():
    out = clv.clv_for_game(_history(), side="home")
    assert out["side"] == "home"
    assert out["clv_pts"] > 0          # market moved toward home after open
    assert out["beat_close"] is True


def test_lean_on_away_is_negative_when_line_moves_home():
    out = clv.clv_for_game(_history(), side="away")
    assert out["clv_pts"] < 0
    assert out["beat_close"] is False


def test_none_without_two_sided_history():
    rows = [_r("home", -120, "2026-06-26T12:00Z")]   # no away
    assert clv.clv_for_game(rows, side="home") is None


def test_ignores_other_books():
    rows = _history() + [_r("home", +500, "2026-06-26T19:00Z", book="WeirdBook"),
                         _r("away", -900, "2026-06-26T19:00Z", book="WeirdBook")]
    cl = clv.closing_line(rows, BOOK)
    assert cl["home"] == -150          # WeirdBook's later, wild line is ignored


# ── DB-backed slate ───────────────────────────────────────────────────────────
def test_clv_slate(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    conn.execute("INSERT INTO games (game_pk, official_date, game_datetime, home_team_id, "
                 "away_team_id, home_team_abbr, away_team_abbr, scraped_at) "
                 "VALUES (999,'2026-06-26','2026-06-26T20:00Z',147,111,'NYY','BOS','x')")
    for r in _history():
        conn.execute("INSERT INTO odds_lines (game_pk, book, market, side, line, price, "
                     "captured_at) VALUES (999,?,?,?,NULL,?,?)",
                     (r["book"], r["market"], r["side"], r["price"], r["captured_at"]))
    conn.commit()

    games = clv.clv_slate(MlbRepo(conn), "2026-06-26", leans={999: "home"})
    assert len(games) == 1
    g = games[0]
    assert g["home"] == "NYY" and g["side"] == "home"
    assert g["clv_pts"] > 0 and g["opening"]["home"] == -120 and g["closing"]["home"] == -150
