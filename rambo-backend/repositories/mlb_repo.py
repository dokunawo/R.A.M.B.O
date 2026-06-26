"""
R.A.M.B.O. MLB Betting Agent — Read repository (Step 5)
repositories/mlb_repo.py

The single read door to MLB data for downstream Brains (EV model, etc.). No Brain
reads raw_ingest or calls Apify directly — they all go through here, so the storage
shape can change without touching model code. Read-only by design: this class
never writes.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Optional


def _dicts(rows) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


class MlbRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # -- games ---------------------------------------------------------------

    def games_on(self, official_date: str) -> list[dict]:
        return _dicts(self.conn.execute(
            "SELECT * FROM games WHERE official_date=? ORDER BY game_pk",
            (official_date,)))

    def game(self, game_pk: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM games WHERE game_pk=?", (game_pk,)).fetchone()
        return dict(row) if row else None

    # -- odds (latest snapshot via the view) ---------------------------------

    def latest_odds(self, game_pk: Optional[int] = None,
                    market: Optional[str] = None) -> list[dict]:
        q = "SELECT * FROM v_latest_odds WHERE 1=1"
        params: list[Any] = []
        if game_pk is not None:
            q += " AND game_pk=?"; params.append(game_pk)
        if market:
            q += " AND market=?"; params.append(market)
        q += " ORDER BY game_pk, book, market, side"
        return _dicts(self.conn.execute(q, params))

    # -- player stats --------------------------------------------------------

    def player_recent_logs(self, mlb_id: int, stat_group: str = "hitting",
                           limit: int = 15) -> list[dict]:
        """Last N game logs, newest first — the input props models live on."""
        return _dicts(self.conn.execute(
            """SELECT * FROM player_game_logs
               WHERE mlb_id=? AND stat_group=?
               ORDER BY game_date DESC LIMIT ?""",
            (mlb_id, stat_group, limit)))

    def player_season(self, mlb_id: int, season: int,
                      stat_group: Optional[str] = None) -> list[dict]:
        q = "SELECT * FROM player_season_stats WHERE mlb_id=? AND season=?"
        params: list[Any] = [mlb_id, season]
        if stat_group:
            q += " AND stat_group=?"; params.append(stat_group)
        return _dicts(self.conn.execute(q, params))

    # -- props (latest snapshot per book/market/player) ----------------------

    def latest_props(self, game_pk: Optional[int] = None,
                     market: Optional[str] = None,
                     resolved_only: bool = True) -> list[dict]:
        q = """
            SELECT p.* FROM prop_lines p
            JOIN (
                SELECT book, market,
                       COALESCE(CAST(mlb_id AS TEXT), player_name_raw) AS pkey,
                       MAX(captured_at) AS mx
                FROM prop_lines GROUP BY book, market, pkey
            ) last
              ON p.book=last.book AND p.market=last.market
             AND COALESCE(CAST(p.mlb_id AS TEXT), p.player_name_raw)=last.pkey
             AND p.captured_at=last.mx
            WHERE 1=1
        """
        params: list[Any] = []
        if game_pk is not None:
            q += " AND p.game_pk=?"; params.append(game_pk)
        if market:
            q += " AND p.market=?"; params.append(market)
        if resolved_only:
            q += " AND p.mlb_id IS NOT NULL"
        q += " ORDER BY p.market, p.player_name_raw"
        return _dicts(self.conn.execute(q, params))

    # -- ev brain lookups ----------------------------------------------------

    def player_game_context(self, mlb_id: int, date: str) -> Optional[dict]:
        row = self.conn.execute(
            """SELECT g.game_pk, g.home_team_id, g.away_team_id,
                      g.home_team_abbr, g.away_team_abbr,
                      g.home_probable_pitcher_id, g.away_probable_pitcher_id,
                      p.current_team_id
               FROM games g JOIN players p ON p.mlb_id=?
               WHERE g.official_date=?
                 AND (g.home_team_id=p.current_team_id OR g.away_team_id=p.current_team_id)
               LIMIT 1""",
            (mlb_id, date)).fetchone()
        if row is None:
            return None
        is_home = row["home_team_id"] == row["current_team_id"]
        return {
            "game_pk": row["game_pk"],
            "is_home": is_home,
            "team_abbr": row["home_team_abbr"] if is_home else row["away_team_abbr"],
            "opponent_abbr": row["away_team_abbr"] if is_home else row["home_team_abbr"],
            "home_abbr": row["home_team_abbr"],
            "opp_pitcher_id": (row["away_probable_pitcher_id"] if is_home
                               else row["home_probable_pitcher_id"]),
        }

    def pitcher_throws(self, mlb_id: int) -> Optional[str]:
        row = self.conn.execute(
            "SELECT throws FROM players WHERE mlb_id=?", (mlb_id,)).fetchone()
        return row["throws"] if row else None

    # -- health / ops --------------------------------------------------------

    def unresolved_prop_count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM prop_lines WHERE mlb_id IS NULL").fetchone()[0]

    def review_queue(self, status: str = "pending") -> list[dict]:
        return _dicts(self.conn.execute(
            "SELECT * FROM player_review WHERE status=? ORDER BY created_at",
            (status,)))
