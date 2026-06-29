"""Walk-forward moneyline backtest. For each final game in a date range, build a
point-in-time prediction (features strictly before game day), bet the side the model
leans vs the de-vigged early line, and grade the resulting records at BOTH the early
and closing price — so calibration is shared but ROI/CLV expose the entry-timing
effect. Scores through the existing backtest.evaluate()."""
from __future__ import annotations

import sqlite3

from brains.ev import backtest


def pick_record(ev: dict, win_home: bool, early: dict, close: dict) -> dict | None:
    """Build a graded record for the model's leaned side, or None when there's no
    lean or a needed price is missing. `early`/`close` map side -> American price."""
    if ev["model_home"] > ev["book_home"]:
        side, p, won = "home", ev["model_home"], win_home
    elif ev["model_away"] > ev["book_away"]:
        side, p, won = "away", ev["model_away"], not win_home
    else:
        return None
    oe, oc = early.get(side), close.get(side)
    if oe is None or oc is None:
        return None
    return {"p": p, "win": 1 if won else 0, "odds_early": oe, "odds_close": oc}


def _prices_at(conn: sqlite3.Connection, game_pk: int,
               lo: str, hi: str) -> dict | None:
    """home/away moneyline price from the latest snapshot within [lo,hi] (an
    early- or closing-window), pregame books only. None if the window is empty."""
    rows = conn.execute(
        """WITH ml AS (
               SELECT side, price,
                      ROW_NUMBER() OVER (PARTITION BY side ORDER BY captured_at DESC) AS rn
               FROM odds_lines
               WHERE game_pk=? AND market='moneyline' AND price<>0
                 AND book NOT LIKE '%Live%' AND captured_at BETWEEN ? AND ?)
           SELECT side, price FROM ml WHERE rn=1""", (game_pk, lo, hi)).fetchall()
    out = {r["side"]: r["price"] for r in rows}
    return out if "home" in out and "away" in out else None


def run(repo, start: str, end: str, predictor=None) -> dict:
    """Grade every final game in [start,end] using `predictor` (default: the
    closed-form AnchoredPredictor). Returns side-by-side early/close metrics plus
    coverage counters."""
    import datetime as _dt
    from brains.ev.moneyline_model import devig_two_way
    from brains.ev.ml.predictor import AnchoredPredictor
    if predictor is None:
        predictor = AnchoredPredictor()
    conn = repo.conn
    records: list[dict] = []
    skipped_features = skipped_odds = 0
    for g in repo.final_games(start, end):
        date = g["official_date"]
        season = int(date[:4])
        slate = {s["game_pk"]: s for s in repo.moneyline_slate(date)}
        s = slate.get(g["game_pk"])
        if not s:
            skipped_odds += 1
            continue
        predictor.prepare(repo, season, date)
        p_home = predictor.predict_home(repo, season, s, date)
        if p_home is None:
            skipped_features += 1
            continue
        book_home, book_away = devig_two_way(s["home_price"], s["away_price"])
        ev = {"model_home": p_home, "model_away": 1.0 - p_home,
              "book_home": book_home, "book_away": book_away}
        dt = s.get("game_datetime")
        if not dt:
            skipped_odds += 1
            continue
        t = _dt.datetime.fromisoformat(dt)
        early = _prices_at(conn, g["game_pk"],
                           (t - _dt.timedelta(hours=6)).isoformat().replace("+00:00", "Z"),
                           (t - _dt.timedelta(hours=2)).isoformat().replace("+00:00", "Z"))
        close = _prices_at(conn, g["game_pk"],
                           (t - _dt.timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
                           t.isoformat().replace("+00:00", "Z"))
        if not early or not close:
            skipped_odds += 1
            continue
        win_home = g["home_score"] > g["away_score"]
        rec = pick_record(ev, win_home, early, close)
        if rec is None:
            continue
        records.append(rec)

    early_records = [{"p": r["p"], "win": r["win"], "odds": r["odds_early"],
                      "close": r["odds_close"]} for r in records]
    close_records = [{"p": r["p"], "win": r["win"], "odds": r["odds_close"]}
                     for r in records]
    return {
        "n": len(records),
        "skipped_features": skipped_features,
        "skipped_odds": skipped_odds,
        "early": backtest.evaluate(early_records),
        "close": backtest.evaluate(close_records),
    }
