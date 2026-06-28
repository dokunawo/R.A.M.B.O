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

    def final_games(self, start: str, end: str) -> list[dict]:
        """Completed games (both final scores present) in [start, end] inclusive —
        the outcomes a moneyline backtest grades against."""
        return _dicts(self.conn.execute(
            "SELECT game_pk, official_date, home_team_id, away_team_id, "
            "home_team_abbr, away_team_abbr, home_score, away_score FROM games "
            "WHERE official_date BETWEEN ? AND ? "
            "AND home_score IS NOT NULL AND away_score IS NOT NULL "
            "ORDER BY official_date, game_pk", (start, end)))

    # -- odds (latest snapshot via the view) ---------------------------------

    def odds_history(self, game_pk: int, market: str = "moneyline") -> list[dict]:
        """All odds snapshots for a game/market, oldest→newest. Powers CLV
        (opening vs closing line) — latest_odds only gives the newest snapshot."""
        return _dicts(self.conn.execute(
            "SELECT book, market, side, price, captured_at FROM odds_lines "
            "WHERE game_pk=? AND market=? ORDER BY captured_at", (game_pk, market)))

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
               ORDER BY g.game_pk
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

    def player_bats(self, mlb_id: int) -> Optional[str]:
        row = self.conn.execute(
            "SELECT bats FROM players WHERE mlb_id=?", (mlb_id,)).fetchone()
        return row["bats"] if row else None

    def player_name(self, mlb_id: int) -> Optional[str]:
        row = self.conn.execute(
            "SELECT full_name FROM players WHERE mlb_id=?", (mlb_id,)).fetchone()
        return row["full_name"] if row else None

    def team_runs(self, team_id: int, season: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT runs_scored, runs_allowed, games_played FROM team_season_stats "
            "WHERE team_id=? AND season=?", (team_id, season)).fetchone()
        return dict(row) if row else None

    def pitcher_era(self, mlb_id: Optional[int], season: int) -> Optional[float]:
        """Starter's season ERA from pitching stats; None if unavailable."""
        if mlb_id is None:
            return None
        row = self.conn.execute(
            "SELECT stats FROM player_season_stats "
            "WHERE mlb_id=? AND season=? AND stat_group='pitching'",
            (mlb_id, season)).fetchone()
        if row is None:
            return None
        import json
        season_stat = (json.loads(row["stats"]).get("season") or {})
        try:
            return float(season_stat.get("era"))
        except (TypeError, ValueError):
            return None

    def player_recent(self, mlb_id: int, group: str = "hitting",
                      window: str = "L15") -> Optional[dict]:
        """Recent (last-N-day) stat dict, or None if not pulled."""
        row = self.conn.execute(
            "SELECT stats FROM player_recent_stats "
            "WHERE mlb_id=? AND stat_group=? AND window=?",
            (mlb_id, group, window)).fetchone()
        import json
        return json.loads(row["stats"]) if row else None

    def player_statcast(self, mlb_id: int, season: int) -> Optional[dict]:
        """Batter barrel% + hard-hit% (Baseball Savant), or None."""
        row = self.conn.execute(
            "SELECT barrel_rate, hard_hit FROM player_statcast WHERE mlb_id=? AND season=?",
            (mlb_id, season)).fetchone()
        return dict(row) if row else None

    def game_weather(self, game_pk: int) -> Optional[dict]:
        """Game weather (temp/condition/wind), or None if unposted."""
        row = self.conn.execute(
            "SELECT temp, condition, wind FROM game_weather WHERE game_pk=?",
            (game_pk,)).fetchone()
        return dict(row) if row else None

    def lineup_slot(self, mlb_id: int, game_pk: int) -> Optional[int]:
        """battingOrder (100..900) if the player is in the confirmed lineup, else None."""
        row = self.conn.execute(
            "SELECT batting_order FROM game_lineups WHERE game_pk=? AND mlb_id=?",
            (game_pk, mlb_id)).fetchone()
        return row["batting_order"] if row else None

    def lineup_confirmed(self, game_pk: int) -> bool:
        """True once any batting order is posted for the game."""
        return self.conn.execute(
            "SELECT COUNT(*) FROM game_lineups WHERE game_pk=?", (game_pk,)).fetchone()[0] > 0

    def probable_starters(self, date: str) -> list[dict]:
        """Each game's probable starting pitchers on `date` (both sides) with
        mlb_id, name, team abbr, opponent abbr — the pool for Strikeout Watch."""
        rows = self.conn.execute(
            """SELECT game_pk, home_team_abbr, away_team_abbr,
                      home_probable_pitcher_id, away_probable_pitcher_id
               FROM games WHERE official_date=?""", (date,)).fetchall()
        out: list[dict] = []
        for r in rows:
            for pid, team, opp in (
                (r["home_probable_pitcher_id"], r["home_team_abbr"], r["away_team_abbr"]),
                (r["away_probable_pitcher_id"], r["away_team_abbr"], r["home_team_abbr"]),
            ):
                if pid is None:
                    continue
                nm = self.conn.execute(
                    "SELECT full_name FROM players WHERE mlb_id=?", (pid,)).fetchone()
                out.append({"mlb_id": pid, "name": nm["full_name"] if nm else "",
                            "team_abbr": team or "", "opponent_abbr": opp or "",
                            "game_pk": r["game_pk"]})
        return out

    def lineup_batters(self, date: str) -> list[dict]:
        """Every hitter in a confirmed lineup on `date` (distinct mlb_id + name) —
        the candidate pool for the slate-wide Player Watch board."""
        return _dicts(self.conn.execute(
            """SELECT DISTINCT gl.mlb_id AS mlb_id, p.full_name AS name
               FROM game_lineups gl
               JOIN games g ON g.game_pk = gl.game_pk
               LEFT JOIN players p ON p.mlb_id = gl.mlb_id
               WHERE g.official_date = ?
               ORDER BY gl.mlb_id""", (date,)))

    def latest_capture(self, kind: str) -> Optional[str]:
        """Most-recent captured_at for provenance: kind 'moneyline' -> odds_lines
        (pregame), else -> prop_lines."""
        if kind == "moneyline":
            row = self.conn.execute(
                "SELECT MAX(captured_at) FROM odds_lines "
                "WHERE market='moneyline' AND book NOT LIKE '%Live%'").fetchone()
        else:
            row = self.conn.execute("SELECT MAX(captured_at) FROM prop_lines").fetchone()
        return row[0] if row and row[0] else None

    def moneyline_slate(self, date: str) -> list[dict]:
        """Games on `date` with a two-sided PREGAME moneyline, incl. team ids/abbrs,
        probable-pitcher ids, and home/away American prices. Picks the latest price
        per side from a pregame book — excludes in-game '… Live Odds' books and
        price=0 rows, whose extreme/suspended numbers would otherwise poison the line."""
        rows = self.conn.execute(
            """WITH ml AS (
                   SELECT game_pk, side, price,
                          ROW_NUMBER() OVER (PARTITION BY game_pk, side
                                             ORDER BY (book='DraftKings') DESC,
                                                      captured_at DESC) AS rn
                   FROM odds_lines
                   WHERE market='moneyline' AND price <> 0 AND book NOT LIKE '%Live%'
               )
               SELECT g.game_pk, g.game_datetime, g.home_team_id, g.away_team_id,
                      g.home_team_abbr, g.away_team_abbr,
                      g.home_probable_pitcher_id, g.away_probable_pitcher_id,
                      MAX(CASE WHEN m.side='home' THEN m.price END) AS home_price,
                      MAX(CASE WHEN m.side='away' THEN m.price END) AS away_price
               FROM games g
               JOIN ml m ON m.game_pk=g.game_pk AND m.rn=1
               WHERE g.official_date=?
               GROUP BY g.game_pk
               ORDER BY g.game_datetime IS NULL, g.game_datetime, g.away_team_abbr""", (date,)).fetchall()
        return [dict(r) for r in rows
                if r["home_price"] is not None and r["away_price"] is not None]

    # -- health / ops --------------------------------------------------------

    def unresolved_prop_count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM prop_lines WHERE mlb_id IS NULL").fetchone()[0]

    def review_queue(self, status: str = "pending") -> list[dict]:
        return _dicts(self.conn.execute(
            "SELECT * FROM player_review WHERE status=? ORDER BY created_at",
            (status,)))
