"""Closing Line Value — grade a directional lean against the closing moneyline,
using the odds_lines history we already capture.

odds_lines is append-only with captured_at, so the closing line is just the last
snapshot at/under game time. Beating the close is the cleanest honest signal that
a lean had real value, independent of whether the bet won.

To keep the time series clean we track a single REFERENCE book (DraftKings by
default — the product's reference, matching moneyline_slate's preference) rather
than mixing books with different update cadences.
"""
from __future__ import annotations

import os

from brains.ev.moneyline_model import devig_two_way
from brains.ev.line_shop import american_to_decimal

_SIDES = ("home", "away")


def _ref_book() -> str:
    return os.environ.get("RAMBO_CLV_BOOK", "DraftKings")


def _series(rows, book):
    """Moneyline rows for the reference book, valid prices only."""
    return [r for r in rows
            if r.get("market") == "moneyline" and (r.get("book") == book)
            and r.get("price") and r.get("side") in _SIDES and r.get("captured_at")]


def _edge_snapshot(rows, *, latest: bool, cutoff=None):
    """Per-side price at the earliest (latest=False) or latest (latest=True)
    captured_at, optionally only counting snapshots at/under `cutoff`."""
    chosen: dict = {}     # side -> (captured_at, price)
    for r in rows:
        ts, side, price = r["captured_at"], r["side"], r["price"]
        if cutoff and ts > cutoff:
            continue
        cur = chosen.get(side)
        if cur is None or (ts > cur[0] if latest else ts < cur[0]):
            chosen[side] = (ts, price)
    if "home" not in chosen or "away" not in chosen:
        return None
    pick = max if latest else min
    return {"home": chosen["home"][1], "away": chosen["away"][1],
            "as_of": pick(chosen["home"][0], chosen["away"][0])}


def opening_line(rows, book=None):
    return _edge_snapshot(_series(rows, book or _ref_book()), latest=False)


def closing_line(rows, book=None, game_datetime=None):
    """Latest snapshot at/under game time (or latest overall if no game time)."""
    return _edge_snapshot(_series(rows, book or _ref_book()),
                          latest=True, cutoff=game_datetime)


def beat_close_pct(taken_price: int, close_price: int) -> float:
    """How much better the taken payout is vs the close (>0 = beat the close)."""
    return american_to_decimal(taken_price) / american_to_decimal(close_price) - 1


def _fair(home_price, away_price, side):
    fh, fa = devig_two_way(home_price, away_price)
    return fh if side == "home" else fa


def clv_for_game(rows, *, side=None, book=None, game_datetime=None) -> dict | None:
    """Opening + closing reference-book lines for a game; if `side` (the lean) is
    given, the open→close CLV for that side (no-vig prob points + beat-the-close
    %). None when the reference book lacks both an opening and closing two-sided
    quote."""
    book = book or _ref_book()
    op = opening_line(rows, book)
    cl = closing_line(rows, book, game_datetime)
    if not op or not cl:
        return None
    out = {"book": book, "opening": op, "closing": cl}
    if side in _SIDES:
        open_fair = _fair(op["home"], op["away"], side)
        close_fair = _fair(cl["home"], cl["away"], side)
        out["side"] = side
        out["clv_pts"] = round(close_fair - open_fair, 4)        # +ve = moved our way
        out["beat_close_pct"] = round(beat_close_pct(op[side], cl[side]), 4)
        out["beat_close"] = out["clv_pts"] > 0
    return out


def clv_slate(repo, date: str, leans: dict | None = None) -> list[dict]:
    """CLV per moneyline game on `date`. `leans` maps game_pk -> 'home'/'away'
    (RAMBO's lean) so each line is graded; without it, just open/close lines."""
    leans = leans or {}
    out = []
    for g in repo.moneyline_slate(date):
        gp = g["game_pk"]
        c = clv_for_game(repo.odds_history(gp), side=leans.get(gp),
                         game_datetime=g.get("game_datetime"))
        if not c:
            continue
        out.append({"game_pk": gp, "home": g["home_team_abbr"],
                    "away": g["away_team_abbr"], **c})
    return out
