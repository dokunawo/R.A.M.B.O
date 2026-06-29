"""Leak-free calibration backtest for the strikeout model. For each historical start
it builds k_projection as-of the start date and grades P(j+ K) against the real K
count from the game log. No odds — pure calibration (Brier / log-loss / bins)."""
from __future__ import annotations

import json

from brains.ev.k_model import k_projection
from brains.ev import backtest


def run(repo, start: str, end: str, thresholds=(6, 7, 8, 9, 10)) -> dict:
    conn = repo.conn
    rows = conn.execute(
        "SELECT mlb_id, game_date, opponent_team_id, stats FROM player_game_logs "
        "WHERE stat_group='pitching' AND game_date BETWEEN ? AND ? "
        "ORDER BY game_date, mlb_id", (start, end)).fetchall()
    records = {j: [] for j in thresholds}
    n_starts = skipped = 0
    for r in rows:
        stat = (json.loads(r["stats"]).get("stat") or {})
        actual = stat.get("strikeOuts")
        if actual is None:
            skipped += 1
            continue
        date = r["game_date"]
        starter = {"mlb_id": r["mlb_id"], "name": "", "team_abbr": "",
                   "opponent_abbr": "", "opponent_team_id": r["opponent_team_id"]}
        proj = k_projection(repo, date, starter)   # before_date defaults to date -> leak-free
        if proj is None:
            skipped += 1
            continue
        n_starts += 1
        for j in thresholds:
            records[j].append({"p": proj["ladder"].get(j, 0.0),
                               "win": 1 if int(actual) >= j else 0, "odds": 100})
    out: dict = {"n_starts": n_starts, "skipped": skipped}
    for j in thresholds:
        out[j] = backtest.evaluate(records[j])
    return out
